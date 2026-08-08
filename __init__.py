bl_info = {
    "name": "Blender Add-on Tools Suite",
    "author": "Mushus",
    "version": (2026, 8, 8),
    "blender": (5, 1, 0),
    "location": "UV Editor > Sidebar > Edit; 3D View > Sidebar > Edit",
    "description": "UV Island Mask, Slide Relax, Smooth Weight.",
    "category": "3D View",
}

import json
import sys
from importlib import import_module, reload
from pathlib import Path

import bpy

_RUNTIME_KEY = "blender_addon_suite.runtime.v1"


def _load_children() -> tuple[str, ...]:
    """Stable package ids from packages.json (suite zip) or release/packages.json (repo)."""
    root = Path(__file__).resolve().parent
    candidates = (root / "packages.json", root / "release" / "packages.json")
    for path in candidates:
        if not path.is_file():
            continue
        catalog = json.loads(path.read_text(encoding="utf-8"))
        children = tuple(
            package["id"]
            for package in catalog["packages"]
            if package.get("status") == "stable"
        )
        if not children:
            raise RuntimeError(f"No stable packages in {path}")
        return children
    raise RuntimeError(
        "packages.json not found next to suite __init__.py or under release/"
    )


def _runtime_state() -> dict | None:
    return bpy.app.driver_namespace.get(_RUNTIME_KEY)


def _set_modules(modules: list) -> None:
    bpy.app.driver_namespace[_RUNTIME_KEY] = {"modules": modules}


def _clear_runtime() -> None:
    bpy.app.driver_namespace.pop(_RUNTIME_KEY, None)


def register():
    unregister()
    modules = []
    for name in _load_children():
        module_name = f"{__package__}.addons.{name}"
        module = sys.modules.get(module_name)
        if module is not None:
            module = reload(module)
        else:
            module = import_module(module_name)
        modules.append(module)
    _set_modules(modules)
    for module in modules:
        module.register()


def unregister():
    state = _runtime_state()
    modules = list((state or {}).get("modules") or [])
    try:
        for module in reversed(modules):
            try:
                module.unregister()
            except Exception:
                pass
    finally:
        _clear_runtime()
