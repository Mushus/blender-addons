from __future__ import annotations

import bpy

from .exporter import export_with_inbetweens
from .metadata import format_target_name, parse_target_name
from .sync import (
    clear_shape_to_basis,
    controller_group,
    group_for_channel,
    rescan_key,
    sync_key,
)
from .validation import validate_all_meshes


def _active_key(context):
    obj = context.object
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return None
    return obj.data.shape_keys


def _capture_current_mix(obj, context):
    context.view_layer.update()
    evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return [vertex.co.copy() for vertex in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()


def _channel_from_context(obj) -> str:
    active = obj.active_shape_key
    if active is None or active.name == "Basis":
        return ""
    spec = parse_target_name(active.name)
    return spec.channel if spec is not None else active.name.strip()


def _validate_range(channel: str, start: float, end: float, step: float) -> str | None:
    if not channel or "@" in channel:
        return "Channel must be non-empty and must not contain @"
    if not 1.0 <= start <= 100.0 or not 1.0 <= end <= 100.0:
        return "Start and End must be between 1 and 100"
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


class FBXI_OT_add_at_current_value(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.add_at_current_value"
    bl_label = "Add In-Between at Current Value"
    bl_description = "Copy the current mix into an in-between Shape Key at the active controller value"

    @classmethod
    def poll(cls, context) -> bool:
        obj = context.object
        return (
            obj is not None
            and obj.type == "MESH"
            and obj.data.shape_keys is not None
            and obj.mode == "OBJECT"
        )

    def execute(self, context):
        obj = context.object
        key = _active_key(context)
        active = obj.active_shape_key
        if key is None or active is None or active.name == "Basis":
            self.report({"ERROR"}, "Select a Shape Key controller first")
            return {"CANCELLED"}

        active_spec = parse_target_name(active.name)
        group = controller_group(key, active.name)
        if group is None and active_spec is not None:
            group = group_for_channel(key, active_spec.channel)
            if group is None:
                self.report({"ERROR"}, "Select the ordinary Shape Key controller, not an unmanaged target")
                return {"CANCELLED"}
            controller = key.key_blocks.get(group.get("controller", ""))
        else:
            controller = active

        if controller is None or parse_target_name(controller.name) is not None:
            self.report({"ERROR"}, "The active Shape Key is not a controller")
            return {"CANCELLED"}

        channel = controller.name.strip()
        if not channel or "@" in channel:
            self.report({"ERROR"}, "Controller name must be non-empty and must not contain @")
            return {"CANCELLED"}

        weight = round(float(controller.value) * 100.0, 6)
        if not 1.0 <= weight < 100.0:
            self.report({"ERROR"}, "Set the controller Value between 0.01 and 0.99 before adding an in-between")
            return {"CANCELLED"}

        target_name = format_target_name(channel, weight)
        if key.key_blocks.get(target_name) is not None:
            self.report({"ERROR"}, f"In-between already exists: {target_name}")
            return {"CANCELLED"}

        is_new_controller = group is None
        endpoint_name = format_target_name(channel, 100.0)
        if is_new_controller and key.key_blocks.get(endpoint_name) is not None:
            self.report({"ERROR"}, f"Cannot convert controller because {endpoint_name} already exists")
            return {"CANCELLED"}

        original_shape = list(point.co.copy() for point in controller.data)
        current_mix = _capture_current_mix(obj, context)
        endpoint = None
        if is_new_controller:
            endpoint = obj.shape_key_add(name=endpoint_name, from_mix=False)
            for point, coordinate in zip(endpoint.data, original_shape, strict=True):
                point.co = coordinate

        target = obj.shape_key_add(name=target_name, from_mix=False)
        for point, coordinate in zip(target.data, current_mix, strict=True):
            point.co = coordinate

        if is_new_controller:
            basis = key.key_blocks[0]
            clear_shape_to_basis(controller, basis)

        sync_key(key, obj)

        obj.active_shape_key_index = key.key_blocks.find(target.name)
        self.report({"INFO"}, f"Added {target_name}")
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
        if spec.weight >= 100.0:
            self.report({"ERROR"}, "The @100 endpoint cannot be removed")
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


class FBXI_OT_drag_target(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.drag_target"
    bl_label = "Move In-Between Key"
    bl_description = "Drag this in-between key to a new timeline position"
    bl_options = {"BLOCKING", "GRAB_CURSOR"}

    target_name: bpy.props.StringProperty(name="Target")
    weight: bpy.props.FloatProperty(name="Position", min=1.0, max=99.0, precision=3)
    track_start: bpy.props.FloatProperty(name="Track Start", default=0.1, min=0.0, max=1.0)
    track_end: bpy.props.FloatProperty(name="Track End", default=0.81, min=0.0, max=1.0)

    _DRAG_THRESHOLD_PX = 3

    @classmethod
    def poll(cls, context) -> bool:
        obj = context.object
        return obj is not None and obj.type == "MESH" and obj.data.shape_keys is not None and obj.mode == "OBJECT"

    def _target(self, context):
        key = _active_key(context)
        return key, key.key_blocks.get(self.target_name) if key is not None else None

    def _apply_weight(self, context, weight: float) -> bool:
        key, target = self._target(context)
        spec = parse_target_name(self.target_name)
        if key is None or target is None or spec is None:
            return False
        weight = round(max(1.0, min(99.0, float(weight))), 6)
        new_name = format_target_name(spec.channel, weight)
        if new_name != target.name and key.key_blocks.get(new_name) is not None:
            return False
        target.name = new_name
        self.target_name = new_name
        self.weight = weight
        sync_key(key, context.object)
        if context.area is not None:
            context.area.tag_redraw()
        return True

    def invoke(self, context, event):
        if event.value != "PRESS":
            # A release without a press is a UI click, not a drag gesture.
            return {"CANCELLED"}
        key, target = self._target(context)
        spec = parse_target_name(self.target_name)
        if key is None or target is None or spec is None or spec.weight >= 100.0:
            self.report({"ERROR"}, "Select an in-between target below @100")
            return {"CANCELLED"}
        self._original_name = target.name
        self._start_weight = spec.weight
        self._press_x = event.mouse_region_x
        self._track_start_x = context.region.width * self.track_start
        self._track_end_x = context.region.width * max(self.track_start, self.track_end)
        self._moved = False
        self._dragging = False
        self._button_down = event.value == "PRESS"
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            key, target = self._target(context)
            if key is not None and target is not None and target.name != self._original_name:
                target.name = self._original_name
                sync_key(key, context.object)
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE" and self._button_down:
            distance = abs(event.mouse_region_x - self._press_x)
            if not self._dragging and distance >= self._DRAG_THRESHOLD_PX:
                self._dragging = True
            if self._dragging:
                track_width = max(1.0, self._track_end_x - self._track_start_x)
                normalized = (event.mouse_region_x - self._track_start_x) / track_width
                absolute_weight = max(1.0, min(99.0, normalized * 100.0))
                self._moved = self._apply_weight(context, absolute_weight) or self._moved
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                self._button_down = True
                return {"RUNNING_MODAL"}
            if event.value == "RELEASE":
                self._button_down = False
                key, target = self._target(context)
                if key is not None and target is not None:
                    context.object.active_shape_key_index = key.key_blocks.find(target.name)
                return {"FINISHED"}

        return {"RUNNING_MODAL"}


class FBXI_OT_move_target(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.move_target"
    bl_label = "Move In-Between Key"
    bl_description = "Rename this Shape Key target to a new timeline position"

    target_name: bpy.props.StringProperty(name="Target")
    weight: bpy.props.FloatProperty(name="Position", min=1.0, max=99.0, precision=3)

    @classmethod
    def poll(cls, context) -> bool:
        obj = context.object
        return obj is not None and obj.type == "MESH" and obj.data.shape_keys is not None and obj.mode == "OBJECT"

    def invoke(self, context, _event):
        key = _active_key(context)
        target = key.key_blocks.get(self.target_name) if key is not None else None
        spec = parse_target_name(self.target_name)
        if target is None or spec is None or spec.weight >= 100.0:
            self.report({"ERROR"}, "Select an in-between target below @100")
            return {"CANCELLED"}
        self.weight = spec.weight
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        key = _active_key(context)
        target = key.key_blocks.get(self.target_name) if key is not None else None
        spec = parse_target_name(self.target_name)
        if target is None or spec is None or spec.weight >= 100.0:
            self.report({"ERROR"}, "Select an in-between target below @100")
            return {"CANCELLED"}
        weight = round(float(self.weight), 6)
        new_name = format_target_name(spec.channel, weight)
        if not 1.0 <= weight < 100.0:
            self.report({"ERROR"}, "Position must be between 1 and 99")
            return {"CANCELLED"}
        if new_name != target.name and key.key_blocks.get(new_name) is not None:
            self.report({"ERROR"}, f"In-between already exists: {new_name}")
            return {"CANCELLED"}
        target.name = new_name
        sync_key(key, context.object)
        context.object.active_shape_key_index = key.key_blocks.find(new_name)
        return {"FINISHED"}


class FBXI_OT_add_range(bpy.types.Operator):
    bl_idname = "fbx_shape_inbetween.add_range"
    bl_label = "Add In-Between Range"
    bl_description = "Create Shape Keys for the selected channel and weight range"

    channel: bpy.props.StringProperty(name="Channel")
    start: bpy.props.FloatProperty(name="Start", default=25.0, min=1.0, max=100.0)
    end: bpy.props.FloatProperty(name="End", default=100.0, min=1.0, max=100.0)
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
    start: bpy.props.FloatProperty(name="Start", default=25.0, min=1.0, max=100.0)
    end: bpy.props.FloatProperty(name="End", default=100.0, min=1.0, max=100.0)
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
