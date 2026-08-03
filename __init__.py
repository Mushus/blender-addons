bl_info = {
    "name": "Blender Add-on Tools Suite",
    "author": "Your Name",
    "version": (2026, 8, 4),
    "blender": (4, 0, 0),
    "location": "UV Editor > Sidebar > Edit",
    "description": "Stable, independently installable Blender tools.",
    "category": "3D View",
}

import sys
from importlib import import_module, reload

_CHILDREN = ("uv_island_mask",)
_modules = []


def register():
    global _modules
    _modules = []
    for name in _CHILDREN:
        module_name = f"{__package__}.addons.{name}"
        module = sys.modules.get(module_name)
        if module is not None:
            module = reload(module)
        else:
            module = import_module(module_name)
        _modules.append(module)
    for module in _modules:
        module.register()


def unregister():
    try:
        for module in reversed(_modules):
            module.unregister()
    finally:
        _modules.clear()
