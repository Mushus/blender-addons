"""ドキュメント用スクリーンショット: weight_smooth。

背景: Weight Paint サイドバー Edit タブのツール UI が docs の主な説明対象。
なぜ: Docker / Xvfb 上で UI 領域を固定条件で撮り、手動スクショ依存を減らす。
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from doc_screenshot_lib import (
    DocShotError,
    capture_region,
    enable_addon,
    ensure_region_ui,
    find_area,
    parse_shot_args,
    run_doc_shot,
    set_panel_category,
)


def _clear_factory_mesh() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def _make_skinned_strip(name: str):
    """Weight Paint でパネルが活性になるよう、Armature + 変形 VG を用意する。"""
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
    obj.vertex_groups["BoneA"].add([0, 1], 1.0, "REPLACE")
    obj.vertex_groups["BoneB"].add([2], 1.0, "REPLACE")
    return obj


def _enter_weight_paint(obj) -> None:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    result = bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    if result != {"FINISHED"}:
        raise DocShotError(f"Could not enter WEIGHT_PAINT: {result}")
    if bpy.context.mode != "PAINT_WEIGHT":
        raise DocShotError(f"Expected PAINT_WEIGHT, got {bpy.context.mode!r}")


def _shot(output_dir: Path) -> list[Path]:
    options = parse_shot_args()
    enable_addon(Path(options.zip), "weight_smooth")

    _clear_factory_mesh()
    obj = _make_skinned_strip("Smooth Weight Doc")
    _enter_weight_paint(obj)

    settings = bpy.context.scene.weight_smooth
    settings.expanded = True

    area = find_area("VIEW_3D")
    ensure_region_ui(area)
    set_panel_category(area, "Edit")

    sidebar = capture_region(area, "UI", output_dir / "sidebar.png")
    return [sidebar]


if __name__ == "__main__":
    run_doc_shot(_shot)
