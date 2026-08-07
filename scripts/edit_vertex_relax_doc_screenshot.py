"""ドキュメント用スクリーンショット: edit_vertex_relax。

背景: サイドバー Edit タブのツール UI が docs の主な説明対象。
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
    find_area,
    parse_shot_args,
    run_doc_shot,
    set_panel_category,
)


def _shot(output_dir: Path) -> list[Path]:
    options = parse_shot_args()
    enable_addon(Path(options.zip), "edit_vertex_relax")

    obj = create_edit_mesh("Edit Vertex Relax Doc")
    enter_edit_mode(obj)
    bpy.ops.mesh.select_all(action="SELECT")

    settings = bpy.context.scene.edit_vertex_relax
    settings.expanded = True

    area = find_area("VIEW_3D")
    ensure_region_ui(area)
    set_panel_category(area, "Edit")

    sidebar = capture_region(area, "UI", output_dir / "sidebar.png")
    return [sidebar]


if __name__ == "__main__":
    run_doc_shot(_shot)
