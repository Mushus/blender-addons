from __future__ import annotations

import bpy
from bpy.app.translations import pgettext_iface

from .operator import (
    FBXI_OT_add_existing_key,
    FBXI_OT_convert_to_inbetween,
    FBXI_OT_remove_target,
    FBXI_OT_select_target,
)
from .sync import controller_value_path, controller_value_property, read_groups
from .ui_state import find_entry
from .validation import validate_shape_keys


def _message(source: str, **values) -> str:
    return pgettext_iface(source).format(**values)


def _draw_target_row(layout, context, obj, key, member, active_name):
    target_name = member.get("name", "")
    target = key.key_blocks.get(target_name)
    if target is None:
        return

    row = layout.row(align=True)
    button = row.operator(
        FBXI_OT_select_target.bl_idname,
        text="",
        icon="KEYTYPE_KEYFRAME_VEC",
        depress=target_name == active_name,
    )
    button.target_name = target_name

    controls = row.row(align=True)
    controls.enabled = obj.mode == "OBJECT"
    entry = find_entry(context.window_manager, obj, target_name)
    if entry is None:
        controls.label(text="Position unavailable", icon="ERROR")
    else:
        controls.prop(entry, "position", text="", slider=True)
    remove = controls.operator(FBXI_OT_remove_target.bl_idname, text="", icon="X")
    remove.target_name = target_name


def _draw_targets(layout, context, obj, key, group, active_name):
    targets = layout.column(align=True)
    for member in group.get("members", []):
        _draw_target_row(targets, context, obj, key, member, active_name)


def _draw_managed_group(layout, context, obj, key, group, active_name):
    controller_name = group.get("controller", "")
    controller = key.key_blocks.get(controller_name)
    if controller is None:
        layout.label(
            text=_message("Missing controller: {controller}", controller=controller_name),
            icon="ERROR",
        )
        return

    box = layout.box()
    row = box.row(align=True)
    button = row.operator(
        FBXI_OT_select_target.bl_idname,
        text=controller.name,
        icon="DRIVER",
    )
    button.target_name = controller.name
    value_path = controller_value_path(controller.name)
    if controller_value_property(controller.name) in obj:
        row.prop(obj, value_path, text="Value", slider=True)
    else:
        row.label(text="Value unavailable", icon="ERROR")
    row.menu(
        FBXI_MT_add_existing_key.bl_idname,
        text="",
        icon="DOWNARROW_HLT",
    )

    _draw_targets(box, context, obj, key, group, active_name)


def draw_shape_key_inbetween(self, context):
    obj = context.object
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return

    layout = self.layout
    key = obj.data.shape_keys
    # UI draw callbacks must remain read-only.  Synchronisation mutates Object
    # and Shape Key data (relative chains and target positions),
    # which Blender 5.1 rejects while a Properties panel is being drawn.
    # The depsgraph handler and the add-on operators perform this work outside
    # the draw callback.
    active = obj.active_shape_key
    active_name = getattr(active, "name", "")
    groups = read_groups(key)
    active_group = next(
        (
            group
            for group in groups
            if group.get("controller") == active_name
            or any(member.get("name") == active_name for member in group.get("members", []))
        ),
        None,
    )
    if active_group is None:
        multiple_selected = sum(bool(block.select) for block in key.key_blocks) > 1
        if active is not None and active_name != "Basis" and "@" not in active_name and not multiple_selected:
            box = layout.box()
            box.label(text=_message("Shape Key: {name}", name=active_name))
            box.operator(
                FBXI_OT_convert_to_inbetween.bl_idname,
                text="Convert to In-Between Shape Key",
                icon="SHAPEKEY_DATA",
            )
        return

    result = validate_shape_keys(key)
    if result.errors:
        layout.label(text=result.errors[0], icon="ERROR")

    _draw_managed_group(layout, context, obj, key, active_group, active_name)

    # Enabled only by the GUI smoke test. Emitted last so the capture proves the
    # full panel callback ran, not just an early row.
    if context.scene is not None and context.scene.get("_fbxi_ui_pixel_probe"):
        probe_row = layout.row()
        probe_row.alert = True
        probe_row.label(text="FBXI UI PIXEL PROBE", icon="CHECKMARK")


class FBXI_PT_shape_key_inbetween(bpy.types.Panel):
    bl_idname = "FBXI_PT_shape_key_inbetween"
    bl_label = "In-Between Shape Key"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(cls, context) -> bool:
        obj = context.object
        return (
            obj is not None
            and obj.type == "MESH"
            and obj.data.shape_keys is not None
        )

    def draw(self, context):
        draw_shape_key_inbetween(self, context)


class FBXI_MT_add_existing_key(bpy.types.Menu):
    bl_idname = "FBXI_MT_add_existing_key"
    bl_label = "Add Existing Shape Key"

    def draw(self, context):
        layout = self.layout
        obj = context.object
        key = getattr(getattr(obj, "data", None), "shape_keys", None)
        active = getattr(obj, "active_shape_key", None)
        if key is None or active is None:
            return
        group = next(
            (
                group
                for group in read_groups(key)
                if group.get("controller") == active.name
                or any(member.get("name") == active.name for member in group.get("members", []))
            ),
            None,
        )
        if group is None:
            layout.label(text="Select an In-Between controller first", icon="INFO")
            return
        controller = key.key_blocks.get(group.get("controller", ""))
        if controller is None:
            layout.label(text="In-Between controller is unavailable", icon="ERROR")
            return

        existing = [
            block
            for block in key.key_blocks
            if block.name != "Basis"
            and block.name != controller.name
            and "@" not in block.name
            and not any(other.get("controller") == block.name for other in read_groups(key))
        ]
        if not existing:
            layout.label(text="No existing Shape Keys available", icon="INFO")
            return
        layout.operator_context = "INVOKE_DEFAULT"
        item = layout.operator(
            FBXI_OT_add_existing_key.bl_idname,
            text="Add to In-Between",
            icon="ADD",
        )
        item.controller_name = controller.name


def draw_shape_key_specials(self, context):
    if FBXI_OT_convert_to_inbetween.poll(context):
        self.layout.operator(
            FBXI_OT_convert_to_inbetween.bl_idname,
            text="Convert to In-Between Shape Key",
            icon="SHAPEKEY_DATA",
        )
