from __future__ import annotations

import importlib
import sys

import bpy

from . import runtime

bl_info = {
    "name": "In Between Shape Key",
    "author": "Mushus",
    "version": (2026, 8, 6),
    "blender": (5, 1, 0),
    "location": "Properties > Data > Shape Keys; File > Export > FBX (.fbx)",
    "description": "Export Name@Weight Shape Keys as FBX in-between blend shapes.",
    "category": "Import-Export",
}

_CHILD_MODULES = (
    "runtime",
    "metadata",
    "fbx_binary",
    "postprocess",
    "validation",
    "sync",
    "exporter",
    "operator",
    "ui",
)

_dirty = False
_sync_guard = False
_export_class = None


def _reload_children():
    """Reload implementation modules after cleanup so upgrades use new code."""
    for module_name in _CHILD_MODULES:
        full_name = f"{__package__}.{module_name}"
        module = sys.modules.get(full_name)
        if module is not None:
            importlib.reload(module)


def _bindings():
    operator = importlib.import_module(f"{__package__}.operator")
    ui = importlib.import_module(f"{__package__}.ui")
    sync = importlib.import_module(f"{__package__}.sync")
    return operator, ui, sync


def _mark_dirty(*_args):
    global _dirty
    if not _sync_guard:
        _dirty = True


def _sync_handler(_scene, _depsgraph):
    global _dirty, _sync_guard
    if _sync_guard:
        return
    _dirty = False
    _sync_guard = True
    try:
        sync = importlib.import_module(f"{__package__}.sync")
        sync.sync_all(bpy.data)
    finally:
        _sync_guard = False


def _frame_change_handler(_scene):
    global _sync_guard
    if _sync_guard:
        return
    _sync_guard = True
    try:
        sync = importlib.import_module(f"{__package__}.sync")
        sync.sync_all(bpy.data)
    finally:
        _sync_guard = False
    bpy.context.view_layer.update()


def _menu_func_export(self, _context):
    export_class = _export_class
    state = runtime.get_state()
    if state is not None and state.get("export_class") is not None:
        export_class = state["export_class"]
    if export_class is None:
        return
    self.layout.operator(export_class.bl_idname, text="FBX (.fbx) - In Between Shape Key")


def register():
    global _export_class
    # Always tear down any previous installation first. Module reload replaces
    # locals, but durable handles in driver_namespace still point at the old RNA.
    runtime.uninstall()
    _reload_children()
    # runtime may have been reloaded; re-bind the package attribute.
    runtime_mod = importlib.import_module(f"{__package__}.runtime")

    operator, ui, _sync = _bindings()
    classes = (
        ui.FBXI_PT_shape_key_inbetween,
        operator.FBXI_OT_rescan_groups,
        operator.FBXI_OT_validate,
        operator.FBXI_OT_add_at_current_value,
        operator.FBXI_OT_remove_target,
        operator.FBXI_OT_select_target,
        operator.FBXI_OT_drag_target,
        operator.FBXI_OT_move_target,
        operator.FBXI_OT_add_range,
        operator.FBXI_OT_remove_range,
    )

    state = runtime_mod.begin_state()
    export_class = operator.make_export_operator()
    _export_class = export_class
    bpy.utils.register_class(export_class)
    state["export_class"] = export_class

    for cls in classes:
        bpy.utils.register_class(cls)
        state["classes"].append(cls)

    draw_specials = ui.draw_shape_key_specials
    for menu in (
        getattr(bpy.types, "MESH_MT_shape_key_context_menu", None),
        getattr(bpy.types, "MESH_MT_shape_key_tree_context_menu", None),
    ):
        if menu is None:
            continue
        menu.append(draw_specials)
        state["menus"].append((menu, draw_specials))

    msgbus_owner = object()
    state["msgbus_owner"] = msgbus_owner
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.ShapeKey, "name"),
        owner=msgbus_owner,
        args=(),
        notify=_mark_dirty,
    )
    depsgraph_handlers = bpy.app.handlers.depsgraph_update_pre
    frame_handlers = bpy.app.handlers.frame_change_post
    if _sync_handler not in depsgraph_handlers:
        depsgraph_handlers.append(_sync_handler)
        state["handlers"].append((depsgraph_handlers, _sync_handler))
    if _frame_change_handler not in frame_handlers:
        frame_handlers.append(_frame_change_handler)
        state["handlers"].append((frame_handlers, _frame_change_handler))

    fbx_module = importlib.import_module("io_scene_fbx")
    original_menu = getattr(fbx_module, "menu_func_export", None)
    if original_menu is not None:
        try:
            bpy.types.TOPBAR_MT_file_export.remove(original_menu)
        except (RuntimeError, ValueError):
            pass
    bpy.types.TOPBAR_MT_file_export.append(_menu_func_export)
    state["fbx_menu"] = {"custom": _menu_func_export, "original": original_menu}


def unregister():
    global _export_class
    runtime_mod = sys.modules.get(f"{__package__}.runtime")
    if runtime_mod is None:
        runtime_mod = importlib.import_module(f"{__package__}.runtime")
    runtime_mod.uninstall()
    _export_class = None
