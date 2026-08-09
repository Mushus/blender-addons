from __future__ import annotations

import bpy

from .metadata import format_target_name, parse_target_name

TARGET_POSITIONS_PROP = "fbxi_target_positions"
_syncing = False


def _key_token(key) -> str:
    return str(key.as_pointer())


def _block_token(block) -> str:
    return str(block.as_pointer())


def _target_object(entry, context):
    active = getattr(context, "object", None)
    if (
        active is not None
        and active.type == "MESH"
        and active.data.shape_keys is not None
        and _key_token(active.data.shape_keys) == entry.key_token
    ):
        return active
    return next(
        (
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH"
            and obj.data.shape_keys is not None
            and _key_token(obj.data.shape_keys) == entry.key_token
        ),
        None,
    )


def _update_position(entry, context) -> None:
    global _syncing
    if _syncing:
        return

    obj = _target_object(entry, context)
    if obj is None or obj.mode != "OBJECT":
        return
    key = obj.data.shape_keys
    target = key.key_blocks.get(entry.target_name)
    if target is None or _block_token(target) != entry.target_token:
        target = next(
            (block for block in key.key_blocks if _block_token(block) == entry.target_token),
            None,
        )
    spec = parse_target_name(target.name) if target is not None else None
    if target is None or spec is None:
        return

    weight = float(round(max(0.0, min(1.0, float(entry.position))) * 100.0))
    new_name = format_target_name(spec.channel, weight)
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


class FBXI_PG_target_position(bpy.types.PropertyGroup):
    key_token: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    target_token: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    target_name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    position: bpy.props.FloatProperty(
        name="Position",
        description="Position of this in-between Shape Key",
        min=0.0,
        max=1.0,
        soft_min=0.0,
        soft_max=1.0,
        step=1,
        precision=2,
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
    key_token = _key_token(key)
    entry = next(
        (
            entry
            for entry in entries
            if entry.key_token == key_token and entry.target_name == target_name
        ),
        None,
    )
    if entry is not None:
        return entry

    target = key.key_blocks.get(target_name)
    if target is None:
        return None
    target_token = _block_token(target)
    return next(
        (
            entry
            for entry in entries
            if entry.key_token == key_token and entry.target_token == target_token
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
    key_token = _key_token(key)
    for block in key.key_blocks:
        spec = parse_target_name(block.name)
        if spec is not None and 0.0 <= spec.weight <= 100.0:
            desired[block.name] = spec.weight / 100.0

    _syncing = True
    try:
        for index in reversed(range(len(entries))):
            entry = entries[index]
            if entry.key_token == key_token and entry.target_name not in desired:
                entries.remove(index)
        for target_name, position in desired.items():
            entry = find_entry(window_manager, obj, target_name)
            if entry is None:
                entry = entries.add()
                entry.key_token = key_token
            entry.target_token = _block_token(key.key_blocks[target_name])
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
    live_keys = {_key_token(obj.data.shape_keys) for obj in objects}
    _syncing = True
    try:
        for index in reversed(range(len(entries))):
            if entries[index].key_token not in live_keys:
                entries.remove(index)
    finally:
        _syncing = False

    for obj in objects:
        sync_object(obj, window_manager)
