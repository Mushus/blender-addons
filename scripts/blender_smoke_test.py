from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zip_utils import extract_zip

RUNTIME_KEYS = {
    "uv_island_mask": "uv_island_mask.runtime.v1",
    "in_between_shape_key": "in_between_shape_key.runtime.v1",
    "slide_relax": "slide_relax.runtime.v1",
    "blender_addon_suite": "blender_addon_suite.runtime.v1",
}
HOST_KEY = "blender_addon_tools.embedded_host.v1"
def args():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--module", required=True)
    return parser.parse_args(raw)


def _assert_clean(module_name: str, baseline_handlers: dict[str, int]) -> None:
    dns = getattr(bpy.app, "driver_namespace", {})
    runtime_key = RUNTIME_KEYS.get(module_name)
    if runtime_key and runtime_key in dns:
        raise AssertionError(f"Runtime key still present: {runtime_key}")
    if HOST_KEY in dns:
        raise AssertionError("Embedded host state was not cleaned up")

    depsgraph_count = len(bpy.app.handlers.depsgraph_update_pre)
    frame_count = len(bpy.app.handlers.frame_change_post)
    if depsgraph_count != baseline_handlers["depsgraph"]:
        raise AssertionError(
            f"depsgraph handlers leaked: {depsgraph_count} != {baseline_handlers['depsgraph']}"
        )
    if frame_count != baseline_handlers["frame"]:
        raise AssertionError(
            f"frame handlers leaked: {frame_count} != {baseline_handlers['frame']}"
        )

    if module_name == "in_between_shape_key":
        if hasattr(bpy.types, "FBXI_PT_shape_key_inbetween"):
            raise AssertionError("In Between Shape Key panel still registered")
    elif module_name == "uv_island_mask":
        if hasattr(bpy.types.Scene, "uv_island_mask"):
            raise AssertionError("Scene.uv_island_mask still registered")
    elif module_name == "slide_relax":
        if hasattr(bpy.types.Scene, "slide_relax"):
            raise AssertionError("Scene.slide_relax still registered")
    elif module_name == "blender_addon_suite":
        if hasattr(bpy.types.Scene, "slide_relax"):
            raise AssertionError("Slide Relax property leaked from suite")
        if hasattr(bpy.types, "FBXI_PT_shape_key_inbetween"):
            raise AssertionError("In Between Shape Key panel leaked from suite")


def _enable(module_name: str) -> None:
    result = bpy.ops.preferences.addon_enable(module=module_name)
    if result != {"FINISHED"}:
        raise AssertionError(f"{module_name} did not enable: {result}")


def _disable(module_name: str) -> None:
    result = bpy.ops.preferences.addon_disable(module=module_name)
    if result != {"FINISHED"}:
        raise AssertionError(f"{module_name} did not disable: {result}")


def main():
    options = args()
    zip_path = Path(options.zip).resolve()
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="blender-addon-smoke-"))
    extract_zip(zip_path, temp_dir)
    sys.path.insert(0, str(temp_dir))

    baseline_handlers = {
        "depsgraph": len(bpy.app.handlers.depsgraph_update_pre),
        "frame": len(bpy.app.handlers.frame_change_post),
    }

    module = importlib.import_module(options.module)

    # Normal enable/disable cycle with reload between disables.
    for _ in range(2):
        _enable(options.module)
        module = importlib.import_module(options.module)
        if not getattr(module, "bl_info", None):
            raise AssertionError(f"{options.module} did not load")
        if options.module == "blender_addon_suite":
            if not hasattr(bpy.types, "FBXI_PT_shape_key_inbetween"):
                raise AssertionError("Suite did not register In Between Shape Key")
            if not bpy.types.MESH_MT_shape_key_context_menu.is_extended():
                raise AssertionError("Suite did not extend the Shape Key context menu")
        _disable(options.module)
        _assert_clean(options.module, baseline_handlers)
        module = importlib.reload(module)

    # Reload while enabled must not leave durable leftovers or block re-enable.
    _enable(options.module)
    module = importlib.reload(importlib.import_module(options.module))
    _disable(options.module)
    _assert_clean(options.module, baseline_handlers)
    _enable(options.module)
    module = importlib.import_module(options.module)
    # Idempotent register while enabled.
    module.register()
    module.register()
    _disable(options.module)
    _assert_clean(options.module, baseline_handlers)

    print(f"Smoke test passed: {options.module}")


if __name__ == "__main__":
    main()
