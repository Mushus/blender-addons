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

from . import i18n
from .embedded_host import ToolSpec, register_tool, unregister_tool
from .operator import UVIM_OT_bake_mask
from .properties import UVIM_Settings
from .ui import draw_tool, tool_poll

classes = (UVIM_Settings, UVIM_OT_bake_mask)
_tool_id = "uv_island_mask"


def _reload_child_modules():
    """Reload implementation modules after Blender reinstalls this add-on."""
    module_names = (
        f"{__package__}.embedded_host.registry",
        f"{__package__}.embedded_host.ui",
        f"{__package__}.embedded_host",
        f"{__package__}.context",
        f"{__package__}.selection",
        f"{__package__}.properties",
        f"{__package__}.mask",
        f"{__package__}.i18n",
        f"{__package__}.operator",
        f"{__package__}.ui",
    )
    for module_name in module_names:
        module = sys.modules.get(module_name)
        if module is not None:
            reload(module)

    host = import_module(f"{__package__}.embedded_host")
    operator_module = import_module(f"{__package__}.operator")
    properties_module = import_module(f"{__package__}.properties")
    ui_module = import_module(f"{__package__}.ui")
    global ToolSpec, register_tool, unregister_tool, UVIM_OT_bake_mask, UVIM_Settings, draw_tool, tool_poll, i18n, classes
    ToolSpec = host.ToolSpec
    register_tool = host.register_tool
    unregister_tool = host.unregister_tool
    UVIM_OT_bake_mask = operator_module.UVIM_OT_bake_mask
    UVIM_Settings = properties_module.UVIM_Settings
    draw_tool = ui_module.draw_tool
    tool_poll = ui_module.tool_poll
    i18n = import_module(f"{__package__}.i18n")
    classes = (UVIM_Settings, UVIM_OT_bake_mask)


def register():
    _reload_child_modules()
    i18n.register()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.uv_island_mask = bpy.props.PointerProperty(type=UVIM_Settings)
    register_tool(
        ToolSpec(
            tool_id=_tool_id,
            owner_id=__package__,
            display_name="UV Island Mask",
            group_id="uv_utility",
            group_label="UV Utility",
            sort_order=100,
            space_type="IMAGE_EDITOR",
            region_type="UI",
            category="Edit",
            poll=tool_poll,
            draw=draw_tool,
        )
    )


def unregister():
    try:
        unregister_tool(_tool_id, __package__)
    finally:
        if hasattr(bpy.types.Scene, "uv_island_mask"):
            del bpy.types.Scene.uv_island_mask
        for cls in reversed(classes):
            try:
                bpy.utils.unregister_class(cls)
            except RuntimeError:
                pass
        try:
            i18n.unregister()
        except RuntimeError:
            pass
