"""ドキュメント用スクリーンショットの共有ヘルパ。

SoftGL + Xvfb では Blender のスクショ演算子が空バッファになりやすい。
仮想ディスプレイ全体を ImageMagick `import` で撮り、領域で切り出す。
"""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import bpy
from zip_utils import extract_zip

RESULT_NAME = "doc_screenshot_result.txt"


class DocShotError(RuntimeError):
    """撮影シナリオ失敗。フォールバックせず即時中断する。"""


def parse_shot_args() -> argparse.Namespace:
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--package-id", required=True)
    return parser.parse_args(raw)


def require_window():
    window = bpy.context.window
    if window is None:
        raise DocShotError("Blender GUI window is not available (is Xvfb running?)")
    return window


def require_screen():
    screen = bpy.context.screen
    if screen is None:
        raise DocShotError("Blender screen is not available")
    return screen


def enable_addon(zip_path: Path, module_name: str) -> None:
    package_root = Path(tempfile.mkdtemp(prefix=f"doc-shot-{module_name}-"))
    extract_zip(zip_path.resolve(), package_root)
    sys.path.insert(0, str(package_root))
    importlib.import_module(module_name)
    result = bpy.ops.preferences.addon_enable(module=module_name)
    if result != {"FINISHED"}:
        raise DocShotError(f"{module_name} did not enable: {result}")


def find_area(space_type: str):
    screen = require_screen()
    area = next((candidate for candidate in screen.areas if candidate.type == space_type), None)
    if area is None:
        raise DocShotError(f"No area with type {space_type!r}")
    return area


def largest_area():
    screen = require_screen()
    return max(screen.areas, key=lambda area: area.width * area.height)


def set_area_type(area, space_type: str):
    if area.type != space_type:
        area.type = space_type
    if area.type != space_type:
        raise DocShotError(f"Could not switch area to {space_type!r} (got {area.type!r})")


def find_region(area, region_type: str):
    region = next((candidate for candidate in area.regions if candidate.type == region_type), None)
    if region is None or region.width <= 0 or region.height <= 0:
        raise DocShotError(
            f"Area {area.type} has no visible region {region_type!r}: "
            f"{getattr(region, 'width', None)}x{getattr(region, 'height', None)}"
        )
    return region


def ensure_region_ui(area) -> None:
    space = area.spaces.active
    if not hasattr(space, "show_region_ui"):
        raise DocShotError(f"{area.type} space has no show_region_ui")
    space.show_region_ui = True
    if not space.show_region_ui:
        raise DocShotError(f"Failed to show UI region for {area.type}")


def set_panel_category(area, category: str) -> None:
    """N パネル等のタブを切り替える。Blender 3.5+ の Region API を必須とする。"""
    region = find_region(area, "UI")
    if not hasattr(region, "active_panel_category"):
        raise DocShotError("Region.active_panel_category is required (Blender 3.5+)")
    region.active_panel_category = category
    if region.active_panel_category != category:
        raise DocShotError(
            f"Could not activate panel category {category!r} "
            f"(active={region.active_panel_category!r})"
        )


def redraw_area(area, region=None, iterations: int = 4) -> None:
    window = require_window()
    target_region = region
    if target_region is None:
        target_region = next(
            (candidate for candidate in area.regions if candidate.type == "WINDOW"),
            area.regions[0],
        )
    area.tag_redraw()
    with bpy.context.temp_override(window=window, area=area, region=target_region):
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=iterations)


def _capture_root_png() -> Path:
    display = os.environ.get("DISPLAY")
    if not display:
        raise DocShotError("DISPLAY is not set; doc screenshots require Xvfb")
    root_png = Path(tempfile.mkdtemp(prefix="doc-shot-root-")) / "root.png"
    completed = subprocess.run(
        ["import", "-window", "root", str(root_png)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not root_png.exists() or root_png.stat().st_size < 1000:
        raise DocShotError(
            "X11 root capture failed: "
            f"code={completed.returncode}, stderr={completed.stderr.strip()}, "
            f"size={root_png.stat().st_size if root_png.exists() else None}"
        )
    return root_png


def _root_image_size(root_png: Path) -> tuple[int, int]:
    completed = subprocess.run(
        ["identify", "-format", "%w %h", str(root_png)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise DocShotError(f"identify failed: {completed.stderr.strip()}")
    width_text, height_text = completed.stdout.strip().split()
    return int(width_text), int(height_text)


def crop_region_to_png(region, output_path: Path) -> Path:
    """Blender region（原点は左下）を X11 root PNG（原点は左上）から切り出す。"""
    root_png = _capture_root_png()
    full_w, full_h = _root_image_size(root_png)
    crop_x = max(0, min(region.x, full_w - 1))
    crop_w = max(1, min(region.width, full_w - crop_x))
    top = max(0, full_h - (region.y + region.height))
    crop_h = max(1, min(region.height, full_h - top))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    completed = subprocess.run(
        [
            "convert",
            str(root_png),
            "-crop",
            f"{crop_w}x{crop_h}+{crop_x}+{top}",
            "+repage",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not output_path.exists() or output_path.stat().st_size < 100:
        raise DocShotError(
            "Region crop failed: "
            f"code={completed.returncode}, stderr={completed.stderr.strip()}, "
            f"size={output_path.stat().st_size if output_path.exists() else None}"
        )
    return output_path


def capture_region(area, region_type: str, output_path: Path) -> Path:
    region = find_region(area, region_type)
    redraw_area(area, region)
    return crop_region_to_png(region, output_path)


def create_edit_mesh(name: str = "DocShot Mesh"):
    mesh = bpy.data.meshes.new(f"{name} Data")
    mesh.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def enter_edit_mode(obj) -> None:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    result = bpy.ops.object.mode_set(mode="EDIT")
    if result != {"FINISHED"}:
        raise DocShotError(f"Could not enter EDIT mode: {result}")


def write_result(output_dir: Path, status: str, message: str = "") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = status if not message else f"{status}\n{message}"
    (output_dir / RESULT_NAME).write_text(payload, encoding="utf-8")


def quit_blender() -> None:
    try:
        bpy.ops.wm.quit_blender()
    except Exception:
        pass


def run_doc_shot(shot: Callable[[Path], list[Path]]) -> None:
    """Blender --python エントリ。GUI 起動後に timer で撮影する。"""

    def _run() -> None:
        options = parse_shot_args()
        output_dir = options.output if options.output.is_absolute() else Path.cwd() / options.output
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            require_window()
            paths = shot(output_dir)
            if not paths:
                raise DocShotError("Shot produced no PNG paths")
            missing = [str(path) for path in paths if not path.exists() or path.stat().st_size < 100]
            if missing:
                raise DocShotError(f"Missing or empty screenshots: {', '.join(missing)}")
            write_result(
                output_dir,
                "PASS",
                f"package={options.package_id} files=" + ",".join(path.name for path in paths),
            )
            quit_blender()
        except Exception as exc:
            write_result(output_dir, "FAIL", f"{type(exc).__name__}: {exc}")
            quit_blender()

    # --python はイベントループ前に走る。ウィンドウ生成を待つ。
    bpy.app.timers.register(_run, first_interval=1.0)
