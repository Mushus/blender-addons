"""Durable registration handles that survive module reload."""

from __future__ import annotations

import bpy

RUNTIME_KEY = "edit_vertex_relax.runtime.v1"
HOST_KEY = "blender_addon_tools.embedded_host.v1"


def get_state() -> dict | None:
    return bpy.app.driver_namespace.get(RUNTIME_KEY)


def begin_state() -> dict:
    state = {
        "classes": [],
        "scene_prop": None,
        "tool_id": None,
        "owner_id": None,
        "unregister_tool": None,
    }
    bpy.app.driver_namespace[RUNTIME_KEY] = state
    return state


def uninstall() -> None:
    """Remove any previous installation using durable references only."""
    state = get_state()
    if state is None:
        if hasattr(bpy.types.Scene, "edit_vertex_relax"):
            try:
                del bpy.types.Scene.edit_vertex_relax
            except (AttributeError, TypeError):
                pass
        return

    tool_id = state.get("tool_id")
    owner_id = state.get("owner_id")
    unregister_tool = state.get("unregister_tool")
    if tool_id and owner_id and unregister_tool is not None:
        try:
            unregister_tool(tool_id, owner_id)
        except Exception:
            host_state = bpy.app.driver_namespace.get(HOST_KEY)
            if host_state is not None:
                owners = host_state.get("tools", {}).get(tool_id)
                if owners is not None:
                    owners.pop(owner_id, None)

    scene_prop = state.get("scene_prop")
    if scene_prop and hasattr(bpy.types.Scene, scene_prop):
        try:
            delattr(bpy.types.Scene, scene_prop)
        except (AttributeError, TypeError):
            pass

    for cls in reversed(list(state.get("classes") or [])):
        try:
            bpy.utils.unregister_class(cls)
        except (RuntimeError, ValueError, ReferenceError):
            pass

    bpy.app.driver_namespace.pop(RUNTIME_KEY, None)