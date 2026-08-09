from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from zip_utils import extract_zip


def parse_args():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon-root")
    parser.add_argument("--zip")
    return parser.parse_args(raw)


def _find_nodes(node, name):
    result = []
    if node.name == name:
        result.append(node)
    for child in node.children:
        result.extend(_find_nodes(child, name))
    return result


def _connections(scene):
    root = next(node for node in scene.roots if node.name == b"Connections")
    result = []
    for node in root.children_named(b"C"):
        if len(node.properties) >= 3:
            result.append((node.prop(0), int(node.prop(1)), int(node.prop(2))))
    return result


class _RecordingLayout:
    """Small UILayout stand-in for exercising the panel draw callback headlessly."""

    def __init__(self, events=None) -> None:
        self.events = events if events is not None else []

    def separator(self):
        self.events.append(("separator",))

    def label(self, *, text="", **_kwargs):
        self.events.append(("label", text))

    def prop(self, data, property_name, **_kwargs):
        self.events.append(("prop", getattr(data, "name", ""), property_name))

    def box(self):
        self.events.append(("box",))
        return _RecordingLayout(self.events)

    def row(self, **_kwargs):
        self.events.append(("row",))
        return _RecordingLayout(self.events)

    def column(self, **_kwargs):
        self.events.append(("column",))
        return _RecordingLayout(self.events)

    def grid_flow(self, **_kwargs):
        self.events.append(("grid_flow",))
        return _RecordingLayout(self.events)

    def split(self, **_kwargs):
        self.events.append(("split",))
        return _RecordingLayout(self.events)

    def template_color_ramp(self, data, property_name, **_kwargs):
        self.events.append(("color_ramp", data.name, property_name))

    def operator(self, operator_id, **_kwargs):
        self.events.append(("operator", operator_id))
        self.events.append(("operator_text", operator_id, _kwargs.get("text")))
        return SimpleNamespace()

    def menu(self, menu_id, **_kwargs):
        self.events.append(("menu", menu_id))


class _RecordingPanel:
    def __init__(self) -> None:
        self.layout = _RecordingLayout()


def _set_controller_value(obj, controller, value: float) -> None:
    from in_between_shape_key.sync import set_controller_value

    set_controller_value(obj, controller.name, value)
    bpy.context.view_layer.update()


def _flush_position_updates() -> None:
    from in_between_shape_key.ui_state import _flush_pending_positions

    _flush_pending_positions(force=True)


def _assert_managed_drivers(obj, key, controller_name: str, target_names: set[str]) -> None:
    from in_between_shape_key.sync import controller_value_path

    controller_path = controller_value_path(controller_name)
    expected_paths = {key.key_blocks[name].path_from_id("value") for name in target_names}
    expected_paths.add(key.key_blocks[controller_name].path_from_id("value"))
    animation_data = key.animation_data
    assert animation_data is not None
    matching = []
    for fcurve in animation_data.drivers:
        variables = fcurve.driver.variables
        if len(variables) != 1 or variables[0].name != "fbxi_controller":
            continue
        target = variables[0].targets[0]
        if target.id == obj and target.data_path == controller_path:
            matching.append(fcurve)
    assert {fcurve.data_path for fcurve in matching} == expected_paths
    assert all(fcurve.driver.type == "SCRIPTED" for fcurve in matching)


def _assert_inbetween_panel_draws(obj):
    from in_between_shape_key.operator import (
        FBXI_OT_convert_to_inbetween,
        FBXI_OT_remove_target,
        FBXI_OT_select_target,
    )
    from in_between_shape_key.ui import draw_shape_key_inbetween, draw_shape_key_specials

    key = obj.data.shape_keys
    empty_menu = _RecordingPanel()
    draw_shape_key_specials(empty_menu, SimpleNamespace(object=None))
    assert not empty_menu.layout.events
    for block in key.key_blocks:
        block.select = block.name == "Smile@0.5"
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)
    labels = [event[1] for event in panel.layout.events if event[0] == "label"]
    assert "Shape Key Controllers" not in labels, panel.layout.events
    assert "@1  Locked" not in labels, panel.layout.events
    assert not any(event[0] == "color_ramp" for event in panel.layout.events), panel.layout.events
    assert sum(event[0] == "grid_flow" for event in panel.layout.events) == 0, panel.layout.events
    assert sum(event[0] == "menu" for event in panel.layout.events) == 1, panel.layout.events
    assert sum(event[0] == "box" for event in panel.layout.events) == 1, panel.layout.events
    assert sum(event == ("operator", FBXI_OT_select_target.bl_idname) for event in panel.layout.events) == 3
    assert sum(
        event == ("operator_text", FBXI_OT_select_target.bl_idname, "")
        for event in panel.layout.events
    ) == 2
    assert sum(event == ("operator", FBXI_OT_remove_target.bl_idname) for event in panel.layout.events) == 2
    positions = [event for event in panel.layout.events if event[0] == "prop" and event[2] == "position"]
    assert len(positions) == 2, panel.layout.events
    from in_between_shape_key.sync import controller_value_path

    controller_values = [
        event
        for event in panel.layout.events
        if event[0] == "prop" and event[2] == controller_value_path("Smile")
    ]
    assert len(controller_values) == 1, panel.layout.events

    # @1 uses the same editable/removable detail row as every other target.
    for block in key.key_blocks:
        block.select = block.name == "Smile@1"
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)
    assert sum(event == ("operator", FBXI_OT_remove_target.bl_idname) for event in panel.layout.events) == 2
    positions = [event for event in panel.layout.events if event[0] == "prop" and event[2] == "position"]
    assert len(positions) == 2, panel.layout.events

    # The controller row is also a valid context for the panel.  This is the
    # case users need when they want to add the first in-between key.
    obj.active_shape_key_index = key.key_blocks.find("Smile")
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)
    labels = [event[1] for event in panel.layout.events if event[0] == "label"]
    assert "Shape Key Controllers" not in labels, panel.layout.events

    # An ordinary unmanaged shape key presents a "Convert to In-Between" action.
    unmanaged = obj.shape_key_add(name="Wink")
    obj.active_shape_key_index = key.key_blocks.find("Wink")
    for block in key.key_blocks:
        block.select = block == unmanaged
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)
    assert any(event == ("operator", FBXI_OT_convert_to_inbetween.bl_idname) for event in panel.layout.events), (
        panel.layout.events
    )

    # Basis and target selections must not add a disabled Convert entry to the
    # Shape Key specials menu.
    for invalid_name in ("Basis", "Smile@0.5"):
        obj.active_shape_key_index = key.key_blocks.find(invalid_name)
        for block in key.key_blocks:
            block.select = block.name == invalid_name
        menu = _RecordingPanel()
        draw_shape_key_specials(menu, SimpleNamespace(object=obj))
        assert not any(
            event == ("operator", FBXI_OT_convert_to_inbetween.bl_idname)
            for event in menu.layout.events
        )

    obj.active_shape_key_index = key.key_blocks.find("Wink")
    for block in key.key_blocks:
        block.select = block == unmanaged
    menu = _RecordingPanel()
    draw_shape_key_specials(menu, SimpleNamespace(object=obj))
    assert any(
        event == ("operator", FBXI_OT_convert_to_inbetween.bl_idname)
        for event in menu.layout.events
    )

    # Multiple tree selections hide Convert instead of presenting a disabled action.
    key.key_blocks["Smile"].select = True
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)
    assert not any(event == ("operator", FBXI_OT_convert_to_inbetween.bl_idname) for event in panel.layout.events), (
        panel.layout.events
    )
    menu = _RecordingPanel()
    draw_shape_key_specials(menu, SimpleNamespace(object=obj))
    assert not any(event == ("operator", FBXI_OT_convert_to_inbetween.bl_idname) for event in menu.layout.events)
    assert not FBXI_OT_convert_to_inbetween.poll(bpy.context)
    obj.shape_key_remove(unmanaged)

    print("Shape Key panel draw test passed (in-between and controller selection)")


def _assert_position_slider_operations():
    from in_between_shape_key.sync import sync_key
    from in_between_shape_key.ui_state import find_entry
    from in_between_shape_key.validation import validate_shape_keys

    # Arrange: a converted controller with one endpoint. The UI slider is a
    # transient adapter; the Shape Key name remains the persisted source of truth.
    mesh = bpy.data.meshes.new("FBXI Position Slider Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new("FBXI Position Slider Object", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.shape_key_add(name="Basis")
    controller = obj.shape_key_add(name="Position")
    controller.data[1].co.y = 1.0
    obj.active_shape_key_index = mesh.shape_keys.key_blocks.find(controller.name)
    assert bpy.ops.fbx_shape_inbetween.convert_to_inbetween() == {"FINISHED"}
    key = mesh.shape_keys
    entry = find_entry(bpy.context.window_manager, obj, "Position@1")
    assert entry is not None
    assert abs(entry.position - 1.0) < 1e-6

    # Act: edit the standard slider's RNA value, then evaluate beyond the new
    # highest target. This exercises the same update callback used by the GUI.
    obj.name = "FBXI Position Slider Renamed Object"
    entry.position = 0.9
    assert key.key_blocks.get("Position@1") is not None
    assert key.key_blocks.get("Position@0.9") is None
    _flush_position_updates()
    _set_controller_value(obj, controller, 0.95)
    bpy.context.view_layer.update()

    # Assert: the key was renamed, @1 is optional, and the final @0.9 target
    # remains fully applied through 100%.
    assert key.key_blocks.get("Position@1") is None
    assert key.key_blocks.get("Position@0.9") is not None
    assert entry.target_name == "Position@0.9"
    assert abs(key.key_blocks["Position@0.9"].value - 1.0) < 1e-6
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    evaluated_mesh = evaluated.to_mesh()
    try:
        assert abs(evaluated_mesh.vertices[1].co.y - 1.0) < 1e-6
    finally:
        evaluated.to_mesh_clear()
    assert validate_shape_keys(key).ok

    # Arrange/Act: create another target, then try to move it onto an occupied
    # position. The adapter must reject the duplicate and restore its slider.
    obj.shape_key_add(name="Position@0.5", from_mix=False)
    sync_key(key, obj)
    duplicate_entry = find_entry(bpy.context.window_manager, obj, "Position@0.5")
    assert duplicate_entry is not None
    duplicate_entry.position = 0.9
    _flush_position_updates()

    # Assert: duplicate positions never rename or overwrite a Shape Key.
    assert key.key_blocks.get("Position@0.5") is not None
    assert key.key_blocks.get("Position@0.9") is not None
    assert abs(duplicate_entry.position - 0.5) < 1e-6
    assert bpy.ops.fbx_shape_inbetween.remove_target(target_name="Position@0.9") == {"FINISHED"}
    assert key.key_blocks.get("Position@0.9") is None
    assert validate_shape_keys(key).ok

    # Arrange/Act: rename only the controller, as Blender users normally do.
    # The still-live drivers identify every target linked to that controller.
    controller.name = "Position Renamed"
    import in_between_shape_key

    in_between_shape_key._sync_ui_timer()

    # Assert: current names alone rebuild group ownership, drivers, and UI rows.
    assert key.key_blocks.get("Position@0.5") is None
    assert key.key_blocks.get("Position Renamed@0.5") is not None
    renamed_entry = find_entry(bpy.context.window_manager, obj, "Position Renamed@0.5")
    assert renamed_entry is not None
    assert abs(renamed_entry.position - 0.5) < 1e-6

    bpy.data.objects.remove(obj, do_unlink=True)
    print("Position slider, parent rename, duplicate rejection, and flat-tail tests passed")


def _assert_zero_position_target():
    from in_between_shape_key.sync import sync_key
    from in_between_shape_key.ui_state import find_entry
    from in_between_shape_key.validation import validate_shape_keys

    # Background: @0 is the lower endpoint, not an invalid or inactive target.
    # With relative Shape Keys it stays at value 1 while later targets blend
    # from its shape as the controller rises above zero.
    # Arrange: convert Thickness and add an existing shape at controller value 0.
    mesh = bpy.data.meshes.new("FBXI Zero Weight Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new("FBXI Zero Weight Object", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.shape_key_add(name="Basis")
    controller = obj.shape_key_add(name="Thickness")
    controller.data[1].co.y = 1.0
    obj.active_shape_key_index = mesh.shape_keys.key_blocks.find(controller.name)
    assert bpy.ops.fbx_shape_inbetween.convert_to_inbetween() == {"FINISHED"}
    key = mesh.shape_keys
    zero_source = obj.shape_key_add(name="Thickness Zero Source")
    zero_source.data[1].co.y = -1.0
    _set_controller_value(obj, controller, 0.0)
    assert bpy.ops.fbx_shape_inbetween.add_existing_key(
        controller_name="Thickness",
        source_name=zero_source.name,
    ) == {"FINISHED"}

    # Assert: zero is accepted by naming, validation, and the native slider.
    zero = key.key_blocks["Thickness@0"]
    endpoint = key.key_blocks["Thickness@1"]
    entry = find_entry(bpy.context.window_manager, obj, zero.name)
    assert entry is not None and abs(entry.position) < 1e-6
    assert validate_shape_keys(key).ok
    _assert_managed_drivers(obj, key, "Thickness", {"Thickness@0", "Thickness@1"})
    zero_driver = next(
        fcurve
        for fcurve in key.animation_data.drivers
        if fcurve.data_path == zero.path_from_id("value")
    )
    assert zero_driver.driver.expression == "1.0"

    # Act/Assert: @0 is fully applied at Value 0; later targets interpolate
    # relative to it while it remains enabled.
    for controller_value, endpoint_value, evaluated_y in (
        (0.0, 0.0, -1.0),
        (0.5, 0.5, 0.0),
        (1.0, 1.0, 1.0),
    ):
        _set_controller_value(obj, controller, controller_value)
        sync_key(key, obj)
        bpy.context.view_layer.update()
        assert abs(zero.value - 1.0) < 1e-6
        assert abs(endpoint.value - endpoint_value) < 1e-6
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        evaluated_mesh = evaluated.to_mesh()
        try:
            assert abs(evaluated_mesh.vertices[1].co.y - evaluated_y) < 1e-6
        finally:
            evaluated.to_mesh_clear()

    # Act/Assert: the slider can move away from zero and return to exactly zero.
    entry.position = 0.1
    _flush_position_updates()
    assert key.key_blocks.get("Thickness@0.1") is not None
    entry.position = 0.0
    _flush_position_updates()
    assert key.key_blocks.get("Thickness@0.1") is None
    assert key.key_blocks.get("Thickness@0") is not None
    assert abs(key.key_blocks["Thickness@0"].value - 1.0) < 1e-6

    bpy.data.objects.remove(obj, do_unlink=True)
    print("Zero-position target interpolation and slider regression test passed")


def _assert_manual_group_rename_keeps_slider():
    from in_between_shape_key.ui import draw_shape_key_inbetween
    from in_between_shape_key.ui_state import find_entry

    # Background: names are the only persisted group contract. After both sides
    # are renamed, synchronization must rebuild the UI without identity caches.
    # Arrange: convert Bold and confirm its initial slider adapter exists.
    mesh = bpy.data.meshes.new("FBXI Manual Rename Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new("FBXI Manual Rename Object", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.shape_key_add(name="Basis")
    controller = obj.shape_key_add(name="Bold")
    controller.data[1].co.y = 1.0
    obj.active_shape_key_index = mesh.shape_keys.key_blocks.find(controller.name)
    assert bpy.ops.fbx_shape_inbetween.convert_to_inbetween() == {"FINISHED"}
    key = mesh.shape_keys
    assert find_entry(bpy.context.window_manager, obj, "Bold@1") is not None

    # Act: rename the controller and endpoint manually, then synchronize names.
    controller.name = "Thickness"
    endpoint = key.key_blocks["Bold@1"]
    endpoint.name = "Thickness@1"
    import in_between_shape_key

    in_between_shape_key._sync_ui_timer()
    obj.active_shape_key_index = key.key_blocks.find(endpoint.name)
    for block in key.key_blocks:
        block.select = block == endpoint
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)

    # Assert: the standard slider is rebuilt from the current canonical names.
    labels = [event[1] for event in panel.layout.events if event[0] == "label"]
    assert "Position unavailable" not in labels, panel.layout.events
    assert any(event[0] == "prop" and event[2] == "position" for event in panel.layout.events), panel.layout.events
    renamed_entry = find_entry(bpy.context.window_manager, obj, "Thickness@1")
    assert renamed_entry is not None
    renamed_entry.position = 0.8
    _flush_position_updates()
    assert key.key_blocks.get("Thickness@1") is None
    assert key.key_blocks.get("Thickness@0.8") is not None

    bpy.data.objects.remove(obj, do_unlink=True)
    print("Manual Bold/Thickness group rename slider regression test passed")


def _assert_canonical_position_validation():
    from in_between_shape_key.metadata import (
        format_position,
        format_target_name,
        normalize_position,
        parse_target_name,
    )
    from in_between_shape_key.sync import sync_key
    from in_between_shape_key.validation import validate_shape_keys

    # Background: target names use the same 0..1 factor shown in the UI.
    # Non-canonical spellings must never enter
    # driver synchronization and create a zero-width interpolation span.
    # Arrange: create a valid @0.5 target and forbidden equivalent spellings.
    mesh = bpy.data.meshes.new("FBXI Duplicate Numeric Weight Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new("FBXI Duplicate Numeric Weight Object", mesh)
    bpy.context.collection.objects.link(obj)
    try:
        assert normalize_position(0.1234) == 0.123
        assert format_position(0.1234) == "0.123"
        assert format_target_name("Precise", 0.1234) == "Precise@0.123"
        assert parse_target_name("Precise@.123") is None
        assert parse_target_name("Precise@0.1230") is None
        obj.shape_key_add(name="Basis")
        obj.shape_key_add(name="Duplicate")
        obj.shape_key_add(name="Duplicate@0.5")
        obj.shape_key_add(name="Duplicate@0.500")

        # Act: validate and run the same synchronization used by the timer.
        result = validate_shape_keys(mesh.shape_keys)
        sync_key(mesh.shape_keys, obj)

        # Assert: the non-canonical name is rejected and receives no driver.
        assert result.errors == ("Invalid shape key name at index 3: Duplicate@0.500",), result.errors
        invalid_path = mesh.shape_keys.key_blocks["Duplicate@0.500"].path_from_id("value")
        assert all(
            fcurve.data_path != invalid_path
            for fcurve in mesh.shape_keys.animation_data.drivers
        )
        assert all(
            "/ 0," not in fcurve.driver.expression
            for fcurve in mesh.shape_keys.animation_data.drivers
        )
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
    print("Canonical position validation regression test passed")


def _assert_managed_animation_rebuild():
    from in_between_shape_key.sync import controller_value_path, set_controller_value, sync_key

    # Background: managed Shape Key values are driven exclusively by the
    # controller property. Pre-existing keyframes and malformed drivers must not
    # remain on the same value path after conversion or a naming-rule change.
    # Arrange: keyframe an ordinary Shape Key before converting it.
    mesh = bpy.data.meshes.new("FBXI Animation Rebuild Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new("FBXI Animation Rebuild Object", mesh)
    bpy.context.collection.objects.link(obj)
    try:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        obj.shape_key_add(name="Basis")
        controller = obj.shape_key_add(name="Animated")
        key = mesh.shape_keys
        obj.active_shape_key_index = key.key_blocks.find(controller.name)
        controller.value = 0.25
        controller.keyframe_insert("value", frame=1)
        controller.value = 0.75
        controller.keyframe_insert("value", frame=10)
        controller_path = controller.path_from_id("value")

        # Act: conversion installs the managed driver.
        assert bpy.ops.fbx_shape_inbetween.convert_to_inbetween() == {"FINISHED"}

        # Assert: no action F-Curve remains on the now-driven property.
        action = key.animation_data.action
        action_paths = {
            fcurve.data_path
            for layer in action.layers
            for strip in layer.strips
            for channelbag in strip.channelbags
            for fcurve in channelbag.fcurves
        }
        assert controller_path not in action_paths
        old_controller_path = controller_value_path("Animated")
        set_controller_value(obj, "Animated", 0.25)
        obj.keyframe_insert(data_path=old_controller_path, frame=1)
        set_controller_value(obj, "Animated", 0.75)
        obj.keyframe_insert(data_path=old_controller_path, frame=10)

        # Act: rename only the controller and synchronize.
        controller.name = "Rebuilt"
        sync_key(key, obj)

        # Assert: the renamed group has one driver and its Value animation moved
        # from the old name-derived property path.
        assert key.key_blocks.get("Rebuilt@1") is not None
        rebuilt_path = controller.path_from_id("value")
        drivers = [
            fcurve for fcurve in key.animation_data.drivers
            if fcurve.data_path == rebuilt_path
        ]
        assert len(drivers) == 1
        assert drivers[0].driver.expression == "fbxi_controller"
        assert [variable.name for variable in drivers[0].driver.variables] == ["fbxi_controller"]
        new_controller_path = controller_value_path("Rebuilt")
        object_action_paths = {
            fcurve.data_path
            for layer in obj.animation_data.action.layers
            for strip in layer.strips
            for channelbag in strip.channelbags
            for fcurve in channelbag.fcurves
        }
        assert old_controller_path not in object_action_paths
        assert new_controller_path in object_action_paths

        # Act: corrupt the managed driver without changing the naming contract.
        driver = drivers[0]
        driver.driver.expression = "0.25"
        while driver.driver.variables:
            driver.driver.variables.remove(driver.driver.variables[0])
        sync_key(key, obj)

        # Assert: synchronization rebuilds the malformed driver from names.
        drivers = [
            fcurve for fcurve in key.animation_data.drivers
            if fcurve.data_path == rebuilt_path
        ]
        assert len(drivers) == 1
        assert drivers[0].driver.expression == "fbxi_controller"
        assert [variable.name for variable in drivers[0].driver.variables] == ["fbxi_controller"]
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
    print("Managed animation rebuild regression test passed")


def _assert_flat_tail_export():
    from in_between_shape_key.fbx_binary import FBXBinary
    from in_between_shape_key.ui_state import find_entry

    # Background: FBX FullWeights must contain one weight per target shape. When
    # the user's highest target is below 100%, export must synthesize an identical
    # 100% target so the last shape remains flat instead of making @1 special in Blender.
    # Arrange: convert one Shape Key and move its endpoint to 90%.
    mesh = bpy.data.meshes.new("FBXI Flat Tail Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new("FBXI Flat Tail Object", mesh)
    bpy.context.collection.objects.link(obj)
    try:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        obj.shape_key_add(name="Basis")
        controller = obj.shape_key_add(name="FlatTail")
        controller.data[1].co.y = 1.0
        obj.active_shape_key_index = mesh.shape_keys.key_blocks.find(controller.name)
        assert bpy.ops.fbx_shape_inbetween.convert_to_inbetween() == {"FINISHED"}
        entry = find_entry(bpy.context.window_manager, obj, "FlatTail@1")
        assert entry is not None
        entry.position = 0.9
        _flush_position_updates()
        assert mesh.shape_keys.key_blocks.get("FlatTail@0.9") is not None

        # Act: export through the production post-processor.
        output = Path(tempfile.mkdtemp(prefix="blender-fbxi-flat-tail-")) / "flat-tail.fbx"
        result = bpy.ops.export_scene.fbx_shape_inbetween(
            filepath=str(output),
            use_selection=True,
            object_types={"MESH"},
            bake_anim=False,
        )
        assert result == {"FINISHED"}, result
        scene = FBXBinary.read(str(output))

        # Assert: one progressive channel has real @0.9 plus an identical virtual
        # @1 geometry, and FullWeights converts those positions to FBX percentages.
        objects = next(node for node in scene.roots if node.name == b"Objects")
        channel = next(
            node
            for node in objects.children_named(b"Deformer")
            if node.prop(2) == "BlendShapeChannel"
            and str(node.prop(1)).startswith("FlatTail\x00\x01")
        )
        weights = channel.child(b"FullWeights")
        assert weights is not None and weights.prop(0) == [90.0, 100.0]
        shapes = {
            str(node.prop(1)).split("\x00\x01", 1)[0]: node
            for node in objects.children_named(b"Geometry")
            if node.prop(2) == "Shape"
            and str(node.prop(1)).startswith("FlatTail@")
        }
        assert set(shapes) == {"FlatTail@0.9", "FlatTail@1"}, set(shapes)
        assert shapes["FlatTail@0.9"].children == shapes["FlatTail@1"].children
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
    print("Optional @1 flat-tail FBX export regression test passed")


def _assert_japanese_translation():
    from bpy.app.translations import pgettext_iface

    # Background: project policy requires Japanese UI for every updated add-on.
    # Arrange/Act: switch Blender's interface lookup to Japanese.
    view = bpy.context.preferences.view
    original_language = view.language
    original_translate = view.use_translate_interface
    try:
        view.language = "ja_JP"
        view.use_translate_interface = True

        # Assert: the add-on translation domain is active.
        assert pgettext_iface("In-Between Shape Key") == "インビトウィーン・シェイプキー"
        assert pgettext_iface("Position") == "位置"
    finally:
        view.language = original_language
        view.use_translate_interface = original_translate
    print("Japanese translation registration test passed")


def _assert_undo_redo_tracking():
    from in_between_shape_key.sync import sync_key
    from in_between_shape_key.ui_state import find_entry

    # Background: the UI cache uses Blender session UIDs and canonical names.
    # Undo may restore datablocks from another snapshot, so current names must
    # rebuild drivers and rows without any stale pointer mapping.
    # Arrange: create a managed group and push the pre-rename snapshot.
    mesh = bpy.data.meshes.new("FBXI Undo Tracking Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new("FBXI Undo Tracking Object", mesh)
    bpy.context.collection.objects.link(obj)
    try:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        obj.shape_key_add(name="Basis")
        controller = obj.shape_key_add(name="UndoTrack")
        obj.active_shape_key_index = mesh.shape_keys.key_blocks.find(controller.name)
        assert bpy.ops.fbx_shape_inbetween.convert_to_inbetween() == {"FINISHED"}
        assert bpy.ops.ed.undo_push(message="FBXI before tracked rename") == {"FINISHED"}

        # Act: rename through synchronization, then push the renamed snapshot.
        key = obj.data.shape_keys
        controller.name = "RedoTrack"
        key.key_blocks["UndoTrack@1"].name = "RedoTrack@1"
        sync_key(key, obj)
        assert key.key_blocks.get("RedoTrack@1") is not None
        assert bpy.ops.ed.undo_push(message="FBXI after tracked rename") == {"FINISHED"}

        # Assert: undo restores the original group and a matching transient UI row.
        assert bpy.ops.ed.undo() == {"FINISHED"}
        obj = bpy.data.objects["FBXI Undo Tracking Object"]
        key = obj.data.shape_keys
        sync_key(key, obj)
        assert key.key_blocks.get("UndoTrack") is not None
        assert key.key_blocks.get("UndoTrack@1") is not None
        assert key.key_blocks.get("RedoTrack") is None
        assert find_entry(bpy.context.window_manager, obj, "UndoTrack@1") is not None

        # Act/Assert: redo restores the renamed group and its matching UI row.
        assert bpy.ops.ed.redo() == {"FINISHED"}
        obj = bpy.data.objects["FBXI Undo Tracking Object"]
        key = obj.data.shape_keys
        sync_key(key, obj)
        assert key.key_blocks.get("RedoTrack") is not None
        assert key.key_blocks.get("RedoTrack@1") is not None
        assert key.key_blocks.get("UndoTrack") is None
        assert find_entry(bpy.context.window_manager, obj, "RedoTrack@1") is not None
    finally:
        obj = bpy.data.objects.get("FBXI Undo Tracking Object")
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
    print("Undo/redo name reconstruction regression test passed")


def _move_shape_key(obj, key, name: str, direction: str, steps: int) -> None:
    for block in key.key_blocks:
        block.select = block.name == name
    for _step in range(steps):
        obj.active_shape_key_index = key.key_blocks.find(name)
        with bpy.context.temp_override(object=obj, active_object=obj):
            assert bpy.ops.object.shape_key_move(type=direction) == {"FINISHED"}


def _assert_add_reorder_and_rename_order_independence():
    from in_between_shape_key.metadata import parse_target_name
    from in_between_shape_key.sync import controller_value_path, read_groups, sync_key
    from in_between_shape_key.ui import draw_shape_key_inbetween
    from in_between_shape_key.ui_state import find_entry

    # Background: target membership used to be inferred from adjacency. Adding
    # an existing key or moving keys around could therefore bind the wrong row
    # and leave all transient sliders unavailable. Membership must instead
    # survive order changes by following the same Shape Key elements.
    # Arrange: convert Bold, add two existing keys, and scatter every member.
    mesh = bpy.data.meshes.new("FBXI Reorder Rename Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new("FBXI Reorder Rename Object", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.shape_key_add(name="Basis")
    controller = obj.shape_key_add(name="Bold")
    controller.data[1].co.y = 1.0
    obj.active_shape_key_index = mesh.shape_keys.key_blocks.find(controller.name)
    assert bpy.ops.fbx_shape_inbetween.convert_to_inbetween() == {"FINISHED"}
    key = mesh.shape_keys
    for source_name, weight in (("Bold Low Source", 0.25), ("Bold Mid Source", 0.5)):
        source = obj.shape_key_add(name=source_name)
        source.data[1].co.y = weight
        _set_controller_value(obj, controller, weight)
        assert bpy.ops.fbx_shape_inbetween.add_existing_key(
            controller_name=controller.name,
            source_name=source.name,
        ) == {"FINISHED"}
    obj.shape_key_add(name="Unrelated")
    _move_shape_key(obj, key, "Bold@1", "DOWN", 3)
    _move_shape_key(obj, key, "Unrelated", "UP", 2)
    scattered_order = [block.name for block in key.key_blocks]

    # Act/Assert: synchronization must neither depend on nor overwrite the
    # user's physical ordering.
    sync_key(key, obj)
    assert [block.name for block in key.key_blocks] == scattered_order
    assert {member["name"] for member in read_groups(key)[0]["members"]} == {
        "Bold@0.25", "Bold@0.5", "Bold@1",
    }

    # Act: rename the complete Name@Position contract explicitly. There is no
    # pointer-backed membership cache that can guess an incomplete rename.
    controller.name = "Thickness"
    for position in ("0.25", "0.5", "1"):
        key.key_blocks[f"Bold@{position}"].name = f"Thickness@{position}"
    sync_key(key, obj)
    assert key.key_blocks.get("Thickness") == controller
    assert all(
        key.key_blocks.get(f"Thickness@{position}") is not None
        for position in ("0.25", "0.5", "1")
    )

    # Act: add another existing Shape Key after conversion and reorder it. A
    # newly named member joins by the current naming convention, not adjacency.
    source = obj.shape_key_add(name="Late Existing")
    source.data[1].co.y = 0.75
    _set_controller_value(obj, controller, 0.75)
    assert bpy.ops.fbx_shape_inbetween.add_existing_key(
        controller_name="Thickness",
        source_name=source.name,
    ) == {"FINISHED"}
    _move_shape_key(obj, key, "Thickness@0.75", "UP", 3)
    reordered_again = [block.name for block in key.key_blocks]
    sync_key(key, obj)
    assert [block.name for block in key.key_blocks] == reordered_again

    # Act: delete an arbitrary middle target, then rename only the controller.
    obj.shape_key_remove(key.key_blocks["Thickness@0.5"])
    sync_key(key, obj)
    controller.name = "Height"
    sync_key(key, obj)

    # Assert: current names form one valid group and deleted members leave no
    # stale driver or slider state behind.
    group = next(group for group in read_groups(key) if group["controller"] == "Height")
    assert {member["position"] for member in group["members"]} == {0.25, 0.75, 1.0}
    _assert_managed_drivers(
        obj,
        key,
        "Height",
        {"Height@0.25", "Height@0.75", "Height@1"},
    )
    for member in group["members"]:
        name = member["name"]
        spec = parse_target_name(name)
        assert spec is not None and 0.0 <= spec.position <= 1.0
        assert "@@" not in name
        assert find_entry(bpy.context.window_manager, obj, name) is not None
    obj.active_shape_key_index = key.key_blocks.find("Height@0.75")
    for block in key.key_blocks:
        block.select = block.name == "Height@0.75"
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)
    labels = [event[1] for event in panel.layout.events if event[0] == "label"]
    assert "Position unavailable" not in labels, panel.layout.events
    assert sum(event[0] == "prop" and event[2] == "position" for event in panel.layout.events) == 3

    # Act/Assert: deleting the controller removes all managed drivers instead of
    # leaving stale references or Value animation for a deleted naming group.
    controller_path = controller_value_path("Height")
    obj.keyframe_insert(data_path=controller_path, frame=1)
    obj.shape_key_remove(controller)
    sync_key(key, obj)
    animation_data = key.animation_data
    assert animation_data is not None
    assert not any(
        any(variable.name == "fbxi_controller" for variable in fcurve.driver.variables)
        for fcurve in animation_data.drivers
    )
    assert controller_path not in {
        fcurve.data_path
        for layer in obj.animation_data.action.layers
        for strip in layer.strips
        for channelbag in strip.channelbags
        for fcurve in channelbag.fcurves
    }

    bpy.data.objects.remove(obj, do_unlink=True)
    print("Existing-key addition, arbitrary reorder, and rename-order regression tests passed")


def main():
    options = parse_args()
    if bool(options.addon_root) == bool(options.zip):
        raise ValueError("Pass exactly one of --addon-root or --zip")
    if options.zip:
        package_root = Path(tempfile.mkdtemp(prefix="blender-fbxi-addon-"))
        extract_zip(Path(options.zip).resolve(), package_root)
        sys.path.insert(0, str(package_root))
    else:
        sys.path.insert(0, str(Path(options.addon_root).resolve()))
    importlib.import_module("in_between_shape_key")

    result = bpy.ops.preferences.addon_enable(module="in_between_shape_key")
    if result != {"FINISHED"}:
        raise AssertionError(f"in_between_shape_key did not enable: {result}")
    from in_between_shape_key.ui import FBXI_PT_shape_key_inbetween

    if FBXI_PT_shape_key_inbetween.bl_idname != "FBXI_PT_shape_key_inbetween":
        raise AssertionError("In Between Shape Key panel was not registered")
    if getattr(bpy.types, FBXI_PT_shape_key_inbetween.__name__, None) is None:
        raise AssertionError("In Between Shape Key panel class is not registered")
    if not bpy.types.MESH_MT_shape_key_context_menu.is_extended():
        raise AssertionError("In Between Shape Key was not added to the Shape Key context menu")
    _assert_japanese_translation()
    from in_between_shape_key.fbx_binary import FBXBinary
    from in_between_shape_key.sync import read_groups, sync_key

    mesh = bpy.data.meshes.new("FBX In-Between Smoke Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new("FBX In-Between Smoke Object", mesh)
    bpy.context.collection.objects.link(obj)
    obj.shape_key_add(name="Basis")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    smile = obj.shape_key_add(name="Smile")
    smile.data[1].co.y = 1.0
    smile.value = 0.5
    key = mesh.shape_keys
    obj.active_shape_key_index = key.key_blocks.find("Smile")
    assert bpy.ops.fbx_shape_inbetween.convert_to_inbetween() == {"FINISHED"}
    controller = key.key_blocks["Smile"]
    source = obj.shape_key_add(name="Smile Mid")
    source.data[1].co.y = 0.5
    _set_controller_value(obj, controller, 0.5)
    result = bpy.ops.fbx_shape_inbetween.add_existing_key(
        controller_name="Smile",
        source_name="Smile Mid",
    )
    assert result == {"FINISHED"}, result

    custom_props_before_draw = set(key.keys())
    node_groups_before_draw = {node_group.name for node_group in bpy.data.node_groups}
    _assert_inbetween_panel_draws(obj)
    assert set(key.keys()) == custom_props_before_draw, "UI draw mutated Shape Key custom properties"
    assert {node_group.name for node_group in bpy.data.node_groups} == node_groups_before_draw, (
        "UI draw created or removed a node group"
    )

    assert key.key_blocks.get("Smile@0.5") is not None
    assert key.key_blocks.get("Smile@1") is not None
    controller = key.key_blocks["Smile"]
    first = key.key_blocks["Smile@0.5"]
    second = key.key_blocks["Smile@1"]
    assert abs(controller.data[1].co.y) < 1e-6
    assert abs(first.data[1].co.y - 0.5) < 1e-6, first.data[1].co.y
    assert abs(second.data[1].co.y - 1.0) < 1e-6
    _assert_managed_drivers(obj, key, "Smile", {"Smile@0.5", "Smile@1"})

    _set_controller_value(obj, controller, 0.25)
    bpy.context.view_layer.update()
    assert abs(first.value - 0.5) < 1e-6
    assert abs(second.value) < 1e-6
    source = obj.shape_key_add(name="Smile High")
    source.data[1].co.y = 0.75
    _set_controller_value(obj, controller, 0.75)
    bpy.context.view_layer.update()
    assert abs(first.value - 1.0) < 1e-6
    assert abs(second.value - 0.5) < 1e-6

    source_index_before_add = key.key_blocks.find("Smile High")
    result = bpy.ops.fbx_shape_inbetween.add_existing_key(
        controller_name="Smile",
        source_name="Smile High",
    )
    assert result == {"FINISHED"}, result
    assert key.key_blocks.get("Smile@0.75") is not None
    assert abs(key.key_blocks["Smile@0.75"].data[1].co.y - 0.75) < 1e-6
    assert key.key_blocks.find("Smile@0.75") == source_index_before_add

    normal = obj.shape_key_add(name="Blink")
    normal.data[2].co.x = 0.25
    obj.active_shape_key_index = key.key_blocks.find("Blink")
    convert_result = bpy.ops.fbx_shape_inbetween.convert_to_inbetween()
    assert convert_result == {"FINISHED"}, convert_result
    assert key.key_blocks.get("Blink@1") is not None
    assert abs(key.key_blocks["Blink@1"].data[2].co.x - 0.25) < 1e-6
    assert abs(key.key_blocks["Blink"].data[2].co.x) < 1e-6

    zero_source = obj.shape_key_add(name="Smile Zero")
    _set_controller_value(obj, controller, 0.0)
    assert bpy.ops.fbx_shape_inbetween.add_existing_key(
        controller_name="Smile",
        source_name=zero_source.name,
    ) == {"FINISHED"}
    assert key.key_blocks.get("Smile@0") is not None

    _set_controller_value(obj, controller, 0.75)
    obj.active_shape_key_index = key.key_blocks.find("Smile")
    bpy.context.view_layer.update()
    assert abs(key.key_blocks["Smile@0.5"].value - 1.0) < 1e-6
    assert abs(key.key_blocks["Smile@0.75"].value - 1.0) < 1e-6
    assert abs(key.key_blocks["Smile@1"].value) < 1e-6

    scene = bpy.context.scene
    scene.frame_set(1)
    _set_controller_value(obj, controller, 0.25)
    from in_between_shape_key.sync import controller_value_path

    value_path = controller_value_path("Smile")
    obj.keyframe_insert(data_path=value_path)
    scene.frame_set(10)
    _set_controller_value(obj, controller, 0.75)
    obj.keyframe_insert(data_path=value_path)
    scene.frame_set(1)
    bpy.context.view_layer.update()
    assert abs(controller.value - 0.25) < 1e-6
    assert abs(key.key_blocks["Smile@0.5"].value - 0.5) < 1e-6, key.key_blocks["Smile@0.5"].value
    scene.frame_set(10)
    bpy.context.view_layer.update()
    assert abs(controller.value - 0.75) < 1e-6
    assert abs(key.key_blocks["Smile@1"].value) < 1e-6

    controller.data[1].co.y = 0.9
    bpy.context.view_layer.update()
    import in_between_shape_key

    in_between_shape_key._sync_ui_timer()
    assert abs(controller.data[1].co.y) < 1e-6

    obj.active_shape_key_index = key.key_blocks.find("Smile")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.view_layer.update()
    in_between_shape_key._sync_ui_timer()
    assert obj.active_shape_key.name != "Smile"
    bpy.ops.object.mode_set(mode="OBJECT")

    controller = key.key_blocks["Smile"]
    _set_controller_value(obj, controller, 0.75)
    bpy.context.view_layer.update()

    sync_key(key, obj)

    output = Path(tempfile.mkdtemp(prefix="blender-fbxi-smoke-")) / "smoke.fbx"
    result = bpy.ops.export_scene.fbx_shape_inbetween(
        filepath=str(output),
        use_selection=True,
        object_types={"MESH"},
        bake_anim=False,
    )
    assert result == {"FINISHED"}, result
    in_between_shape_key._sync_ui_timer()
    _assert_managed_drivers(
        obj,
        key,
        "Smile",
        {"Smile@0", "Smile@0.5", "Smile@0.75", "Smile@1"},
    )
    _assert_managed_drivers(obj, key, "Blink", {"Blink@1"})
    scene = FBXBinary.read(str(output))
    objects = next(node for node in scene.roots if node.name == b"Objects")
    channels = [node for node in objects.children_named(b"Deformer") if node.prop(2) == "BlendShapeChannel"]
    names = [node.prop(1) for node in channels]
    assert sum(str(name).startswith("Smile\x00\x01") for name in names) == 1, names
    assert not any(str(name).startswith("Smile@") for name in names), names
    assert not any(str(name) == "Smile" for name in names), names
    happy = next(node for node in channels if str(node.prop(1)).startswith("Smile\x00\x01"))
    weights = happy.child(b"FullWeights")
    assert weights is not None
    assert weights.prop(0) == [0.0, 50.0, 75.0, 100.0], weights.prop(0)
    assert any(str(node.prop(1)).startswith("Blink\x00\x01") for node in channels)

    assert any(group.get("controller") == "Smile" for group in read_groups(key))
    assert not list(key.keys()), "Shape Key metadata was persisted by the add-on"
    assert not any(name.startswith("FBXI_") for name in bpy.data.node_groups), (
        "UI storage node group was created"
    )
    obj.shape_key_add(name="Smile@0.25", from_mix=False)
    sync_key(key, obj)
    assert key.key_blocks.get("Smile@0.25") is not None

    key.key_blocks["Smile@0.5"].name = "Smile@0.6"
    sync_key(key, obj)
    assert key.key_blocks.get("Smile@0.6") is not None, [block.name for block in key.key_blocks]
    assert key.key_blocks.get("Smile@0.5") is None

    obj.shape_key_remove(key.key_blocks["Smile@0.25"])
    sync_key(key, obj)
    assert key.key_blocks.get("Smile@0.25") is None

    key.key_blocks["Smile"].name = "Happy"
    key.key_blocks["Smile@0.6"].name = "Happy@0.6"
    key.key_blocks["Smile@0.75"].name = "Happy@0.75"
    key.key_blocks["Smile@1"].name = "Happy@1"
    bpy.context.view_layer.update()
    sync_key(key, obj)
    assert key.key_blocks.get("Happy") is not None
    assert key.key_blocks.get("Happy@0.6") is not None
    assert key.key_blocks.get("Smile") is None
    assert not list(key.keys()), "Shape Key metadata was persisted by the add-on"

    _assert_position_slider_operations()
    _assert_zero_position_target()
    _assert_manual_group_rename_keeps_slider()
    _assert_canonical_position_validation()
    _assert_add_reorder_and_rename_order_independence()
    bpy.data.objects.remove(obj, do_unlink=True)
    _assert_managed_animation_rebuild()
    _assert_flat_tail_export()
    # Undo replaces Blender datablocks and invalidates Python references, so run
    # this isolated scenario only after every earlier fixture has been cleaned up.
    _assert_undo_redo_tracking()
    result = bpy.ops.preferences.addon_disable(module="in_between_shape_key")
    if result != {"FINISHED"}:
        raise AssertionError(f"in_between_shape_key did not disable: {result}")

    # Reload-while-enabled must not leak Python/RNA registrations.
    baseline_depsgraph = len(bpy.app.handlers.depsgraph_update_pre)
    baseline_frame = len(bpy.app.handlers.frame_change_post)
    result = bpy.ops.preferences.addon_enable(module="in_between_shape_key")
    if result != {"FINISHED"}:
        raise AssertionError(f"in_between_shape_key did not enable for reload probe: {result}")
    module = importlib.reload(importlib.import_module("in_between_shape_key"))
    module.register()
    result = bpy.ops.preferences.addon_disable(module="in_between_shape_key")
    if result != {"FINISHED"}:
        raise AssertionError(f"in_between_shape_key did not disable after reload probe: {result}")
    if "in_between_shape_key.runtime.v1" in getattr(bpy.app, "driver_namespace", {}):
        raise AssertionError("in_between_shape_key runtime key leaked")
    if len(bpy.app.handlers.depsgraph_update_pre) != baseline_depsgraph:
        raise AssertionError("depsgraph handlers leaked after reload-while-enabled")
    if len(bpy.app.handlers.frame_change_post) != baseline_frame:
        raise AssertionError("frame handlers leaked after reload-while-enabled")
    if hasattr(bpy.types, "FBXI_PT_shape_key_inbetween"):
        raise AssertionError("panel still registered after reload-while-enabled cleanup")
    if hasattr(bpy.types.WindowManager, "fbxi_target_positions"):
        raise AssertionError("target position RNA property leaked after reload-while-enabled")

    print("FBX Shape Key In-Between functional smoke test passed")


if __name__ == "__main__":
    main()
