from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from zip_utils import extract_zip

LOG_PATH = Path(tempfile.gettempdir()) / "in_between_shape_key_ui_smoke.log"
ARTIFACTS = Path(tempfile.gettempdir()) / "in_between_shape_key_ui_artifacts"
RESULT_NAME = "in_between_shape_key_ui_result.txt"
_ACTIVE_ARTIFACTS: Path | None = None
_EVENT_QUEUE: list[Callable[[], None]] = []


def _log(message: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")
    print(message, flush=True)


def parse_args():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    return parser.parse_args(raw)


def _write_result(status: str, message: str = "") -> None:
    if _ACTIVE_ARTIFACTS is None:
        return
    _ACTIVE_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = status if not message else f"{status}\n{message}"
    (_ACTIVE_ARTIFACTS / RESULT_NAME).write_text(payload, encoding="utf-8")


def _fail(message: str) -> None:
    _log(f"FAIL: {message}")
    _write_result("FAIL", message)
    try:
        bpy.ops.wm.quit_blender()
    except Exception:
        pass


def _pass(message: str) -> None:
    _log(message)
    _write_result("PASS", message)
    bpy.ops.wm.quit_blender()


def _enable_addon(zip_path: Path) -> None:
    package_root = Path(tempfile.mkdtemp(prefix="blender-fbxi-ui-addon-"))
    extract_zip(zip_path.resolve(), package_root)
    sys.path.insert(0, str(package_root))
    importlib.import_module("in_between_shape_key")
    result = bpy.ops.preferences.addon_enable(module="in_between_shape_key")
    if result != {"FINISHED"}:
        raise RuntimeError(f"in_between_shape_key did not enable: {result}")


def _properties_area():
    screen = bpy.context.screen
    if screen is None:
        raise RuntimeError("Blender screen is not available")
    area = next((candidate for candidate in screen.areas if candidate.type == "PROPERTIES"), None)
    if area is None:
        raise RuntimeError("Blender startup screen has no Properties area")
    area.spaces.active.context = "DATA"
    return area


def _prepare_controller() -> tuple[bpy.types.Object, bpy.types.Key]:
    mesh = bpy.data.meshes.new("FBX In-Between UI Smoke Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new("FBX In-Between UI Smoke Object", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.shape_key_add(name="Basis")
    smile = obj.shape_key_add(name="Smile")
    smile.data[1].co.y = 1.0
    smile.value = 0.5
    obj.active_shape_key_index = mesh.shape_keys.key_blocks.find("Smile")
    if bpy.ops.fbx_shape_inbetween.convert_to_inbetween() != {"FINISHED"}:
        raise RuntimeError("Could not convert the UI smoke controller")
    source = obj.shape_key_add(name="Smile Mid")
    source.data[1].co.y = 0.5
    if bpy.ops.fbx_shape_inbetween.add_existing_key(
        controller_name="Smile",
        source_name="Smile Mid",
    ) != {"FINISHED"}:
        raise RuntimeError("Could not add the UI smoke existing Shape Key")
    return obj, mesh.shape_keys


def _click(window, x: int, y: int) -> None:
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
    window.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
    window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=x, y=y)


def _tap(window, key_type: str, *, ctrl: bool = False, shift: bool = False) -> None:
    window.event_simulate(type=key_type, value="PRESS", ctrl=ctrl, shift=shift)
    window.event_simulate(type=key_type, value="RELEASE", ctrl=ctrl, shift=shift)


def _queue_tap(window, key_type: str, *, shift: bool = False) -> None:
    _EVENT_QUEUE.append(lambda: _tap(window, key_type, shift=shift))


def _queue_type(window, text: str) -> None:
    for character in text:
        _EVENT_QUEUE.append(
            lambda ch=character: window.event_simulate(
                type="TEXTINPUT", value="PRESS", unicode=ch
            )
        )


def _pump_events(on_done: Callable[[], None], interval: float = 0.08):
    def step():
        try:
            if _EVENT_QUEUE:
                _EVENT_QUEUE.pop(0)()
                return interval
            on_done()
        except Exception as exc:
            _fail(f"{type(exc).__name__}: {exc}")
        return None

    bpy.app.timers.register(step, first_interval=interval)


def _capture_region_pixels(area):
    import os
    import subprocess
    import tempfile

    window = bpy.context.window
    if window is None:
        raise RuntimeError("Blender GUI window is not available")
    region = next((candidate for candidate in area.regions if candidate.type == "WINDOW"), None)
    if region is None or region.width <= 0 or region.height <= 0:
        raise RuntimeError(f"Properties WINDOW region has no visible pixels: {area.width}x{area.height}")
    area.tag_redraw()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=4)

    # SoftGL + screenshot operators often write empty buffers in Xvfb. Capture the
    # virtual display instead, then crop to the Properties WINDOW region.
    root_png = Path(tempfile.mkdtemp(prefix="fbxi-ui-root-")) / "root.png"
    display = os.environ.get("DISPLAY")
    if not display:
        raise RuntimeError("DISPLAY is not set; GUI smoke requires Xvfb")
    completed = subprocess.run(
        ["import", "-window", "root", str(root_png)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not root_png.exists() or root_png.stat().st_size < 1000:
        raise RuntimeError(
            "X11 root capture failed: "
            f"code={completed.returncode}, stderr={completed.stderr.strip()}, "
            f"size={root_png.stat().st_size if root_png.exists() else None}"
        )

    image = bpy.data.images.load(str(root_png), check_existing=False)
    full_w, full_h = image.size
    # Blender region y is bottom-up; ImageMagick/PNG y is top-down.
    crop_x = max(0, min(region.x, full_w - 1))
    crop_w = max(1, min(region.width, full_w - crop_x))
    top = max(0, full_h - (region.y + region.height))
    crop_h = max(1, min(region.height, full_h - top))
    flat_full = list(image.pixels[:])
    bpy.data.images.remove(image)

    cropped: list[float] = []
    for row in range(crop_h):
        # image.pixels are bottom-up as well in Blender.
        src_y = full_h - (top + crop_h) + row
        start = (src_y * full_w + crop_x) * 4
        end = start + crop_w * 4
        cropped.extend(flat_full[start:end])
    if not cropped:
        raise RuntimeError("Cropped Properties capture was empty")
    return cropped, crop_w, crop_h


def _write_png(path: Path, flat_pixels: list[float], width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = bpy.data.images.new(path.stem, width=width, height=height, alpha=True)
    image.pixels = flat_pixels
    image.filepath_raw = path.resolve().as_posix()
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def _pixel_difference(before, after) -> tuple[int, float]:
    if len(before) != len(after):
        raise RuntimeError("UI screenshots have different Properties area sizes")
    changed = 0
    difference = 0.0
    for first, second in zip(before, after, strict=True):
        delta = abs(first - second)
        difference += delta
        if delta > 0.01:
            changed += 1
    return changed, difference


def _count_probe_pixels(before, after) -> int:
    # Alert rows lean red; count pixels that became distinctly more red after probe.
    probe = 0
    for index in range(0, len(before), 4):
        br, _bg, _bb = before[index], before[index + 1], before[index + 2]
        ar, ag, ab = after[index], after[index + 1], after[index + 2]
        if ar - br > 0.15 and ar > ag + 0.1 and ar > ab + 0.1:
            probe += 1
    return probe


def _start(artifacts: Path, zip_path: Path) -> None:
    _log("Starting Blender UI smoke test under virtual display")
    window = bpy.context.window
    if window is None:
        raise RuntimeError("Blender GUI window is not available (is Xvfb running?)")

    _enable_addon(zip_path)
    obj, key = _prepare_controller()
    _log("Addon enabled and controller prepared")

    area = _properties_area()
    region = next((candidate for candidate in area.regions if candidate.type == "WINDOW"), None)
    if region is None:
        raise RuntimeError("Properties WINDOW region is unavailable")

    if key.key_blocks.get("Smile@0.5") is None or key.key_blocks.get("Smile@1") is None:
        raise RuntimeError(
            "UI smoke setup did not create in-between keys: "
            + ", ".join(block.name for block in key.key_blocks)
        )
    _log("Existing Shape Key interaction created Smile@0.5 and Smile@1")
    from in_between_shape_key.ui_state import find_entry

    endpoint = find_entry(bpy.context.window_manager, obj, "Smile@1")
    if endpoint is None:
        raise RuntimeError("UI smoke could not resolve the @1 position row")
    for position in (0.95, 0.925, 0.901):
        endpoint.position = position
    if key.key_blocks.get("Smile@1") is None:
        raise RuntimeError("Position drag updates were applied before debounce completion")

    def verify_debounced_position():
        if key.key_blocks.get("Smile@0.901") is None:
            _fail("Debounced position update did not create Smile@0.901")
            return
        _log("Position drag updates were consolidated at 0.901")
        _continue_after_interaction(artifacts, window, obj, key, area, region)

    bpy.app.timers.register(verify_debounced_position, first_interval=0.3)


def _continue_after_interaction(artifacts, window, obj, key, area, region) -> None:
    with bpy.context.temp_override(window=window, area=area, region=region):
        for _ in range(24):
            bpy.ops.view2d.scroll_down(deltay=20)
    click_x = area.x + max(40, area.width // 4)
    click_y = area.y + max(40, area.height // 5)
    _click(window, click_x, click_y)
    _log(f"Simulated Properties click at ({click_x}, {click_y})")

    obj.active_shape_key_index = key.key_blocks.find("Smile@0.5")
    area = _properties_area()
    region = next((candidate for candidate in area.regions if candidate.type == "WINDOW"), None)
    if region is None:
        raise RuntimeError("Properties WINDOW region is unavailable")
    from in_between_shape_key.ui import FBXI_PT_shape_key_inbetween, draw_shape_key_inbetween

    # Remove every add-on draw path so the baseline is Shape Keys UI without our panel.
    try:
        bpy.types.DATA_PT_shape_keys.remove(draw_shape_key_inbetween)
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(FBXI_PT_shape_key_inbetween)
    except Exception:
        pass
    bpy.context.scene["_fbxi_ui_pixel_probe"] = False
    for screen_area in bpy.context.screen.areas:
        screen_area.tag_redraw()
    before_path = artifacts / "in_between_shape_key_before.png"
    after_path = artifacts / "in_between_shape_key_after.png"
    _log(f"Capturing baseline UI pixels: {before_path}")
    before_pixels, width, height = _capture_region_pixels(area)
    _write_png(before_path, before_pixels, width, height)

    def capture_addon_ui():
        try:
            bpy.utils.register_class(FBXI_PT_shape_key_inbetween)
            bpy.types.DATA_PT_shape_keys.append(draw_shape_key_inbetween)
            bpy.context.scene["_fbxi_ui_pixel_probe"] = True
            with bpy.context.temp_override(window=window, area=area, region=region):
                for _ in range(4):
                    bpy.ops.view2d.scroll_up(deltay=40)
            for screen_area in bpy.context.screen.areas:
                screen_area.tag_redraw()
            _log(f"Capturing add-on UI pixels: {after_path}")
            after_pixels, after_width, after_height = _capture_region_pixels(area)
            if (after_width, after_height) != (width, height):
                raise RuntimeError(
                    f"Capture size changed: {(width, height)} -> {(after_width, after_height)}"
                )
            _write_png(after_path, after_pixels, after_width, after_height)
            changed, difference = _pixel_difference(before_pixels, after_pixels)
            probe_pixels = _count_probe_pixels(before_pixels, after_pixels)
            if changed < 100 or difference < 10.0:
                raise RuntimeError(
                    "Shape Key UI did not produce a visible pixel change: "
                    f"changed_pixels={changed}, difference={difference}, "
                    f"probe_pixels={probe_pixels}, area={area.width}x{area.height}, "
                    f"before_bytes={before_path.stat().st_size}, after_bytes={after_path.stat().st_size}"
                )
            bpy.data.objects.remove(obj, do_unlink=True)
            result = bpy.ops.preferences.addon_disable(module="in_between_shape_key")
            if result != {"FINISHED"}:
                raise RuntimeError(f"in_between_shape_key did not disable: {result}")
            _pass(
                "Shape Key UI smoke test passed: "
                f"changed_pixels={changed}, difference={difference:.2f}, "
                f"probe_pixels={probe_pixels}, area={area.width}x{area.height}"
            )
        except Exception as exc:
            _fail(f"{type(exc).__name__}: {exc}")

    bpy.app.timers.register(capture_addon_ui, first_interval=0.5)


def _run_visual_and_interaction_test():
    global _ACTIVE_ARTIFACTS
    options = parse_args()
    artifacts = options.artifacts if options.artifacts.is_absolute() else Path.cwd() / options.artifacts
    artifacts.mkdir(parents=True, exist_ok=True)
    _ACTIVE_ARTIFACTS = artifacts
    LOG_PATH.write_text("", encoding="utf-8")
    try:
        _start(artifacts, Path(options.zip))
    except Exception as exc:
        _fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    # --python runs before the GUI event loop; defer until a live window exists.
    bpy.app.timers.register(_run_visual_and_interaction_test, first_interval=1.0)
