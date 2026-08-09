from __future__ import annotations

import time

import bpy
from bpy.app.translations import pgettext_iface

from .metadata import POSITION_DECIMALS, format_target_name, normalize_position, parse_target_name
from .runtime import get_state

TARGET_POSITIONS_PROP = "fbxi_target_positions"
_syncing = False
_POSITION_DEBOUNCE_SECONDS = 0.15


def _session_uid(value) -> str:
    return str(value.session_uid)


def _target_object(entry, context):
    active = getattr(context, "object", None)
    if (
        active is not None
        and active.type == "MESH"
        and active.data.shape_keys is not None
        and _session_uid(active) == entry.object_session_uid
        and _session_uid(active.data.shape_keys) == entry.key_session_uid
    ):
        return active
    return next(
        (
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH"
            and obj.data.shape_keys is not None
            and _session_uid(obj) == entry.object_session_uid
            and _session_uid(obj.data.shape_keys) == entry.key_session_uid
        ),
        None,
    )


def _apply_position(entry, context, position: float | None = None) -> None:
    obj = _target_object(entry, context)
    if obj is None or obj.mode != "OBJECT":
        return
    key = obj.data.shape_keys
    target = key.key_blocks.get(entry.target_name)
    spec = parse_target_name(target.name) if target is not None else None
    if target is None or spec is None:
        return

    target_position = normalize_position(entry.position if position is None else position)
    new_name = format_target_name(spec.channel, target_position)
    duplicate = key.key_blocks.get(new_name)
    if duplicate is not None and duplicate != target:
        sync_object(obj, context.window_manager)
        return

    target.name = new_name
    entry.target_name = new_name
    from .sync import sync_key

    sync_key(key, obj)
    obj.active_shape_key_index = key.key_blocks.find(new_name)
    if context.area is not None:
        context.area.tag_redraw()


def _flush_pending_positions(*, force: bool = False):
    global _syncing
    state = get_state()
    if state is None:
        return None
    pending = state.setdefault("pending_positions", {})
    now = time.monotonic()
    remaining = []
    entries = _entries(getattr(bpy.context, "window_manager", None))
    if entries is None:
        pending.clear()
    else:
        for token, item in list(pending.items()):
            delay = _POSITION_DEBOUNCE_SECONDS - (now - item["updated_at"])
            if not force and delay > 0.0:
                remaining.append(delay)
                continue
            del pending[token]
            entry = next(
                (
                    candidate
                    for candidate in entries
                    if candidate.object_session_uid == item["object_session_uid"]
                    and candidate.key_session_uid == item["key_session_uid"]
                    and candidate.target_name == item["target_name"]
                ),
                None,
            )
            if entry is not None:
                _syncing = True
                try:
                    entry.position = item["position"]
                finally:
                    _syncing = False
                _apply_position(entry, bpy.context, item["position"])
    if pending:
        return max(0.01, min(remaining, default=_POSITION_DEBOUNCE_SECONDS))
    state["position_timer"] = None
    return None


def _schedule_position_apply() -> None:
    state = get_state()
    if state is None:
        raise RuntimeError(pgettext_iface("In-Between runtime is unavailable"))
    timer = state.get("position_timer")
    if timer is not None and bpy.app.timers.is_registered(timer):
        return
    bpy.app.timers.register(_flush_pending_positions, first_interval=_POSITION_DEBOUNCE_SECONDS)
    state["position_timer"] = _flush_pending_positions
    if _flush_pending_positions not in state["timers"]:
        state["timers"].append(_flush_pending_positions)


def _update_position(entry, context) -> None:
    if _syncing:
        return
    obj = _target_object(entry, context)
    if obj is None or obj.mode != "OBJECT":
        return
    key = obj.data.shape_keys
    target = key.key_blocks.get(entry.target_name)
    if target is None:
        return
    position = normalize_position(entry.position)
    state = get_state()
    if state is None:
        raise RuntimeError(pgettext_iface("In-Between runtime is unavailable"))
    token = f"{entry.object_session_uid}:{entry.key_session_uid}:{entry.target_name}"
    state.setdefault("pending_positions", {})[token] = {
        "object_session_uid": entry.object_session_uid,
        "key_session_uid": entry.key_session_uid,
        "target_name": entry.target_name,
        "position": position,
        "updated_at": time.monotonic(),
    }
    _schedule_position_apply()


class FBXI_PG_target_position(bpy.types.PropertyGroup):
    object_session_uid: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    key_session_uid: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    target_name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    position: bpy.props.FloatProperty(
        name="Position",
        description="Position of this in-between Shape Key",
        min=0.0,
        max=1.0,
        soft_min=0.0,
        soft_max=1.0,
        step=1,
        precision=POSITION_DECIMALS,
        subtype="FACTOR",
        options={"SKIP_SAVE"},
        update=_update_position,
    )


def _entries(window_manager):
    return getattr(window_manager, TARGET_POSITIONS_PROP, None)


def find_entry(window_manager, obj, target_name: str):
    entries = _entries(window_manager)
    if entries is None:
        return None
    key = obj.data.shape_keys
    object_session_uid = _session_uid(obj)
    key_session_uid = _session_uid(key)
    return next(
        (
            entry
            for entry in entries
            if entry.object_session_uid == object_session_uid
            and entry.key_session_uid == key_session_uid
            and entry.target_name == target_name
        ),
        None,
    )


def sync_object(obj, window_manager=None) -> None:
    global _syncing
    if window_manager is None:
        window_manager = getattr(bpy.context, "window_manager", None)
    entries = _entries(window_manager)
    if entries is None or obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return

    desired = {}
    key = obj.data.shape_keys
    object_session_uid = _session_uid(obj)
    key_session_uid = _session_uid(key)
    for block in key.key_blocks:
        spec = parse_target_name(block.name)
        if spec is not None and 0.0 <= spec.position <= 1.0:
            desired[block.name] = spec.position

    _syncing = True
    try:
        for index in reversed(range(len(entries))):
            entry = entries[index]
            if (
                entry.object_session_uid == object_session_uid
                and entry.key_session_uid == key_session_uid
                and entry.target_name not in desired
            ):
                entries.remove(index)
        for target_name, position in desired.items():
            entry = find_entry(window_manager, obj, target_name)
            if entry is None:
                entry = entries.add()
                entry.object_session_uid = object_session_uid
                entry.key_session_uid = key_session_uid
            entry.target_name = target_name
            if abs(float(entry.position) - position) > 1e-9:
                entry.position = position
    finally:
        _syncing = False


def sync_all(bpy_data, window_manager=None) -> None:
    global _syncing
    if window_manager is None:
        window_manager = getattr(bpy.context, "window_manager", None)
    entries = _entries(window_manager)
    if entries is None:
        return

    objects = [
        obj
        for obj in bpy_data.objects
        if obj.type == "MESH" and obj.data.shape_keys is not None
    ]
    live_pairs = {
        (_session_uid(obj), _session_uid(obj.data.shape_keys))
        for obj in objects
    }
    _syncing = True
    try:
        for index in reversed(range(len(entries))):
            entry = entries[index]
            if (entry.object_session_uid, entry.key_session_uid) not in live_pairs:
                entries.remove(index)
    finally:
        _syncing = False

    for obj in objects:
        sync_object(obj, window_manager)
