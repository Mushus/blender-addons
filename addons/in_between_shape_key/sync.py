from __future__ import annotations

import base64
from collections import defaultdict

from .metadata import format_target_name, parse_target_name
from .runtime import get_state

_SYNCING_KEYS: set[int] = set()
_CONTROLLER_VALUE_PREFIX = "_fbxi_inbetween_value_"


def controller_value_property(channel: str) -> str:
    encoded = base64.urlsafe_b64encode(channel.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{_CONTROLLER_VALUE_PREFIX}{encoded}"


def controller_value_path(channel: str) -> str:
    return f'["{controller_value_property(channel)}"]'


def set_controller_value(obj, channel: str, value: float) -> None:
    property_name = controller_value_property(channel)
    if property_name not in obj:
        raise KeyError(f"In-Between controller value is unavailable: {channel}")
    obj[property_name] = max(0.0, min(1.0, float(value)))


def get_controller_value(obj, channel: str) -> float:
    property_name = controller_value_property(channel)
    if property_name not in obj:
        raise KeyError(f"In-Between controller value is unavailable: {channel}")
    return float(obj[property_name])


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
        if not 0.0 <= spec.weight <= 100.0:
            continue
        members.append({"index": index, "name": block.name, "weight": spec.weight})
    return sorted(members, key=lambda item: item["weight"])


def _driver_expression(previous: float, weight: float) -> str:
    if weight == 0.0:
        return "1.0"
    span = weight - previous
    return f"min(max((fbxi_controller * 100.0 - {previous:.12g}) / {span:.12g}, 0.0), 1.0)"


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


def _ensure_value_driver(key, obj, block, source_path: str, expression: str) -> None:
    fcurve = _driver_fcurve(key, block)
    if fcurve is None:
        fcurve = block.driver_add("value")
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


def _ensure_controller_value(obj, controller) -> tuple[str, str]:
    property_name = controller_value_property(controller.name)
    if property_name not in obj:
        obj[property_name] = max(0.0, min(1.0, float(controller.value)))
    obj.id_properties_ui(property_name).update(
        min=0.0,
        max=1.0,
        soft_min=0.0,
        soft_max=1.0,
        description=f"Value for In-Between controller {controller.name}",
    )
    return property_name, controller_value_path(controller.name)


def _sync_managed_group(key, group: dict, obj=None) -> tuple[set[str], str | None]:
    controller = _controller_block(key, group)
    if controller is None or not group.get("controller"):
        return set(), None

    if obj is None:
        return set(), None
    members = _target_members(key, group["channel"])
    if not members:
        return set(), None

    _set_relative_chain(key, members)
    property_name, source_path = _ensure_controller_value(obj, controller)
    _ensure_value_driver(key, obj, controller, source_path, "fbxi_controller")
    managed_paths = {controller.path_from_id("value")}
    previous = 0.0
    for member in members:
        block = key.key_blocks.get(member["name"])
        if block is not None:
            expression = _driver_expression(previous, float(member["weight"]))
            _ensure_value_driver(key, obj, block, source_path, expression)
            managed_paths.add(block.path_from_id("value"))
        previous = float(member["weight"])

    clear_shape_to_basis(controller, key.key_blocks[0])
    return managed_paths, property_name


def rescan_key(key, obj=None) -> None:
    sync_key(key, obj)


def _sync_key_impl(key, obj=None) -> bool:
    _sync_group_tracks(key)
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
        for property_name in list(obj.keys()):
            if property_name.startswith(_CONTROLLER_VALUE_PREFIX) and property_name not in controller_properties:
                del obj[property_name]
    return False


def _token(value) -> str:
    return str(value.as_pointer())


def _key_tracks(key) -> list[dict]:
    state = get_state()
    if state is None:
        return []
    all_tracks = state.setdefault("group_tracks", {})
    return all_tracks.setdefault(_token(key), [])


def _bootstrap_tracks(key, tracks: list[dict]) -> None:
    tracked_controllers = {track["controller_token"] for track in tracks}
    for group in groups_from_names(key):
        controller = key.key_blocks.get(group.get("controller", ""))
        if controller is None or _token(controller) in tracked_controllers:
            continue
        tracks.append(
            {
                "controller_token": _token(controller),
                "channel": controller.name,
                "members": {
                    _token(key.key_blocks[member["name"]]): float(member["weight"])
                    for member in group["members"]
                },
            }
        )
        tracked_controllers.add(_token(controller))


def _rename_tracked_group(key, track: dict, blocks_by_token: dict[str, object]) -> None:
    controller = blocks_by_token.get(track["controller_token"])
    if controller is None:
        return
    old_channel = track["channel"]
    members = {
        token: (blocks_by_token[token], weight)
        for token, weight in track["members"].items()
        if token in blocks_by_token
    }

    candidates = set()
    if controller.name != old_channel and controller.name != "Basis" and "@" not in controller.name:
        candidates.add(controller.name.strip())
    current_weights = {}
    for token, (block, stored_weight) in members.items():
        spec = parse_target_name(block.name)
        current_weights[token] = spec.weight if spec is not None else stored_weight
        if spec is not None and spec.channel != old_channel:
            candidates.add(spec.channel)
    if len(candidates) > 1:
        return
    channel = next(iter(candidates), old_channel)
    if not channel or "@" in channel:
        return

    desired = [(controller, channel)]
    desired.extend(
        (block, format_target_name(channel, current_weights[token]))
        for token, (block, _weight) in members.items()
    )
    desired_names = [name for _block, name in desired]
    if len(desired_names) != len(set(desired_names)):
        return
    moving = {_token(block) for block, _name in desired}
    if any(
        (occupied := key.key_blocks.get(name)) is not None and _token(occupied) not in moving
        for _block, name in desired
    ):
        return

    changing = [(block, name) for block, name in desired if block.name != name]
    for index, (block, _name) in enumerate(changing):
        block.name = f"__FBXI_RENAME_{_token(key)}_{index}__"
    for block, name in changing:
        block.name = name
    if any(block.name != name for block, name in desired):
        return

    track["channel"] = channel
    track["members"] = {
        token: current_weights[token]
        for token in members
    }


def _attach_named_members(key, track: dict, blocks_by_token: dict[str, object]) -> None:
    controller = blocks_by_token.get(track["controller_token"])
    if controller is None:
        return
    channel = track["channel"]
    members = track["members"]
    for block in key.key_blocks:
        spec = parse_target_name(block.name)
        if spec is not None and spec.channel == channel:
            members[_token(block)] = spec.weight
    track["members"] = {
        token: weight
        for token, weight in members.items()
        if token in blocks_by_token
    }


def _sync_group_tracks(key) -> None:
    tracks = _key_tracks(key)
    blocks_by_token = {_token(block): block for block in key.key_blocks}
    tracks[:] = [track for track in tracks if track["controller_token"] in blocks_by_token]
    _bootstrap_tracks(key, tracks)
    for track in tracks:
        _rename_tracked_group(key, track, blocks_by_token)
        _attach_named_members(key, track, blocks_by_token)
    _bootstrap_tracks(key, tracks)


def sync_key(key, obj=None, *, sync_ui=True) -> bool:
    key_id = key.as_pointer()
    if key_id in _SYNCING_KEYS:
        return False
    _SYNCING_KEYS.add(key_id)
    try:
        changed = _sync_key_impl(key, obj)
        if sync_ui and obj is not None:
            from .ui_state import sync_object

            sync_object(obj)
        return changed
    finally:
        _SYNCING_KEYS.remove(key_id)


def sync_all(bpy_data, *, sync_ui=False) -> None:
    state = get_state()
    if state is not None:
        tracks = state.setdefault("group_tracks", {})
        live_key_tokens = {
            _token(obj.data.shape_keys)
            for obj in bpy_data.objects
            if obj.type == "MESH" and obj.data.shape_keys is not None
        }
        for token in set(tracks) - live_key_tokens:
            del tracks[token]
    synced_keys = set()
    for obj in bpy_data.objects:
        if obj.type != "MESH" or obj.data.shape_keys is None:
            continue
        enforce_controller_selection(obj)
        if obj.mode != "OBJECT":
            continue
        key_token = _token(obj.data.shape_keys)
        if key_token in synced_keys:
            continue
        synced_keys.add(key_token)
        sync_key(obj.data.shape_keys, obj, sync_ui=False)
    if sync_ui:
        from .ui_state import sync_all as sync_all_ui

        sync_all_ui(bpy_data)


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
