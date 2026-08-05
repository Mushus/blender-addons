bl_info = {
    "name": "UV Island Mask",
    "author": "Your Name",
    "version": (2026, 8, 4),
    "blender": (4, 0, 0),
    "location": "UV Editor > Sidebar > Edit",
    "description": "Bake a mask image from selected UV faces.",
    "category": "UV",
}

import sys
from importlib import import_module, reload

import bpy

_tool_id = "uv_island_mask"
_CHILD_MODULES = (
    "runtime",
    "embedded_host.registry",
    "embedded_host.ui",
    "embedded_host",
    "context",
    "selection",
    "properties",
    "mask",
    "i18n",
    "operator",
    "ui",
)


def _reload_child_modules():
    """Reload implementation modules after durable cleanup."""
    for module_name in _CHILD_MODULES:
        full_name = f"{__package__}.{module_name}"
        module = sys.modules.get(full_name)
        if module is not None:
            reload(module)


def _bindings():
    host = import_module(f"{__package__}.embedded_host")
    operator_module = import_module(f"{__package__}.operator")
    properties_module = import_module(f"{__package__}.properties")
    ui_module = import_module(f"{__package__}.ui")
    i18n_module = import_module(f"{__package__}.i18n")
    return host, operator_module, properties_module, ui_module, i18n_module


def register():
    runtime_mod = import_module(f"{__package__}.runtime")
    runtime_mod.uninstall()
    _reload_child_modules()
    runtime_mod = import_module(f"{__package__}.runtime")

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
    runtime_mod = sys.modules.get(f"{__package__}.runtime")
    if runtime_mod is None:
        runtime_mod = import_module(f"{__package__}.runtime")
    runtime_mod.uninstall()
