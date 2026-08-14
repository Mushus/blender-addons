from __future__ import annotations

import base64
from collections import defaultdict

from bpy.app.translations import pgettext_iface

from .metadata import format_target_name, is_basis_block, normalize_position, parse_target_name

_SYNCING_KEYS: set[int] = set()
_CONTROLLER_VALUE_PREFIX = "_fbxi_inbetween_value_"


def _message(source: str, **values) -> str:
    return pgettext_iface(source).format(**values)


def controller_value_property(channel: str) -> str:
    encoded = base64.urlsafe_b64encode(channel.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{_CONTROLLER_VALUE_PREFIX}{encoded}"


def controller_value_path(channel: str) -> str:
    return f'["{controller_value_property(channel)}"]'


def set_controller_value(obj, channel: str, value: float) -> None:
    property_name = controller_value_property(channel)
    if property_name not in obj:
        raise KeyError(
            _message("In-Between controller value is unavailable: {channel}", channel=channel)
        )
    obj[property_name] = normalize_position(value)


def get_controller_value(obj, channel: str) -> float:
    property_name = controller_value_property(channel)
    if property_name not in obj:
        raise KeyError(
            _message("In-Between controller value is unavailable: {channel}", channel=channel)
        )
    return float(obj[property_name])


def groups_from_names(key) -> list[dict]:
    """Infer all channels and their targets directly from Shape Key names."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for index, block in enumerate(key.key_blocks):
        if is_basis_block(key, block):
            continue
        spec = parse_target_name(block.name)
        if spec is None:
            continue
        grouped[spec.channel].append(
            {"index": index, "name": block.name, "position": spec.position}
        )
    groups = []
    for channel, members in sorted(grouped.items()):
        controller = key.key_blocks.get(channel)
        if controller is None or is_basis_block(key, controller):
            controller_name = ""
        else:
            controller_name = controller.name
        groups.append(
            {
                "channel": channel,
                "controller": controller_name,
                "members": sorted(members, key=lambda item: item["position"]),
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
        if is_basis_block(key, block):
            continue
        spec = parse_target_name(block.name)
        if spec is None or spec.channel != channel:
            continue
        if not 0.0 <= spec.position <= 1.0:
            continue
        members.append({"index": index, "name": block.name, "position": spec.position})
    return sorted(members, key=lambda item: item["position"])


def _driver_expression(previous: float, position: float) -> str:
    if position == 0.0:
        return "1.0"
    span = position - previous
    if span <= 0.0:
        raise ValueError(_message("In-Between target positions must be strictly increasing"))
    return f"min(max((fbxi_controller - {previous:.12g}) / {span:.12g}, 0.0), 1.0)"


def _driver_fcurve(key, block):
    animation_data = key.animation_data
    if animation_data is None:
        return None
    data_path = block.path_from_id("value")
    return next(
        (
            fcurve
            for fcurve in animation_data.drivers
            if fcurve.data_path == data_path and fcurve.array_index == 0
        ),
        None,
    )


def _is_addon_driver(fcurve) -> bool:
    return any(variable.name == "fbxi_controller" for variable in fcurve.driver.variables)


def _action_fcurves(id_data) -> list:
    animation_data = getattr(id_data, "animation_data", None)
    action = getattr(animation_data, "action", None)
    if action is None:
        return []
    return [
        fcurve
        for layer in action.layers
        for strip in layer.strips
        for channelbag in strip.channelbags
        for fcurve in channelbag.fcurves
    ]


def _controller_source_path(key, controller) -> str | None:
    fcurve = _driver_fcurve(key, controller)
    if fcurve is None or not _is_addon_driver(fcurve):
        return None
    variable = next(
        (variable for variable in fcurve.driver.variables if variable.name == "fbxi_controller"),
        None,
    )
    if variable is None or variable.type != "SINGLE_PROP":
        return None
    return variable.targets[0].data_path


def _normalize_linked_target_names(key) -> None:
    """Propagate a controller rename through targets linked by its live driver."""
    linked_by_path: dict[str, list[tuple[object, object]]] = defaultdict(list)
    for block in key.key_blocks:
        if is_basis_block(key, block):
            continue
        spec = parse_target_name(block.name)
        if spec is None:
            continue
        source_path = _controller_source_path(key, block)
        if source_path is not None:
            linked_by_path[source_path].append((block, spec))

    for controller in key.key_blocks:
        if is_basis_block(key, controller) or parse_target_name(controller.name) is not None:
            continue
        source_path = _controller_source_path(key, controller)
        if source_path is None:
            continue
        linked = linked_by_path.get(source_path, [])
        stale_channels = {
            spec.channel
            for _block, spec in linked
            if spec.channel != controller.name and key.key_blocks.get(spec.channel) is None
        }
        if not stale_channels:
            continue
        if len(stale_channels) != 1:
            raise RuntimeError(
                _message(
                    "Cannot resolve renamed In-Between controller {channel}",
                    channel=controller.name,
                )
            )
        stale_channel = next(iter(stale_channels))
        renames = [
            (block, format_target_name(controller.name, spec.position))
            for block, spec in linked
            if spec.channel == stale_channel
        ]
        for block, new_name in renames:
            existing = key.key_blocks.get(new_name)
            if existing is not None and existing != block:
                raise RuntimeError(_message("Shape Key already exists: {name}", name=new_name))
        for block, new_name in renames:
            block.name = new_name


def _move_action_path(id_data, old_path: str, new_path: str) -> None:
    if old_path == new_path:
        return
    fcurves = _action_fcurves(id_data)
    moving = [fcurve for fcurve in fcurves if fcurve.data_path == old_path]
    if moving and any(fcurve.data_path == new_path for fcurve in fcurves):
        raise RuntimeError(
            _message(
                "Animation already exists for In-Between controller path: {path}",
                path=new_path,
            )
        )
    for fcurve in moving:
        fcurve.data_path = new_path


def _remove_action_paths(id_data, paths: set[str]) -> None:
    if not paths:
        return
    animation_data = getattr(id_data, "animation_data", None)
    action = getattr(animation_data, "action", None)
    if action is None:
        return
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                for fcurve in list(channelbag.fcurves):
                    if fcurve.data_path in paths:
                        channelbag.fcurves.remove(fcurve)


def _ensure_value_driver(key, obj, block, source_path: str, expression: str) -> None:
    fcurve = _driver_fcurve(key, block)
    if fcurve is not None:
        driver = fcurve.driver
        configured = (
            driver.type == "SCRIPTED"
            and driver.expression == expression
            and len(driver.variables) == 1
            and driver.variables[0].name == "fbxi_controller"
            and driver.variables[0].type == "SINGLE_PROP"
            and driver.variables[0].targets[0].id == obj
            and driver.variables[0].targets[0].data_path == source_path
        )
        if configured:
            return
        if not block.driver_remove("value"):
            raise RuntimeError(
                _message("Failed to rebuild Shape Key driver: {name}", name=block.name)
            )
    fcurve = block.driver_add("value")
    driver = fcurve.driver
    while driver.variables:
        driver.variables.remove(driver.variables[0])
    variable = driver.variables.new()
    variable.name = "fbxi_controller"
    variable.type = "SINGLE_PROP"
    target = variable.targets[0]
    target.id_type = "OBJECT"
    target.id = obj
    target.data_path = source_path
    driver.type = "SCRIPTED"
    driver.expression = expression


def _remove_value_keyframes(key, blocks: list) -> None:
    managed_paths = {block.path_from_id("value") for block in blocks}
    _remove_action_paths(key, managed_paths)


def _remove_orphan_addon_drivers(key, managed_paths: set[str]) -> None:
    animation_data = key.animation_data
    if animation_data is None:
        return
    for fcurve in list(animation_data.drivers):
        if _is_addon_driver(fcurve) and fcurve.data_path not in managed_paths:
            animation_data.drivers.remove(fcurve)


def _set_relative_chain(key, members: list[dict]) -> None:
    basis = key.key_blocks[0]
    previous = basis
    for member in members:
        block = key.key_blocks.get(member["name"])
        if block is None:
            continue
        block.relative_key = previous
        previous = block


def _ensure_controller_value(obj, controller, previous_path: str | None) -> tuple[str, str]:
    property_name = controller_value_property(controller.name)
    source_path = controller_value_path(controller.name)
    if property_name not in obj:
        obj[property_name] = normalize_position(controller.value)
    if previous_path is not None:
        _move_action_path(obj, previous_path, source_path)
    obj.id_properties_ui(property_name).update(
        min=0.0,
        max=1.0,
        soft_min=0.0,
        soft_max=1.0,
        precision=3,
        step=0.001,
        description=_message(
            "Value for In-Between controller {channel}",
            channel=controller.name,
        ),
    )
    return property_name, source_path


def _sync_managed_group(key, group: dict, obj=None) -> tuple[set[str], str | None]:
    controller = _controller_block(key, group)
    if controller is None or not group.get("controller"):
        return set(), None

    if obj is None:
        return set(), None
    members = _target_members(key, group["channel"])
    if not members:
        return set(), None

    member_blocks = [key.key_blocks[member["name"]] for member in members]
    _remove_value_keyframes(key, [controller, *member_blocks])
    _set_relative_chain(key, members)
    previous_path = _controller_source_path(key, controller)
    property_name, source_path = _ensure_controller_value(obj, controller, previous_path)
    _ensure_value_driver(key, obj, controller, source_path, "fbxi_controller")
    managed_paths = {controller.path_from_id("value")}
    previous = 0.0
    for member in members:
        block = key.key_blocks.get(member["name"])
        if block is not None:
            expression = _driver_expression(previous, float(member["position"]))
            _ensure_value_driver(key, obj, block, source_path, expression)
            managed_paths.add(block.path_from_id("value"))
        previous = float(member["position"])

    clear_shape_to_basis(controller, key.key_blocks[0])
    return managed_paths, property_name


def rescan_key(key, obj=None) -> None:
    sync_key(key, obj)


def _sync_key_impl(key, obj=None) -> bool:
    _normalize_linked_target_names(key)
    managed_paths = set()
    controller_properties = set()
    for group in groups_from_names(key):
        if group.get("controller"):
            group_paths, property_name = _sync_managed_group(key, group, obj)
            managed_paths.update(group_paths)
            if property_name is not None:
                controller_properties.add(property_name)
    _remove_orphan_addon_drivers(key, managed_paths)
    if obj is not None:
        orphan_paths = set()
        for property_name in list(obj.keys()):
            if property_name.startswith(_CONTROLLER_VALUE_PREFIX) and property_name not in controller_properties:
                orphan_paths.add(f'["{property_name}"]')
                del obj[property_name]
        _remove_action_paths(obj, orphan_paths)
    return False


def sync_key(key, obj=None) -> bool:
    key_id = key.session_uid
    if key_id in _SYNCING_KEYS:
        return False
    _SYNCING_KEYS.add(key_id)
    try:
        return _sync_key_impl(key, obj)
    finally:
        _SYNCING_KEYS.remove(key_id)


def sync_all(bpy_data) -> None:
    synced_keys = set()
    for obj in bpy_data.objects:
        if obj.type != "MESH" or obj.data.shape_keys is None:
            continue
        enforce_controller_selection(obj)
        key_id = obj.data.shape_keys.session_uid
        if key_id in synced_keys:
            continue
        synced_keys.add(key_id)
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
