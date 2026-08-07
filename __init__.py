bl_info = {
    "name": "Blender Add-on Tools Suite",
    "author": "Mushus",
    "version": (2026, 8, 7),
    "blender": (5, 1, 0),
    "location": "UV Editor > Sidebar > Edit; 3D View > Sidebar > Edit",
    "description": "UV Island Mask and Slide Relax.",
    "category": "3D View",
}

import sys
from importlib import import_module, reload

import bpy

_CHILDREN = ("uv_island_mask", "slide_relax")
_RUNTIME_KEY = "blender_addon_suite.runtime.v1"


def _runtime_state() -> dict | None:
    return bpy.app.driver_namespace.get(_RUNTIME_KEY)


def _set_modules(modules: list) -> None:
    bpy.app.driver_namespace[_RUNTIME_KEY] = {"modules": modules}


def _clear_runtime() -> None:
    bpy.app.driver_namespace.pop(_RUNTIME_KEY, None)


def register():
    unregister()
    modules = []
    for name in _CHILDREN:
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
