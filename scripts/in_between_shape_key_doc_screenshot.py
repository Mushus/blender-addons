"""ドキュメント用スクリーンショット: in_between_shape_key。

背景: Properties > Object Data > Shape Keys 上のパネルが docs の主な説明対象。
なぜ: Docker / Xvfb 上で Properties 領域を固定条件で撮り、手動スクショ依存を減らす。
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
    find_area,
    parse_shot_args,
    redraw_area,
    run_doc_shot,
)


def _prepare_shape_keys():
    obj = create_edit_mesh("In-Between Shape Key Doc")
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.shape_key_add(name="Basis")
    smile = obj.shape_key_add(name="Smile")
    smile.data[1].co.y = 1.0
    smile.value = 0.5
    obj.active_shape_key_index = obj.data.shape_keys.key_blocks.find("Smile")
    return obj


def _properties_data_area():
    area = find_area("PROPERTIES")
    area.spaces.active.context = "DATA"
    redraw_area(area)
    return area


def _shot(output_dir: Path) -> list[Path]:
    options = parse_shot_args()
    enable_addon(Path(options.zip), "in_between_shape_key")
    _prepare_shape_keys()
    area = _properties_data_area()
    properties = capture_region(area, "WINDOW", output_dir / "properties.png")
    return [properties]


if __name__ == "__main__":
    run_doc_shot(_shot)
