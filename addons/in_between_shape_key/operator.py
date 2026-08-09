from __future__ import annotations

import bpy

from .exporter import export_with_inbetweens
from .metadata import format_target_name, parse_target_name
from .sync import (
    clear_shape_to_basis,
    controller_group,
    get_controller_value,
    rescan_key,
    sync_key,
)
from .validation import validate_all_meshes


def _active_key(context):
    obj = context.object
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return None
    return obj.data.shape_keys


def _has_multiple_selected_shape_keys(key) -> bool:
    return sum(bool(block.select) for block in key.key_blocks) > 1


def _existing_shape_key_items(operator, context):
    key = _active_key(context)
    if key is None:
        return []
    items = []
    for block in key.key_blocks:
        if block.name == "Basis" or block.name == operator.controller_name:
            continue
        if parse_target_name(block.name) is not None or controller_group(key, block.name) is not None:
            continue
        items.append((block.name, block.name, "Add this existing Shape Key as an In-Between"))
    return items


def _channel_from_context(obj) -> str:
    active = obj.active_shape_key
    if active is None or active.name == "Basis":
        return ""
    spec = parse_target_name(active.name)
    return spec.channel if spec is not None else active.name.strip()


def _validate_range(channel: str, start: float, end: float, step: float) -> str | None:
    if not channel or "@" in channel:
        return "Channel must be non-empty and must not contain @"
    if not 0.0 <= start <= 100.0 or not 0.0 <= end <= 100.0:
        return "Start and End must be between 0 and 100"
    if start > end:
        return "Start must not be greater than End"
    if step <= 0.0:
        return "Step must be greater than 0"
    return None


def _weights(start: float, end: float, step: float) -> list[float]:
    result = []
    value = start
    while value <= end + 1e-6:
        result.append(round(value, 6))
        value += step
    return result


class FBXI_OT_rescan_groups(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.rescan_groups"
    bl_label = "Rescan In-Between Groups"
    bl_description = "Re-evaluate Shape Key groups from current names"

    @classmethod
    def poll(cls, context) -> bool:
        return _active_key(context) is not None

    def execute(self, context):
        rescan_key(_active_key(context), context.object)
        self.report({"INFO"}, "Shape Key in-between groups re-evaluated")
        return {"FINISHED"}


class FBXI_OT_validate(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.validate"
    bl_label = "Validate In-Between Shape Keys"
    bl_description = "Validate Shape Key names and in-between weights"

    def execute(self, _context):
        result = validate_all_meshes(bpy.data)
        for message in result.warnings:
            self.report({"WARNING"}, message)
        if result.errors:
            self.report({"ERROR"}, result.errors[0])
            return {"CANCELLED"}
        self.report({"INFO"}, "Shape Key in-between validation passed")
        return {"FINISHED"}


class FBXI_OT_add_existing_key(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.add_existing_key"
    bl_label = "Add to In-Between"
    bl_description = "Choose an existing Shape Key to add at the controller's current value"

    controller_name: bpy.props.StringProperty(name="Controller", options={"HIDDEN"})
    source_name: bpy.props.EnumProperty(
        name="Shape Key",
        description="Existing Shape Key to add as an In-Between",
        items=_existing_shape_key_items,
    )

    @classmethod
    def poll(cls, context) -> bool:
        obj = context.object
        return (
            obj is not None
            and obj.type == "MESH"
            and obj.data.shape_keys is not None
            and obj.mode == "OBJECT"
        )

    def invoke(self, context, _event):
        if not _existing_shape_key_items(self, context):
            self.report({"ERROR"}, "No ordinary existing Shape Keys are available")
            return {"CANCELLED"}
        self.source_name = _existing_shape_key_items(self, context)[0][0]
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        obj = context.object
        key = _active_key(context)
        layout = self.layout
        layout.label(text=f"Controller: {self.controller_name}")
        if key is not None:
            controller = key.key_blocks.get(self.controller_name)
            if controller is not None:
                layout.label(
                    text=f"Value: {get_controller_value(obj, controller.name):.3f}"
                )
        layout.prop(self, "source_name", text="Shape Key")

    def execute(self, context):
        obj = context.object
        key = _active_key(context)
        controller = key.key_blocks.get(self.controller_name) if key is not None else None
        source = key.key_blocks.get(self.source_name) if key is not None else None
        if controller is None or source is None:
            self.report({"ERROR"}, "The selected Shape Key is no longer available")
            return {"CANCELLED"}
        if controller.name == "Basis" or parse_target_name(controller.name) is not None:
            self.report({"ERROR"}, "Select an In-Between controller")
            return {"CANCELLED"}
        if source == key.key_blocks[0] or source == controller or parse_target_name(source.name) is not None:
            self.report({"ERROR"}, "Select an ordinary existing Shape Key")
            return {"CANCELLED"}
        if controller_group(key, source.name) is not None:
            self.report({"ERROR"}, "An In-Between controller cannot be used as a target")
            return {"CANCELLED"}

        weight = round(get_controller_value(obj, controller.name) * 100.0, 6)
        if not 0.0 <= weight <= 100.0:
            self.report({"ERROR"}, "Set the controller Value between 0.0 and 1.0 before adding an in-between")
            return {"CANCELLED"}

        target_name = format_target_name(controller.name.strip(), weight)
        if key.key_blocks.get(target_name) is not None:
            self.report({"ERROR"}, f"In-between already exists: {target_name}")
            return {"CANCELLED"}
        source.name = target_name
        sync_key(key, obj)
        obj.active_shape_key_index = key.key_blocks.find(target_name)
        self.report({"INFO"}, f"Added existing Shape Key as {target_name}")
        return {"FINISHED"}


class FBXI_OT_convert_to_inbetween(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.convert_to_inbetween"
    bl_label = "Convert to In-Between Shape Key"
    bl_description = "Convert this Shape Key into an in-between controller with an initial @100 target"

    @classmethod
    def poll(cls, context) -> bool:
        obj = context.object
        if obj is None or obj.type != "MESH" or obj.data.shape_keys is None or obj.mode != "OBJECT":
            return False
        active = obj.active_shape_key
        if active is None or active.name == "Basis" or "@" in active.name:
            return False
        key = obj.data.shape_keys
        if _has_multiple_selected_shape_keys(key):
            return False
        endpoint_name = format_target_name(active.name.strip(), 100.0)
        return key.key_blocks.get(endpoint_name) is None

    def execute(self, context):
        obj = context.object
        key = _active_key(context)
        active = obj.active_shape_key
        if key is None or active is None or active.name == "Basis":
            self.report({"ERROR"}, "Select a Shape Key controller first")
            return {"CANCELLED"}

        if "@" in active.name:
            self.report({"ERROR"}, "The active Shape Key is already an in-between target")
            return {"CANCELLED"}

        channel = active.name.strip()
        if not channel:
            self.report({"ERROR"}, "Controller name must not be empty")
            return {"CANCELLED"}

        endpoint_name = format_target_name(channel, 100.0)
        if key.key_blocks.get(endpoint_name) is not None:
            self.report({"ERROR"}, f"Cannot convert controller because {endpoint_name} already exists")
            return {"CANCELLED"}

        original_shape = list(point.co.copy() for point in active.data)
        endpoint = obj.shape_key_add(name=endpoint_name, from_mix=False)
        for point, coordinate in zip(endpoint.data, original_shape, strict=True):
            point.co = coordinate

        basis = key.key_blocks[0]
        clear_shape_to_basis(active, basis)
        sync_key(key, obj)

        obj.active_shape_key_index = key.key_blocks.find(active.name)
        self.report({"INFO"}, f"Converted {channel} to In-Between Shape Key")
        return {"FINISHED"}


class FBXI_OT_remove_target(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.remove_target"
    bl_label = "Remove In-Between Target"
    bl_description = "Remove this in-between Shape Key target"

    target_name: bpy.props.StringProperty(name="Target")

    @classmethod
    def poll(cls, context) -> bool:
        obj = context.object
        return obj is not None and obj.type == "MESH" and obj.data.shape_keys is not None and obj.mode == "OBJECT"

    def execute(self, context):
        key = _active_key(context)
        target = key.key_blocks.get(self.target_name) if key is not None else None
        spec = parse_target_name(self.target_name)
        if target is None or spec is None:
            self.report({"ERROR"}, "Select an in-between target")
            return {"CANCELLED"}
        obj = context.object
        obj.shape_key_remove(target)
        from .sync import sync_key

        sync_key(key, obj)
        self.report({"INFO"}, f"Removed {self.target_name}")
        return {"FINISHED"}


class FBXI_OT_select_target(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.select_target"
    bl_label = "Select In-Between Target"
    bl_description = "Select this Shape Key target"

    target_name: bpy.props.StringProperty(name="Target")

    @classmethod
    def poll(cls, context) -> bool:
        obj = context.object
        return obj is not None and obj.type == "MESH" and obj.data.shape_keys is not None

    def execute(self, context):
        key = _active_key(context)
        target = key.key_blocks.get(self.target_name) if key is not None else None
        if target is None:
            self.report({"ERROR"}, "Select an existing Shape Key target")
            return {"CANCELLED"}
        context.object.active_shape_key_index = key.key_blocks.find(target.name)
        return {"FINISHED"}


class FBXI_OT_add_range(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.add_range"
    bl_label = "Add In-Between Range"
    bl_description = "Create Shape Keys for the selected channel and weight range"

    channel: bpy.props.StringProperty(name="Channel")
    start: bpy.props.FloatProperty(name="Start", default=25.0, min=0.0, max=100.0)
    end: bpy.props.FloatProperty(name="End", default=100.0, min=0.0, max=100.0)
    step: bpy.props.FloatProperty(name="Step", default=25.0, min=0.01, max=100.0)

    @classmethod
    def poll(cls, context) -> bool:
        return _active_key(context) is not None

    def execute(self, context):
        obj = context.object
        key = _active_key(context)
        channel = self.channel.strip() or _channel_from_context(obj)
        start, end, step = float(self.start), float(self.end), float(self.step)
        error = _validate_range(channel, start, end, step)
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}

        existing = {
            (spec.channel, spec.weight)
            for block in key.key_blocks
            if (spec := parse_target_name(block.name)) is not None
        }
        created = 0
        for weight in _weights(start, end, step):
            if (channel, weight) in existing:
                continue
            obj.shape_key_add(name=format_target_name(channel, weight), from_mix=False)
            created += 1
        rescan_key(key, obj)
        self.report({"INFO"}, f"Added {created} in-between Shape Key(s)")
        return {"FINISHED"}


class FBXI_OT_remove_range(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.remove_range"
    bl_label = "Remove In-Between Range"
    bl_description = "Remove Shape Keys in the selected channel and weight range"

    channel: bpy.props.StringProperty(name="Channel")
    start: bpy.props.FloatProperty(name="Start", default=25.0, min=0.0, max=100.0)
    end: bpy.props.FloatProperty(name="End", default=100.0, min=0.0, max=100.0)
    step: bpy.props.FloatProperty(name="Step", default=25.0, min=0.01, max=100.0)

    @classmethod
    def poll(cls, context) -> bool:
        return _active_key(context) is not None

    def execute(self, context):
        obj = context.object
        key = _active_key(context)
        channel = self.channel.strip() or _channel_from_context(obj)
        start, end, step = float(self.start), float(self.end), float(self.step)
        error = _validate_range(channel, start, end, step)
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}

        targets = []
        for index, block in enumerate(key.key_blocks):
            spec = parse_target_name(block.name)
            if spec is not None and spec.channel == channel and start <= spec.weight <= end:
                targets.append(index)
        for index in reversed(targets):
            obj.shape_key_remove(key.key_blocks[index])
        rescan_key(key, obj)
        self.report({"INFO"}, f"Removed {len(targets)} in-between Shape Key(s)")
        return {"FINISHED"}


def make_export_operator():
    import importlib

    fbx_module = importlib.import_module("io_scene_fbx")
    base = fbx_module.ExportFBX

    def execute(self, context):
        return export_with_inbetweens(self, context)

    return type(
        "FBXI_OT_export_fbx_settings",
        (base,),
        {
            "bl_idname": "export_scene.fbx_shape_inbetween",
            "bl_label": "Export In Between Shape Key",
            "execute": execute,
            "_fbx_module": fbx_module,
        },
    )
