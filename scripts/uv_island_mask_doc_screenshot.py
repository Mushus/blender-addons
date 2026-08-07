"""ドキュメント用スクリーンショット: uv_island_mask。

背景: UV Editor サイドバー Edit タブのツール UI が docs の主な説明対象。
なぜ: Docker / Xvfb 上で UI 領域を固定条件で撮り、手動スクショ依存を減らす。
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_screenshot_lib import (
    capture_region,
    create_edit_mesh,
    enable_addon,
    ensure_region_ui,
    enter_edit_mode,
    largest_area,
    parse_shot_args,
    run_doc_shot,
    set_area_type,
    set_panel_category,
)


def _prepare_uv_editor():
    obj = create_edit_mesh("UV Island Mask Doc")
    enter_edit_mode(obj)
    bpy.ops.mesh.select_all(action="SELECT")
    result = bpy.ops.uv.unwrap(method="ANGLE_BASED")
    if result != {"FINISHED"}:
        raise RuntimeError(f"uv.unwrap failed: {result}")

    area = largest_area()
    set_area_type(area, "IMAGE_EDITOR")
    space = area.spaces.active
    # Blender 5.x: UV は mode 側。ui_mode は VIEW/PAINT/MASK のみ。
    if hasattr(space, "mode"):
        space.mode = "UV"
    elif hasattr(space, "ui_mode"):
        space.ui_mode = "UV"
    else:
        raise RuntimeError("IMAGE_EDITOR space has neither mode nor ui_mode")
    current = getattr(space, "mode", getattr(space, "ui_mode", None))
    if current != "UV":
        raise RuntimeError(f"Could not enter UV editor mode (got {current!r})")
    ensure_region_ui(area)
    set_panel_category(area, "Edit")
    return area


def _shot(output_dir: Path) -> list[Path]:
    options = parse_shot_args()
    enable_addon(Path(options.zip), "uv_island_mask")

    settings = bpy.context.scene.uv_island_mask
    settings.expanded = True

    area = _prepare_uv_editor()
    sidebar = capture_region(area, "UI", output_dir / "sidebar.png")
    return [sidebar]


if __name__ == "__main__":
    run_doc_shot(_shot)
