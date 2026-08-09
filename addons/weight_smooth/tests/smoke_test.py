from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from zip_utils import extract_zip


def parse_args():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    return parser.parse_args(raw)


def clear_factory_mesh() -> None:
    """factory startup の Cube が混入しないように消す。"""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def make_skinned_strip(name: str):
    """2 ボーン + 3 頂点の短冊。中央頂点だけ選択してスムーズ効果を見る。"""
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(
        [(0, 0, 0), (1, 0.2, 0), (2, 0, 0)],
        [],
        [(0, 1, 2)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    arm_data = bpy.data.armatures.new(f"{name} Armature")
    arm_obj = bpy.data.objects.new(f"{name} Armature", arm_data)
    bpy.context.collection.objects.link(arm_obj)

    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    bone_a = arm_data.edit_bones.new("BoneA")
    bone_a.head = (0, 0, 0)
    bone_a.tail = (1, 0, 0)
    bone_b = arm_data.edit_bones.new("BoneB")
    bone_b.head = (1, 0, 0)
    bone_b.tail = (2, 0, 0)
    bpy.ops.object.mode_set(mode="OBJECT")

    modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
    modifier.object = arm_obj

    obj.vertex_groups.new(name="BoneA")
    obj.vertex_groups.new(name="BoneB")
    obj.vertex_groups.new(name="Mask")
    # 選択中央 (1): BoneA=1。近傍 (0)(2) は BoneA/BoneB が分かれる。
    obj.vertex_groups["BoneA"].add([0], 1.0, "REPLACE")
    obj.vertex_groups["BoneA"].add([1], 1.0, "REPLACE")
    obj.vertex_groups["BoneB"].add([2], 1.0, "REPLACE")
    obj.vertex_groups["Mask"].add([0, 1, 2], 0.25, "REPLACE")
    return obj, arm_obj


def enter_weight_paint_vertex_select(obj, indices: set[int]) -> None:
    """Object Mode で頂点選択を確定してから Weight Paint + 頂点マスクへ入る。"""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    mesh = obj.data
    for poly in mesh.polygons:
        poly.select = False
    for edge in mesh.edges:
        edge.select = False
    for vert in mesh.vertices:
        vert.select = vert.index in indices
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    mesh.use_paint_mask = False
    mesh.use_paint_mask_vertex = True
    # WP 入場で選択がフラッシュされることがあるので再適用する。
    for poly in mesh.polygons:
        poly.select = False
    for edge in mesh.edges:
        edge.select = False
    for vert in mesh.vertices:
        vert.select = vert.index in indices



def read_weights(obj, vert_index: int) -> dict[str, float]:
    result: dict[str, float] = {}
    for group in obj.vertex_groups:
        try:
            result[group.name] = group.weight(vert_index)
        except RuntimeError:
            result[group.name] = 0.0
    return result


def cleanup(obj, arm) -> None:
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    arm_data = arm.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.objects.remove(arm, do_unlink=True)
    bpy.data.armatures.remove(arm_data, do_unlink=True)


def test_enable_vertex_select_then_smooth():
    """背景: Weight Paint で頂点選択マスクが無いと選択が効かない。
    なぜ: 初回クリックでマスク有効化、2 回目でスムーズする契約を固定する。
    """
    obj, arm = make_skinned_strip("Weight Smooth")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    obj.data.use_paint_mask_vertex = False
    obj.data.use_paint_mask = True

    assert bpy.ops.weight_smooth.smooth() == {"FINISHED"}
    assert obj.data.use_paint_mask_vertex is True
    assert obj.data.use_paint_mask is False

    # マスク有効化後に Object Mode 経由で中央頂点だけ選ぶ。
    enter_weight_paint_vertex_select(obj, {1})
    assert sum(1 for vert in obj.data.vertices if vert.select) == 1

    before_unselected = read_weights(obj, 0)
    before_center = read_weights(obj, 1)
    assert before_center["BoneA"] == 1.0
    assert before_center["BoneB"] == 0.0
    assert before_center["Mask"] == 0.25

    settings = bpy.context.scene.weight_smooth
    settings.factor = 1.0
    settings.iterations = 1
    assert bpy.ops.weight_smooth.smooth() == {"FINISHED"}

    after_unselected = read_weights(obj, 0)
    after_center = read_weights(obj, 1)
    assert after_unselected == before_unselected
    assert after_center["Mask"] == 0.25
    assert after_center["BoneA"] < before_center["BoneA"]
    assert after_center["BoneB"] > before_center["BoneB"]
    assert abs(after_center["BoneA"] + after_center["BoneB"] - 1.0) < 1e-5

    cleanup(obj, arm)


def test_locked_and_missing_armature():
    """背景: ロック VG と Armature 欠落は仕様どおり触らない／即エラー。
    なぜ: フォールバック無しの契約を固定する。
    """
    obj, arm = make_skinned_strip("Weight Smooth Lock")
    obj.vertex_groups["BoneA"].add([1], 0.7, "REPLACE")
    obj.vertex_groups["BoneB"].add([1], 0.3, "REPLACE")
    obj.vertex_groups["BoneB"].lock_weight = True
    enter_weight_paint_vertex_select(obj, {1})

    before = read_weights(obj, 1)
    assert abs(before["BoneB"] - 0.3) < 1e-6
    settings = bpy.context.scene.weight_smooth
    settings.factor = 1.0
    settings.iterations = 1
    assert bpy.ops.weight_smooth.smooth() == {"FINISHED"}
    after = read_weights(obj, 1)
    assert abs(after["BoneB"] - 0.3) < 1e-6
    assert after["Mask"] == before["Mask"]
    assert abs(after["BoneA"] + after["BoneB"] - 1.0) < 1e-5

    cleanup(obj, arm)

    mesh = bpy.data.meshes.new("No Arm Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    orphan = bpy.data.objects.new("No Arm", mesh)
    bpy.context.collection.objects.link(orphan)
    orphan.vertex_groups.new(name="BoneA")
    enter_weight_paint_vertex_select(orphan, {0})
    # ERROR レポート付き CANCELLED は bpy.ops 経由で RuntimeError になる。
    raised = False
    try:
        bpy.ops.weight_smooth.smooth()
    except RuntimeError as exc:
        raised = True
        assert "Armature not found" in str(exc)
    assert raised
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.data.objects.remove(orphan, do_unlink=True)


def test_no_selection():
    """背景: 選択なしは書き込み対象が無い。
    なぜ: 空操作を CANCELLED で明示する。
    """
    obj, arm = make_skinned_strip("Weight Smooth Empty")
    enter_weight_paint_vertex_select(obj, set())
    assert bpy.ops.weight_smooth.smooth() == {"CANCELLED"}
    cleanup(obj, arm)


def main():
    options = parse_args()
    temp_dir = Path(tempfile.mkdtemp(prefix="blender-weight-smooth-smoke-"))
    extract_zip(Path(options.zip).resolve(), temp_dir)
    sys.path.insert(0, str(temp_dir))

    addon = importlib.import_module("weight_smooth")
    addon.register()
    host_state = bpy.app.driver_namespace["blender_addon_tools.embedded_host.v1"]
    assert "weight_smooth" in host_state["tools"]
    assert "weight_utility" in host_state["groups"]
    clear_factory_mesh()
    try:
        test_enable_vertex_select_then_smooth()
        test_locked_and_missing_armature()
        test_no_selection()
    finally:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        addon.unregister()
    print("Smooth Weight functional smoke test passed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        raise SystemExit(1) from None
