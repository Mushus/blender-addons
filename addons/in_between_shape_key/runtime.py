"""Durable registration handles that survive module reload.

Blender can reload this package while RNA classes, app handlers, and menu
draw callbacks remain registered. Module globals are replaced on reload, so
unregister must read the previous installation from driver_namespace.
"""

from __future__ import annotations

import bpy

RUNTIME_KEY = "in_between_shape_key.runtime.v1"


def get_state() -> dict | None:
    return bpy.app.driver_namespace.get(RUNTIME_KEY)


def begin_state() -> dict:
    state = {
        "classes": [],
        "handlers": [],
        "timers": [],
        "ui_sync_timer": None,
        "group_tracks": {},
        "menus": [],
        "msgbus_owner": None,
        "object_props": [],
        "rna_props": [],
        "export_class": None,
        "fbx_menu": {"custom": None, "original": None},
    }
    bpy.app.driver_namespace[RUNTIME_KEY] = state
    return state


def clear_state() -> None:
    bpy.app.driver_namespace.pop(RUNTIME_KEY, None)


def uninstall() -> None:
    """Remove any previous installation using durable refs only."""
    state = get_state()
    if state is None:
        return

    for handler_list, handler in state.get("handlers", []):
        try:
            if handler in handler_list:
                handler_list.remove(handler)
        except (ValueError, TypeError, ReferenceError):
            pass

    for timer in state.get("timers", []):
        try:
            if bpy.app.timers.is_registered(timer):
                bpy.app.timers.unregister(timer)
        except (ValueError, RuntimeError, ReferenceError):
            pass

    owner = state.get("msgbus_owner")
    if owner is not None:
        try:
            bpy.msgbus.clear_by_owner(owner)
        except (RuntimeError, ReferenceError):
            pass

    for menu, draw_fn in state.get("menus", []):
        try:
            menu.remove(draw_fn)
        except (RuntimeError, ValueError, ReferenceError):
            pass

    fbx_menu = state.get("fbx_menu") or {}
    custom = fbx_menu.get("custom")
    original = fbx_menu.get("original")
    if custom is not None:
        try:
            bpy.types.TOPBAR_MT_file_export.remove(custom)
        except (RuntimeError, ValueError, ReferenceError):
            pass
    if original is not None:
        try:
            draws = _export_menu_draws()
            if original not in draws:
                bpy.types.TOPBAR_MT_file_export.append(original)
        except (RuntimeError, ValueError, ReferenceError):
            pass

    for owner, name in reversed(state.get("rna_props") or []):
        if hasattr(owner, name):
            try:
                delattr(owner, name)
            except (AttributeError, TypeError):
                pass

    classes = list(state.get("classes") or [])
    export_class = state.get("export_class")
    if export_class is not None:
        classes.append(export_class)
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except (RuntimeError, ValueError, ReferenceError):
            pass

    for name in state.get("object_props") or []:
        if hasattr(bpy.types.Object, name):
            try:
                delattr(bpy.types.Object, name)
            except (AttributeError, TypeError):
                pass

    clear_state()


def _export_menu_draws() -> list:
    menu = bpy.types.TOPBAR_MT_file_export
    for attr in ("draw_funcs", "_draw_funcs"):
        funcs = getattr(menu, attr, None)
        if funcs:
            return list(funcs)
    try:
        return list(menu._dyn_ui_initialize())
    except Exception:
        return []
