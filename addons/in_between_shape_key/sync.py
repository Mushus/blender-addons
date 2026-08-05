from __future__ import annotations

from collections import defaultdict

import bpy

from .metadata import parse_target_name

_SYNCING_KEYS: set[int] = set()


def groups_from_names(key) -> list[dict]:
    """Infer all channels and their targets directly from Shape Key names."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for index, block in enumerate(key.key_blocks):
        spec = parse_target_name(block.name)
        if spec is None:
            continue
        grouped[spec.channel].append({"index": index, "name": block.name, "weight": spec.weight})
    groups = []
    for channel, members in sorted(grouped.items()):
        controller = key.key_blocks.get(channel)
        if controller is None or controller.name == "Basis":
            controller_name = ""
        else:
            controller_name = controller.name
        groups.append(
            {
                "channel": channel,
                "controller": controller_name,
                "members": sorted(members, key=lambda item: item["weight"]),
            }
        )
    return groups


def read_groups(key) -> list[dict]:
    """Return transient channel metadata inferred from current Shape Key names."""
    return groups_from_names(key)


def clear_shape_to_basis(key_block, basis) -> None:
    for destination_point, basis_point in zip(key_block.data, basis.data, strict=True):
        destination_point.co = basis_point.co


def _controller_block(key, group: dict):
    name = group.get("controller", "")
    if not name:
        return None
    return key.key_blocks.get(name)


def is_controller(key_block) -> bool:
    key = getattr(key_block, "id_data", None)
    if key is None:
        return False
    return controller_group(key, key_block.name) is not None


def controller_group(key, controller_name: str) -> dict | None:
    return next((group for group in groups_from_names(key) if group["controller"] == controller_name), None)


def group_for_channel(key, channel: str) -> dict | None:
    return next((group for group in groups_from_names(key) if group["channel"] == channel), None)


def _target_members(key, channel: str) -> list[dict]:
    members = []
    for index, block in enumerate(key.key_blocks):
        spec = parse_target_name(block.name)
        if spec is None or spec.channel != channel:
            continue
        if not 1.0 <= spec.weight <= 100.0:
            continue
        members.append({"index": index, "name": block.name, "weight": spec.weight})
    return sorted(members, key=lambda item: item["weight"])


def _remove_addon_driver(block) -> None:
    try:
        block.driver_remove("value")
    except (TypeError, ValueError, RuntimeError):
        pass


def _value_at_weight(controller_value: float, previous: float, weight: float) -> float:
    value = controller_value * 100.0
    return max(0.0, min(1.0, (value - previous) / (weight - previous)))


def _set_relative_chain(key, members: list[dict]) -> None:
    basis = key.key_blocks[0]
    previous = basis
    for member in members:
        block = key.key_blocks.get(member["name"])
        if block is None:
            continue
        block.relative_key = previous
        previous = block


def _sort_managed_members(obj, key, controller, members: list[dict]) -> None:
    if obj.mode != "OBJECT":
        return
    desired_names = [member["name"] for member in sorted(members, key=lambda item: item["weight"])]
    active_name = obj.active_shape_key.name if obj.active_shape_key is not None else None
    controller_index = key.key_blocks.find(controller.name)
    if controller_index < 0:
        return

    for offset, name in enumerate(desired_names):
        desired_index = controller_index + 1 + offset
        current_index = key.key_blocks.find(name)
        if current_index < 0:
            continue
        while current_index > desired_index:
            obj.active_shape_key_index = current_index
            with bpy.context.temp_override(object=obj, active_object=obj):
                result = bpy.ops.object.shape_key_move(type="UP")
            if result != {"FINISHED"}:
                break
            current_index -= 1
        while current_index < desired_index:
            obj.active_shape_key_index = current_index
            with bpy.context.temp_override(object=obj, active_object=obj):
                result = bpy.ops.object.shape_key_move(type="DOWN")
            if result != {"FINISHED"}:
                break
            current_index += 1

    if active_name is not None and key.key_blocks.get(active_name) is not None:
        obj.active_shape_key_index = key.key_blocks.find(active_name)


def _sync_managed_group(key, group: dict, obj=None) -> None:
    controller = _controller_block(key, group)
    if controller is None or not group.get("controller"):
        return

    if obj is None:
        return
    members = _target_members(key, group["channel"])
    if not members:
        return

    _sort_managed_members(obj, key, controller, members)
    members = _target_members(key, group["channel"])
    _set_relative_chain(key, members)
    previous = 0.0
    for member in members:
        block = key.key_blocks.get(member["name"])
        if block is not None:
            _remove_addon_driver(block)
            block.value = _value_at_weight(float(controller.value), previous, float(member["weight"]))
        previous = float(member["weight"])

    clear_shape_to_basis(controller, key.key_blocks[0])


def rescan_key(key, obj=None) -> None:
    sync_key(key, obj)


def _sync_key_impl(key, obj=None) -> bool:
    for group in groups_from_names(key):
        if group.get("controller"):
            _sync_managed_group(key, group, obj)
    return False


def sync_key(key, obj=None) -> bool:
    key_id = key.as_pointer()
    if key_id in _SYNCING_KEYS:
        return False
    _SYNCING_KEYS.add(key_id)
    try:
        return _sync_key_impl(key, obj)
    finally:
        _SYNCING_KEYS.remove(key_id)


def sync_all(bpy_data) -> None:
    for obj in bpy_data.objects:
        if obj.type != "MESH" or obj.data.shape_keys is None:
            continue
        enforce_controller_selection(obj)
        sync_key(obj.data.shape_keys, obj)


def enforce_controller_selection(obj) -> None:
    if obj.mode != "EDIT" or obj.data.shape_keys is None:
        return
    key = obj.data.shape_keys
    active = obj.active_shape_key
    if active is None or not is_controller(active):
        return
    group = controller_group(key, active.name)
    if group is None:
        return
    target_index = next(
        (key.key_blocks.find(member.get("name", "")) for member in group.get("members", []) if key.key_blocks.get(member.get("name", ""))),
        0,
    )
    obj.active_shape_key_index = target_index
