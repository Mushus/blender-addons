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


def select_center(mesh) -> None:
    bm = bmesh.from_edit_mesh(mesh)
    for vert in bm.verts:
        vert.select = vert.index == 4
    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)


def select_vertices(mesh, indices: set[int]) -> None:
    bm = bmesh.from_edit_mesh(mesh)
    for vert in bm.verts:
        vert.select = vert.index in indices
    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)


def center_coordinate(mesh):
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    return bm.verts[4].co.copy()


def test_relax_selected_vertices():
    """背景: マルチオブジェクト Edit Mode と境界保持が本番の主要経路。
    なぜ: 選択頂点だけ動き、非選択は不変、strength=0 は無変更、
    境界頂点は内向きに動かないことを回帰で固定する。
    """
    first = make_fan("Vertex Relax First")
    second = make_fan("Vertex Relax Second")
    bpy.context.view_layer.objects.active = first
    first.select_set(True)
    second.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    select_center(first.data)
    select_center(second.data)

    untouched_corner = bmesh.from_edit_mesh(first.data).verts[0].co.copy()
    before_first = center_coordinate(first.data)
    before_second = center_coordinate(second.data)

    settings = bpy.context.scene.edit_vertex_relax
    settings.strength = 0.5
    settings.iterations = 1
    assert bpy.ops.edit_vertex_relax.relax_selected_vertices() == {"FINISHED"}

    after_first = center_coordinate(first.data)
    after_second = center_coordinate(second.data)
    assert after_first != before_first
    assert after_second != before_second
    assert bmesh.from_edit_mesh(first.data).verts[0].co == untouched_corner
    assert abs(after_first.x - 0.7) < 1e-6
    assert abs(after_first.y - 0.65) < 1e-6

    before_zero = center_coordinate(first.data)
    settings.strength = 0.0
    assert bpy.ops.edit_vertex_relax.relax_selected_vertices() == {"FINISHED"}
    assert center_coordinate(first.data) == before_zero

    settings.strength = 0.5
    assert settings.preserve_boundaries
    select_vertices(first.data, {0})
    select_vertices(second.data, set())
    boundary_before = bmesh.from_edit_mesh(first.data).verts[0].co.copy()
    assert bpy.ops.edit_vertex_relax.relax_selected_vertices() == {"FINISHED"}
    assert bmesh.from_edit_mesh(first.data).verts[0].co == boundary_before

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
    obj = make_boundary_strip("Vertex Relax Boundary Slide")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    select_vertices(obj.data, {1})

    settings = bpy.context.scene.edit_vertex_relax
    settings.strength = 0.5
    settings.iterations = 1
    settings.preserve_boundaries = True
    before = bmesh.from_edit_mesh(obj.data).verts[1].co.copy()
    assert bpy.ops.edit_vertex_relax.relax_selected_vertices() == {"FINISHED"}
    after = bmesh.from_edit_mesh(obj.data).verts[1].co.copy()
    assert after.x > before.x
    assert abs(after.y - before.y) < 1e-6

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.data.objects.remove(obj, do_unlink=True)


def main():
    options = parse_args()
    temp_dir = Path(tempfile.mkdtemp(prefix="blender-edit-vertex-relax-smoke-"))
    extract_zip(Path(options.zip).resolve(), temp_dir)
    sys.path.insert(0, str(temp_dir))

    addon = importlib.import_module("edit_vertex_relax")
    addon.register()
    host_state = bpy.app.driver_namespace["blender_addon_tools.embedded_host.v1"]
    assert "edit_vertex_relax" in host_state["tools"]
    assert "mesh_utility" in host_state["groups"]
    try:
        test_relax_selected_vertices()
        test_boundary_slide_preserves_outline()
    finally:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        addon.unregister()
    print("Edit Vertex Relax functional smoke test passed")



if __name__ == "__main__":
    main()
