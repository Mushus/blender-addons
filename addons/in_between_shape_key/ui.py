from __future__ import annotations

import bpy

from .operator import (
    FBXI_OT_add_at_current_value,
    FBXI_OT_drag_target,
    FBXI_OT_move_target,
    FBXI_OT_remove_target,
    FBXI_OT_select_target,
)
from .sync import read_groups
from .validation import validate_shape_keys

_TIMELINE_MIN = 0
_TIMELINE_MAX = 100
_TIMELINE_MAJOR_STEP = 10
_TIMELINE_DISPLAY_STEP = 5
_TIMELINE_TRACK_START = 0.10
_TIMELINE_TRACK_END = 0.88
_DISPLAY_NAME_LIMIT = 28


def _weight(value, default=100.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _display_name(name):
    """Keep detail-card labels compact without changing the actual target name."""
    name = str(name or "")
    if len(name) <= _DISPLAY_NAME_LIMIT:
        return name
    return f"{name[:_DISPLAY_NAME_LIMIT - 1]}…"


def _timeline_markers(controller_name, members, intermediate_members, endpoint):
    markers = [(0.0, controller_name, False)]
    markers.extend(
        (member.get("weight", 100.0), member.get("name", ""), True)
        for member in intermediate_members
    )
    if endpoint is not None:
        markers.append((100.0, endpoint.get("name", ""), False))
    return [(_weight(weight, 100.0), name, draggable) for weight, name, draggable in markers]


def _draw_marker_button(slot, target_name, draggable):
    if not target_name:
        slot.label(text="", icon="KEYFRAME")
        return
    operator_id = FBXI_OT_drag_target.bl_idname if draggable else FBXI_OT_select_target.bl_idname
    # Match the yellow keyframe icon used by the target cards.
    slot.operator_context = "INVOKE_REGION_WIN"
    button = slot.operator(operator_id, text="", icon="KEYTYPE_KEYFRAME_VEC", emboss=False)
    button.target_name = target_name
    if draggable:
        button.track_start = _TIMELINE_TRACK_START
        button.track_end = _TIMELINE_TRACK_END


def _draw_timeline_track(timeline, markers):
    track_box = timeline.box()
    header = track_box.row(align=True)
    header.label(text="Timeline", icon="TIME")

    marker_slots = {}
    for weight, target_name, draggable in markers:
        slot_index = min(
            _TIMELINE_MAX // _TIMELINE_DISPLAY_STEP,
            max(_TIMELINE_MIN, round(weight / _TIMELINE_DISPLAY_STEP)),
        )
        marker_slots.setdefault(slot_index, []).append((target_name, draggable))

    # Use a fixed-width 5% visual grid. It keeps the marker visible at normal
    # Properties-panel widths while the operator still moves the actual value
    # continuously at 1% or finer precision.
    track = track_box.row(align=True)
    slot_grid = track.grid_flow(
        row_major=True,
        columns=_TIMELINE_MAX // _TIMELINE_DISPLAY_STEP + 1,
        even_columns=True,
        even_rows=True,
    )
    for slot_index in range(_TIMELINE_MAX // _TIMELINE_DISPLAY_STEP + 1):
        slot = slot_grid.column(align=True)
        slot.alignment = "CENTER"
        entries = marker_slots.get(slot_index, [])
        if entries:
            for target_name, draggable in entries:
                _draw_marker_button(slot, target_name, draggable)
        elif slot_index % (_TIMELINE_MAJOR_STEP // _TIMELINE_DISPLAY_STEP) == 0:
            slot.label(text="│")
        else:
            slot.label(text="·")

    scale = track_box.row(align=True)
    scale_grid = scale.grid_flow(
        row_major=True,
        columns=_TIMELINE_MAX // _TIMELINE_DISPLAY_STEP + 1,
        even_columns=True,
        even_rows=True,
    )
    for slot_index in range(_TIMELINE_MAX // _TIMELINE_DISPLAY_STEP + 1):
        tick = scale_grid.column(align=True)
        tick.alignment = "CENTER"
        if slot_index % (_TIMELINE_MAJOR_STEP // _TIMELINE_DISPLAY_STEP) == 0:
            tick.label(text="│")
        else:
            tick.label(text="·")


def _draw_target_card(timeline, member, *, endpoint=False):
    target_name = member.get("name", "")
    weight = _weight(member.get("weight", 100.0))
    card = timeline.box()
    row = card.row(align=True)
    button = row.operator(
        FBXI_OT_select_target.bl_idname,
        text=_display_name(target_name),
        icon="KEYTYPE_KEYFRAME_VEC",
    )
    button.target_name = target_name
    if endpoint:
        row.label(text="@100  Locked", icon="LOCKED")
        return
    move = row.operator(
        FBXI_OT_move_target.bl_idname,
        text=f"@{weight:g}",
        icon="DRIVER",
    )
    move.target_name = target_name
    remove = row.operator(FBXI_OT_remove_target.bl_idname, text="", icon="X")
    remove.target_name = target_name


def _draw_timeline(layout, _key, group):
    controller_name = group.get("controller", "")
    members = sorted(
        group.get("members", []),
        key=lambda member: _weight(member.get("weight", 100.0)),
    )
    intermediate_members = [
        member for member in members if _weight(member.get("weight", 100.0)) < 100.0
    ]

    # Shape Key names are the source of truth. The timeline is only a view over
    # the parsed ``Channel@Weight`` names.
    timeline = layout.box()
    endpoint = next(
        (member for member in members if _weight(member.get("weight", 100.0)) >= 100.0),
        None,
    )
    markers = _timeline_markers(controller_name, members, intermediate_members, endpoint)
    _draw_timeline_track(timeline, markers)

    details = timeline.column(align=False)
    for member in intermediate_members:
        _draw_target_card(details, member)

    if endpoint is not None:
        _draw_target_card(details, endpoint, endpoint=True)


def _draw_managed_group(layout, key, group):
    controller_name = group.get("controller", "")
    controller = key.key_blocks.get(controller_name)
    if controller is None:
        layout.label(text=f"Missing controller: {controller_name}", icon="ERROR")
        return

    box = layout.box()
    row = box.row(align=True)
    button = row.operator(
        FBXI_OT_select_target.bl_idname,
        text=controller.name,
        icon="DRIVER",
    )
    button.target_name = controller.name
    row.prop(controller, "value", text="Value", slider=True)

    _draw_timeline(box, key, group)


def draw_shape_key_inbetween(self, context):
    obj = context.object
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return

    layout = self.layout
    key = obj.data.shape_keys
    # UI draw callbacks must remain read-only.  Synchronisation mutates Object
    # and Shape Key data (custom properties, drivers, ordering, and timeline
    # positions),
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
        return

    result = validate_shape_keys(key)
    layout.separator()
    if result.errors:
        layout.label(text=result.errors[0], icon="ERROR")

    _draw_managed_group(layout, key, active_group)

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


def draw_shape_key_specials(self, _context):
    self.layout.separator()
    self.layout.operator(
        FBXI_OT_add_at_current_value.bl_idname,
        text="Add In-Between at Current Value",
        icon="ADD",
    )
