from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from copy import deepcopy

from bpy.app.translations import pgettext_iface

from .fbx_binary import FBXBinary, Node, array_property, string_property
from .metadata import parse_target_name

_FBX_NAME_SEPARATOR = "\x00\x01"
_FBX_SHAPE_SUFFIX = "SubDeformer"


def _message(source: str, **values) -> str:
    return pgettext_iface(source).format(**values)


def _class_name(name: str) -> str:
    return f"{name}{_FBX_NAME_SEPARATOR}{_FBX_SHAPE_SUFFIX}"


def _object_id(node: Node) -> int:
    return int(node.prop(0))


def _object_type(node: Node) -> str:
    return str(node.prop(2, ""))


def _logical_name(value) -> str:
    return str(value).split(_FBX_NAME_SEPARATOR, 1)[0]


def _objects_and_connections(scene: FBXBinary):
    objects = next((node for node in scene.roots if node.name == b"Objects"), None)
    connections = next((node for node in scene.roots if node.name == b"Connections"), None)
    if objects is None or connections is None:
        raise ValueError(_message("FBX is missing Objects or Connections"))
    return objects, connections


def _connection_values(node: Node):
    if len(node.properties) < 3:
        return None
    return str(node.prop(0)), int(node.prop(1)), int(node.prop(2))


def _is_removed_connection(node: Node, remove_ids: set[int]) -> bool:
    values = _connection_values(node)
    return node.name == b"C" and values is not None and (values[1] in remove_ids or values[2] in remove_ids)


def _set_child_property(node: Node, name: bytes, prop_index: int, prop) -> None:
    child = node.child(name)
    if child is None:
        node.children.append(Node(name, [prop]))
    elif len(child.properties) <= prop_index:
        child.properties.extend([string_property("")] * (prop_index + 1 - len(child.properties)))
        child.properties[prop_index] = prop
    else:
        child.properties[prop_index] = prop


def _next_object_id(object_nodes: dict[int, Node]) -> int:
    candidate = max(object_nodes, default=0) + 1
    if candidate >= 2**63:
        raise OverflowError("FBX object identifier space is exhausted")
    return candidate


def _append_flat_tail_target(
    objects: Node,
    connections: Node,
    object_nodes: dict[int, Node],
    channel_name: str,
    highest_geometry_id: int,
    canonical_channel_id: int,
) -> int:
    source = object_nodes[highest_geometry_id]
    duplicate = deepcopy(source)
    duplicate_id = _next_object_id(object_nodes)
    duplicate.properties[0] = connections_id_property(duplicate_id)
    source_name = str(source.prop(1, ""))
    suffix = source_name.split(_FBX_NAME_SEPARATOR, 1)[1] if _FBX_NAME_SEPARATOR in source_name else "Geometry"
    duplicate.properties[1] = string_property(
        f"{channel_name}@1{_FBX_NAME_SEPARATOR}{suffix}"
    )
    objects.children.append(duplicate)
    object_nodes[duplicate_id] = duplicate
    connections.children.append(
        Node(
            b"C",
            [
                string_property("OO"),
                connections_id_property(duplicate_id),
                connections_id_property(canonical_channel_id),
            ],
        )
    )
    return duplicate_id


def transform_scene(scene: FBXBinary) -> int:
    objects, connections = _objects_and_connections(scene)
    object_nodes = {
        _object_id(node): node
        for node in objects.children
        if node.name in {b"Geometry", b"Deformer", b"Model"} and node.properties
    }
    connections_data = []
    for node in connections.children_named(b"C"):
        values = _connection_values(node)
        if values is not None:
            connections_data.append((node, *values))

    geometry_channels = defaultdict(list)
    geometry_names = {}
    channel_parents = defaultdict(list)
    for _node, relation, child_id, parent_id in connections_data:
        if relation != "OO":
            continue
        child = object_nodes.get(child_id)
        parent = object_nodes.get(parent_id)
        if child is None or parent is None:
            continue
        if child.name == b"Geometry" and _object_type(child) == "Shape":
            geometry_channels[child_id].append(parent_id)
            geometry_names[child_id] = _logical_name(child.prop(1, ""))
        if child.name == b"Deformer" and _object_type(child) == "BlendShapeChannel":
            channel_parents[child_id].append(parent_id)

    by_blendshape = defaultdict(lambda: defaultdict(list))
    controllers_by_blendshape = defaultdict(lambda: defaultdict(list))
    for geometry_id, channels in geometry_channels.items():
        logical_name = geometry_names[geometry_id]
        spec = parse_target_name(logical_name)
        if spec is None:
            for channel_id in channels:
                for blendshape_id in channel_parents.get(channel_id, []):
                    controllers_by_blendshape[blendshape_id][logical_name].append((geometry_id, channel_id))
            continue
        for channel_id in channels:
            for blendshape_id in channel_parents.get(channel_id, []):
                by_blendshape[blendshape_id][spec.channel].append(
                    (spec.position, geometry_id, channel_id)
                )

    changed = 0
    remove_ids: set[int] = set()
    for blendshape_id, groups in by_blendshape.items():
        for channel_name, entries in groups.items():
            entries.sort(key=lambda item: item[0])
            positions = [entry[0] for entry in entries]
            if len(positions) != len(set(positions)):
                raise ValueError(
                    _message(
                        "Duplicate in-between position in FBX channel {channel}",
                        channel=channel_name,
                    )
                )
            if positions[-1] < 1.0:
                _highest_position, highest_geometry_id, highest_channel_id = entries[-1]
                flat_tail_geometry_id = _append_flat_tail_target(
                    objects,
                    connections,
                    object_nodes,
                    channel_name,
                    highest_geometry_id,
                    highest_channel_id,
                )
                entries.append((1.0, flat_tail_geometry_id, highest_channel_id))
                positions.append(1.0)
                changed += 1
            _canonical_position, _canonical_geometry_id, canonical_channel_id = entries[-1]
            canonical_channel = object_nodes[canonical_channel_id]
            canonical_channel.properties[1] = string_property(_class_name(channel_name))
            full_weights = [position * 100.0 for position in positions]
            _set_child_property(canonical_channel, b"FullWeights", 0, array_property(full_weights))

            # A controller Shape Key is intentionally empty and exists only to
            # drive the target values in Blender. It must not become an extra
            # empty blend shape in the exported FBX.
            for controller_geometry_id, controller_channel_id in controllers_by_blendshape[blendshape_id].get(
                channel_name, []
            ):
                remove_ids.add(controller_geometry_id)
                remove_ids.add(controller_channel_id)
                changed += 1

            for _position, geometry_id, channel_id in entries:
                if channel_id == canonical_channel_id:
                    continue
                remove_ids.add(channel_id)
                for connection_node, _relation, child_id, parent_id in connections_data:
                    if child_id == geometry_id and parent_id == channel_id:
                        connections.children.remove(connection_node)
                    elif child_id == channel_id and parent_id in channel_parents.get(channel_id, []):
                        connections.children.remove(connection_node)
                changed += 1

            # FBX SDK indexes FullWeights and target Shapes together. Remove the
            # exporter's original links before appending the canonical order.
            target_geometry_ids = {geometry_id for _position, geometry_id, _channel_id in entries}
            expected_target_ids = [geometry_id for _position, geometry_id, _channel_id in entries]
            current_target_ids = [
                values[1]
                for node in connections.children
                if node.name == b"C"
                and (values := _connection_values(node)) is not None
                and values[0] == "OO"
                and values[1] in target_geometry_ids
                and values[2] == canonical_channel_id
            ]
            if current_target_ids != expected_target_ids:
                connections.children[:] = [
                    node
                    for node in connections.children
                    if not (
                        node.name == b"C"
                        and (values := _connection_values(node)) is not None
                        and values[0] == "OO"
                        and values[1] in target_geometry_ids
                        and values[2] == canonical_channel_id
                    )
                ]
                for geometry_id in expected_target_ids:
                    connections.children.append(
                        Node(
                            b"C",
                            [
                                string_property("OO"),
                                connections_id_property(geometry_id),
                                connections_id_property(canonical_channel_id),
                            ],
                        )
                    )
                changed += 1

    if remove_ids:
        objects.children[:] = [node for node in objects.children if _object_id(node) not in remove_ids]
        connections.children[:] = [
            node
            for node in connections.children
            if not _is_removed_connection(node, remove_ids)
        ]
    return changed


def connections_id_property(value: int):
    from .fbx_binary import Property

    return Property(b"L", value)


def process_file(source: str, destination: str) -> int:
    scene = FBXBinary.read(source)
    changed = transform_scene(scene)
    temp_dir = os.path.dirname(destination) or "."
    fd, temp_path = tempfile.mkstemp(prefix="fbxi-", suffix=".fbx", dir=temp_dir)
    os.close(fd)
    try:
        scene.write(temp_path)
        os.replace(temp_path, destination)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return changed
