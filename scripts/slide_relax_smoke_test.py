from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zip_utils import extract_zip


def parse_args():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    return parser.parse_args(raw)


def clear_factory_mesh() -> None:
    """factory startup の Cube が Edit Mode に混入しないように消す。"""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def make_fan(name: str):
    """中心点が偏った扇形。接線緩和の移動量を既知座標で検証するため。"""
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(
        [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (0.4, 0.3, 0)],
        [],
        [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _apply_vert_selection(mesh, indices: set[int]) -> None:
    """頂点選択だけを残す。面/辺の選択が残ると update 時に頂点へ再フラッシュされる。"""
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    for face in bm.faces:
        face.select = False
    for edge in bm.edges:
        edge.select = False
    for vert in bm.verts:
        vert.select = vert.index in indices
    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)


def select_center(mesh) -> None:
    _apply_vert_selection(mesh, {4})


def select_vertices(mesh, indices: set[int]) -> None:
    _apply_vert_selection(mesh, indices)


def center_coordinate(mesh):
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    return bm.verts[4].co.copy()


def vert_coordinate(mesh, index: int):
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    return bm.verts[index].co.copy()


def test_slide_relax():
    """背景: マルチオブジェクト Edit Mode が本番の主要経路。
    なぜ: 選択頂点だけ動き、非選択オブジェクトは不変、strength=0 は無変更を固定する。
    境界スライドの詳細は test_boundary_slide_preserves_outline で見る。
    """
    first = make_fan("Slide Relax First")
    second = make_fan("Slide Relax Second")
    bpy.context.view_layer.objects.active = first
    first.select_set(True)
    second.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    select_center(first.data)
    select_center(second.data)

    untouched_corner = vert_coordinate(first.data, 0)
    before_first = center_coordinate(first.data)
    before_second = center_coordinate(second.data)

    settings = bpy.context.scene.slide_relax
    settings.strength = 0.5
    settings.iterations = 1
    assert bpy.ops.slide_relax.slide_relax() == {"FINISHED"}

    after_first = center_coordinate(first.data)
    after_second = center_coordinate(second.data)
    assert after_first != before_first
    assert after_second != before_second
    assert vert_coordinate(first.data, 0) == untouched_corner
    assert abs(after_first.x - 0.7) < 1e-6
    assert abs(after_first.y - 0.65) < 1e-6

    before_zero = center_coordinate(first.data)
    settings.strength = 0.0
    assert bpy.ops.slide_relax.slide_relax() == {"FINISHED"}
    assert center_coordinate(first.data) == before_zero

    settings.strength = 0.5
    select_vertices(first.data, {4})
    select_vertices(second.data, set())
    first_before = center_coordinate(first.data)
    second_before = center_coordinate(second.data)
    assert bpy.ops.slide_relax.slide_relax() == {"FINISHED"}
    assert center_coordinate(first.data) != first_before
    assert center_coordinate(second.data) == second_before

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.data.objects.remove(first, do_unlink=True)
    bpy.data.objects.remove(second, do_unlink=True)


def make_boundary_strip(name: str):
    """境界辺上の中間点が内寄りに置かれた短冊。境界沿い移動の可否を見る。"""
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(
        [(0, 0, 0), (0.7, 0, 0), (2, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0)],
        [],
        [(0, 1, 4, 3), (1, 2, 5, 4)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def test_boundary_slide_preserves_outline():
    """背景: 境界保持は内向き成分だけを除去し、境界沿いのスライドは残す仕様。
    なぜ: 輪郭収縮だけを防ぎつつ、境界上の偏り緩和が効くことを固定する。
    """
    obj = make_boundary_strip("Slide Relax Boundary Slide")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    select_vertices(obj.data, {1})

    settings = bpy.context.scene.slide_relax
    settings.strength = 0.5
    settings.iterations = 1
    settings.preserve_boundaries = True
    before = vert_coordinate(obj.data, 1)
    assert bpy.ops.slide_relax.slide_relax() == {"FINISHED"}
    after = vert_coordinate(obj.data, 1)
    assert after.x > before.x
    assert abs(after.y - before.y) < 1e-6

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.data.objects.remove(obj, do_unlink=True)


def main():
    options = parse_args()
    temp_dir = Path(tempfile.mkdtemp(prefix="blender-slide-relax-smoke-"))
    extract_zip(Path(options.zip).resolve(), temp_dir)
    sys.path.insert(0, str(temp_dir))

    addon = importlib.import_module("slide_relax")
    addon.register()
    host_state = bpy.app.driver_namespace["blender_addon_tools.embedded_host.v1"]
    assert "slide_relax" in host_state["tools"]
    assert "mesh_utility" in host_state["groups"]
    clear_factory_mesh()
    try:
        test_slide_relax()
        test_boundary_slide_preserves_outline()
    finally:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        addon.unregister()
    print("Slide Relax functional smoke test passed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        raise SystemExit(1) from None
