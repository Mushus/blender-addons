from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zip_utils import extract_zip

HOST_KEY = "blender_addon_tools.embedded_host.v1"


def args():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--module", required=True)
    return parser.parse_args(raw)


def _runtime_key(module_name: str) -> str:
    return f"{module_name}.runtime.v1"


def _module_root(module_name: str) -> Path:
    module = sys.modules.get(module_name) or importlib.import_module(module_name)
    file_path = getattr(module, "__file__", None)
    if not file_path:
        raise AssertionError(f"{module_name} has no __file__")
    return Path(file_path).resolve().parent


def _load_suite_children(module_name: str) -> list[str]:
    catalog_path = _module_root(module_name) / "packages.json"
    if not catalog_path.is_file():
        return []
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if catalog.get("suite_id") != module_name:
        return []
    return [package["id"] for package in catalog["packages"] if package.get("status") == "stable"]


def _state_for(module_name: str) -> dict:
    return dict(getattr(bpy.app, "driver_namespace", {}).get(_runtime_key(module_name)) or {})


def _snapshot_markers(module_name: str, child_ids: list[str]) -> dict:
    """Capture RNA markers from durable state while the add-on is enabled."""
    class_names: set[str] = set()
    scene_props: set[str] = set()
    object_props: set[str] = set()

    for name in (module_name, *child_ids):
        state = _state_for(name)
        for cls in state.get("classes") or []:
            class_name = getattr(cls, "__name__", None)
            if class_name:
                class_names.add(class_name)
        export_class = state.get("export_class")
        export_name = getattr(export_class, "__name__", None) if export_class is not None else None
        if export_name:
            class_names.add(export_name)
        scene_prop = state.get("scene_prop")
        if scene_prop:
            scene_props.add(str(scene_prop))
        for prop in state.get("object_props") or []:
            object_props.add(str(prop))
        # Convention used by several tools: Scene.<module_id>
        if hasattr(bpy.types.Scene, name):
            scene_props.add(name)

    return {
        "class_names": class_names,
        "scene_props": scene_props,
        "object_props": object_props,
        "child_ids": list(child_ids),
    }


def _assert_clean(module_name: str, baseline_handlers: dict[str, int], markers: dict) -> None:
    dns = getattr(bpy.app, "driver_namespace", {})
    runtime_key = _runtime_key(module_name)
    if runtime_key in dns:
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

    for child_id in markers["child_ids"]:
        child_key = _runtime_key(child_id)
        if child_key in dns:
            raise AssertionError(f"Child runtime key still present: {child_key}")

    for class_name in sorted(markers["class_names"]):
        if hasattr(bpy.types, class_name):
            raise AssertionError(f"{class_name} still registered")

    for prop in sorted(markers["scene_props"]):
        if hasattr(bpy.types.Scene, prop):
            raise AssertionError(f"Scene.{prop} still registered")

    for prop in sorted(markers["object_props"]):
        if hasattr(bpy.types.Object, prop):
            raise AssertionError(f"Object.{prop} still registered")


def _assert_enabled(module_name: str, child_ids: list[str]) -> None:
    dns = getattr(bpy.app, "driver_namespace", {})
    if _runtime_key(module_name) not in dns:
        raise AssertionError(f"{module_name} runtime key missing after enable")
    for child_id in child_ids:
        if _runtime_key(child_id) not in dns:
            raise AssertionError(f"Suite did not register child runtime: {child_id}")


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
    child_ids = _load_suite_children(options.module)

    # Normal enable/disable cycle with reload between disables.
    for _ in range(2):
        _enable(options.module)
        module = importlib.import_module(options.module)
        if not getattr(module, "bl_info", None):
            raise AssertionError(f"{options.module} did not load")
        _assert_enabled(options.module, child_ids)
        markers = _snapshot_markers(options.module, child_ids)
        _disable(options.module)
        _assert_clean(options.module, baseline_handlers, markers)
        module = importlib.reload(module)

    # Reload while enabled must not leave durable leftovers or block re-enable.
    _enable(options.module)
    markers = _snapshot_markers(options.module, child_ids)
    module = importlib.reload(importlib.import_module(options.module))
    _disable(options.module)
    _assert_clean(options.module, baseline_handlers, markers)
    _enable(options.module)
    module = importlib.import_module(options.module)
    markers = _snapshot_markers(options.module, child_ids)
    # Idempotent register while enabled.
    module.register()
    module.register()
    _disable(options.module)
    _assert_clean(options.module, baseline_handlers, markers)

    print(f"Smoke test passed: {options.module}")


if __name__ == "__main__":
    main()
