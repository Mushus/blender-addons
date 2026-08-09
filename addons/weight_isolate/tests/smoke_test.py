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
    """2 ボーン + 3 頂点の短冊。中央頂点だけ選択してアイソレート効果を見る。"""
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
    obj.vertex_groups.new(name="NonDeform")
    obj.vertex_groups["BoneA"].add([0], 1.0, "REPLACE")
    obj.vertex_groups["BoneA"].add([1], 0.6, "REPLACE")
    obj.vertex_groups["BoneB"].add([1], 0.4, "REPLACE")
    obj.vertex_groups["BoneB"].add([2], 1.0, "REPLACE")
    obj.vertex_groups["NonDeform"].add([0, 1, 2], 0.5, "REPLACE")
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


def test_enable_vertex_select_then_isolate():
    """背景: Weight Paint で頂点選択マスクが無いと選択が効かない。
    なぜ: 初回クリックでマスク有効化、2回目でアクティブボーンのウェイトを1.0にアイソレートする契約を固定する。
    """
    obj, arm = make_skinned_strip("Weight Isolate")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    obj.data.use_paint_mask_vertex = False
    obj.data.use_paint_mask = True

    # 1回目: 頂点選択マスクが自動的に有効化される
    assert bpy.ops.weight_isolate.isolate() == {"FINISHED"}
    assert obj.data.use_paint_mask_vertex is True
    assert obj.data.use_paint_mask is False

    # マスク有効化後に中央頂点を選択し、BoneA を active vertex group にする
    enter_weight_paint_vertex_select(obj, {1})
    obj.vertex_groups.active_index = obj.vertex_groups["BoneA"].index

    before_unselected = read_weights(obj, 0)
    before_center = read_weights(obj, 1)
    assert abs(before_center["BoneA"] - 0.6) < 1e-6
    assert abs(before_center["BoneB"] - 0.4) < 1e-6
    assert abs(before_center["NonDeform"] - 0.5) < 1e-6

    # 2回目: アイソレート実行 (BoneA = 1.0, BoneB = 0.0)
    assert bpy.ops.weight_isolate.isolate() == {"FINISHED"}

    after_unselected = read_weights(obj, 0)
    after_center = read_weights(obj, 1)
    assert after_unselected == before_unselected
    assert abs(after_center["BoneA"] - 1.0) < 1e-6
    assert abs(after_center["BoneB"] - 0.0) < 1e-6
    # 非変形ボーンのウェイトは保持される
    assert abs(after_center["NonDeform"] - 0.5) < 1e-6

    cleanup(obj, arm)


def test_locked_and_missing_armature():
    """背景: ロック VG と Armature 欠落は仕様どおり触らない／即エラー。
    なぜ: フォールバック無しの契約を固定する。
    """
    obj, arm = make_skinned_strip("Weight Isolate Lock")
    obj.vertex_groups["BoneB"].lock_weight = True
    enter_weight_paint_vertex_select(obj, {1})
    obj.vertex_groups.active_index = obj.vertex_groups["BoneA"].index

    # BoneB (0.4) がロックされている場合、BoneA には残りの 0.6 が割り当てられる
    assert bpy.ops.weight_isolate.isolate() == {"FINISHED"}
    after = read_weights(obj, 1)
    assert abs(after["BoneB"] - 0.4) < 1e-6
    assert abs(after["BoneA"] - 0.6) < 1e-6

    cleanup(obj, arm)


def main():
    options = parse_args()
    temp_dir = Path(tempfile.mkdtemp(prefix="blender-weight-isolate-smoke-"))
    extract_zip(Path(options.zip).resolve(), temp_dir)
    sys.path.insert(0, str(temp_dir))

    addon = importlib.import_module("weight_isolate")
    addon.register()
    host_state = bpy.app.driver_namespace["blender_addon_tools.embedded_host.v1"]
    assert "weight_isolate" in host_state["tools"]
    assert "weight_utility" in host_state["groups"]
    clear_factory_mesh()
    try:
        test_enable_vertex_select_then_isolate()
        test_locked_and_missing_armature()
    finally:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        addon.unregister()
    print("Isolate Weight functional smoke test passed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        raise SystemExit(1) from None
