bl_info = {
    "name": "UV Island Mask",
    "author": "Mushus",
    "version": (2026, 8, 4),
    "blender": (4, 0, 0),
    "location": "UV Editor > Sidebar > Edit",
    "description": "Bake a mask image from selected UV faces.",
    "category": "UV",
}

import sys
from importlib import import_module, reload
from pathlib import Path

# Repo checkout: addons/<tool> → parents[2] is the monorepo root (scaffold lives there).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if (_REPO_ROOT / "scaffold" / "embedded_host").is_dir():
    _root = str(_REPO_ROOT)
    if _root not in sys.path:
        sys.path.insert(0, _root)

import bpy

_tool_id = "uv_island_mask"
# scaffold.* は make_zip 時に embedded_host.* へ書き換えられ、_qualname 経由で __package__ 配下になる。
_CHILD_MODULES = (
    "runtime",
    "scaffold.embedded_host.registry",
    "scaffold.embedded_host.ui",
    "scaffold.embedded_host",
    "context",
    "selection",
    "properties",
    "mask",
    "i18n",
    "operator",
    "ui",
)


def _qualname(module_name: str) -> str:
    if module_name.startswith("scaffold."):
        return module_name
    return f"{__package__}.{module_name}"


def _reload_child_modules():
    """Reload implementation modules after durable cleanup."""
    for module_name in _CHILD_MODULES:
        module = sys.modules.get(_qualname(module_name))
        if module is not None:
            reload(module)


def _bindings():
    host = import_module(_qualname("scaffold.embedded_host"))
    operator_module = import_module(_qualname("operator"))
    properties_module = import_module(_qualname("properties"))
    ui_module = import_module(_qualname("ui"))
    i18n_module = import_module(_qualname("i18n"))
    return host, operator_module, properties_module, ui_module, i18n_module


def register():
    runtime_mod = import_module(_qualname("runtime"))
    runtime_mod.uninstall()
    _reload_child_modules()
    runtime_mod = import_module(_qualname("runtime"))

    host, operator_module, properties_module, ui_module, i18n_module = _bindings()
    classes = (properties_module.UVIM_Settings, operator_module.UVIM_OT_bake_mask)

    state = runtime_mod.begin_state()
    i18n_module.register()
    state["i18n_unregister"] = i18n_module.unregister

    for cls in classes:
        bpy.utils.register_class(cls)
        state["classes"].append(cls)

    bpy.types.Scene.uv_island_mask = bpy.props.PointerProperty(type=properties_module.UVIM_Settings)
    state["scene_prop"] = "uv_island_mask"
    state["tool_id"] = _tool_id
    state["owner_id"] = __package__
    state["unregister_tool"] = host.unregister_tool

    host.register_tool(
        host.ToolSpec(
            tool_id=_tool_id,
            owner_id=__package__,
            display_name="UV Island Mask",
            group_id="uv_utility",
            group_label="UV Utility",
            sort_order=100,
            space_type="IMAGE_EDITOR",
            region_type="UI",
            category="Edit",
            poll=ui_module.tool_poll,
            draw=ui_module.draw_tool,
        )
    )


def unregister():
    runtime_mod = sys.modules.get(_qualname("runtime"))
    if runtime_mod is None:
        runtime_mod = import_module(_qualname("runtime"))
    runtime_mod.uninstall()
