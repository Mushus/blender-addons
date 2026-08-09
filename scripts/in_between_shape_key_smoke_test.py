from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    for block in key.key_blocks:
        block.select = block.name == "Smile@50"
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)
    labels = [event[1] for event in panel.layout.events if event[0] == "label"]
    assert "Shape Key Controllers" not in labels, panel.layout.events
    assert "@100  Locked" not in labels, panel.layout.events
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

    # @100 uses the same editable/removable detail row as every other target.
    for block in key.key_blocks:
        block.select = block.name == "Smile@100"
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
    entry = find_entry(bpy.context.window_manager, obj, "Position@100")
    assert entry is not None
    assert abs(entry.position - 1.0) < 1e-6

    # Act: edit the standard slider's RNA value, then evaluate beyond the new
    # highest target. This exercises the same update callback used by the GUI.
    obj.name = "FBXI Position Slider Renamed Object"
    entry.position = 0.9
    _set_controller_value(obj, controller, 0.95)
    bpy.context.view_layer.update()

    # Assert: the key was renamed, @100 is optional, and the final @90 target
    # remains fully applied through 100%.
    assert key.key_blocks.get("Position@100") is None
    assert key.key_blocks.get("Position@90") is not None
    assert entry.target_name == "Position@90"
    assert abs(key.key_blocks["Position@90"].value - 1.0) < 1e-6
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    evaluated_mesh = evaluated.to_mesh()
    try:
        assert abs(evaluated_mesh.vertices[1].co.y - 1.0) < 1e-6
    finally:
        evaluated.to_mesh_clear()
    assert validate_shape_keys(key).ok

    # Arrange/Act: create another target, then try to move it onto an occupied
    # position. The adapter must reject the duplicate and restore its slider.
    obj.shape_key_add(name="Position@50", from_mix=False)
    sync_key(key, obj)
    duplicate_entry = find_entry(bpy.context.window_manager, obj, "Position@50")
    assert duplicate_entry is not None
    duplicate_entry.position = 0.9

    # Assert: duplicate positions never rename or overwrite a Shape Key.
    assert key.key_blocks.get("Position@50") is not None
    assert key.key_blocks.get("Position@90") is not None
    assert abs(duplicate_entry.position - 0.5) < 1e-6
    assert bpy.ops.fbx_shape_inbetween.remove_target(target_name="Position@90") == {"FINISHED"}
    assert key.key_blocks.get("Position@90") is None
    assert validate_shape_keys(key).ok

    # Arrange/Act: rename the controller. Its contiguous target run must follow
    # the new parent name, and the transient slider entry must remain available.
    controller.name = "Position Renamed"
    import in_between_shape_key

    in_between_shape_key._sync_ui_timer()

    # Assert: group ownership and slider lookup use live Shape Key identity,
    # not stale controller or Key datablock names.
    assert key.key_blocks.get("Position@50") is None
    assert key.key_blocks.get("Position Renamed@50") is not None
    renamed_entry = find_entry(bpy.context.window_manager, obj, "Position Renamed@50")
    assert renamed_entry is not None
    assert abs(renamed_entry.position - 0.5) < 1e-6

    bpy.data.objects.remove(obj, do_unlink=True)
    print("Position slider, parent rename, duplicate rejection, and flat-tail tests passed")


def _assert_zero_weight_target():
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
    endpoint = key.key_blocks["Thickness@100"]
    entry = find_entry(bpy.context.window_manager, obj, zero.name)
    assert entry is not None and abs(entry.position) < 1e-6
    assert validate_shape_keys(key).ok
    _assert_managed_drivers(obj, key, "Thickness", {"Thickness@0", "Thickness@100"})
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
    assert key.key_blocks.get("Thickness@10") is not None
    entry.position = 0.0
    assert key.key_blocks.get("Thickness@10") is None
    assert key.key_blocks.get("Thickness@0") is not None
    assert abs(key.key_blocks["Thickness@0"].value - 1.0) < 1e-6

    bpy.data.objects.remove(obj, do_unlink=True)
    print("Zero-weight target interpolation and slider regression test passed")


def _assert_manual_group_rename_keeps_slider():
    from in_between_shape_key.ui import draw_shape_key_inbetween
    from in_between_shape_key.ui_state import find_entry

    # Background: Blender can deliver panel redraw before the deferred cache
    # refresh after users rename both sides of the Name@Weight convention.
    # The row must follow the live Shape Key identity during that interval.
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
    stale_entry = find_entry(bpy.context.window_manager, obj, "Bold@100")
    assert stale_entry is not None

    # Act: rename the controller and endpoint manually, without running the
    # depsgraph handler or deferred UI-cache timer first.
    controller.name = "Thickness"
    endpoint = key.key_blocks["Bold@100"]
    endpoint.name = "Thickness@100"
    obj.active_shape_key_index = key.key_blocks.find(endpoint.name)
    for block in key.key_blocks:
        block.select = block == endpoint
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)

    # Assert: the standard slider binds through the stable Shape Key identity;
    # the transient old name must not produce the user-visible error state.
    labels = [event[1] for event in panel.layout.events if event[0] == "label"]
    assert "Position unavailable" not in labels, panel.layout.events
    assert any(event[0] == "prop" and event[2] == "position" for event in panel.layout.events), panel.layout.events
    assert find_entry(bpy.context.window_manager, obj, "Thickness@100") == stale_entry
    stale_entry.position = 0.8
    assert key.key_blocks.get("Thickness@100") is None
    assert key.key_blocks.get("Thickness@80") is not None

    bpy.data.objects.remove(obj, do_unlink=True)
    print("Manual Bold/Thickness group rename slider regression test passed")


def _move_shape_key(obj, key, name: str, direction: str, steps: int) -> None:
    for block in key.key_blocks:
        block.select = block.name == name
    for _step in range(steps):
        obj.active_shape_key_index = key.key_blocks.find(name)
        with bpy.context.temp_override(object=obj, active_object=obj):
            assert bpy.ops.object.shape_key_move(type=direction) == {"FINISHED"}


def _assert_add_reorder_and_rename_order_independence():
    from in_between_shape_key.metadata import parse_target_name
    from in_between_shape_key.sync import read_groups, sync_key
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
    _move_shape_key(obj, key, "Bold@100", "DOWN", 3)
    _move_shape_key(obj, key, "Unrelated", "UP", 2)
    scattered_order = [_block.as_pointer() for _block in key.key_blocks]

    # Act/Assert: synchronization must neither depend on nor overwrite the
    # user's physical ordering.
    sync_key(key, obj)
    assert [_block.as_pointer() for _block in key.key_blocks] == scattered_order
    assert {member["name"] for member in read_groups(key)[0]["members"]} == {
        "Bold@25", "Bold@50", "Bold@100",
    }

    # Act: child-first rename. One tracked child establishes the new channel;
    # the controller and siblings must follow regardless of their positions.
    key.key_blocks["Bold@50"].name = "Thickness@50"
    sync_key(key, obj)
    assert key.key_blocks.get("Thickness") == controller
    assert all(key.key_blocks.get(f"Thickness@{weight}") is not None for weight in (25, 50, 100))

    # Act: add another existing Shape Key after conversion and reorder it. A
    # newly named member joins by the current naming convention, not adjacency.
    source = obj.shape_key_add(name="Late Existing")
    source.data[1].co.y = 0.75
    _set_controller_value(obj, controller, 0.75)
    assert bpy.ops.fbx_shape_inbetween.add_existing_key(
        controller_name="Thickness",
        source_name=source.name,
    ) == {"FINISHED"}
    _move_shape_key(obj, key, "Thickness@75", "UP", 3)
    reordered_again = [_block.as_pointer() for _block in key.key_blocks]
    sync_key(key, obj)
    assert [_block.as_pointer() for _block in key.key_blocks] == reordered_again

    # Act: controller-first, then simultaneous controller/child rename. These
    # cover every ordering class without enumerating UI gesture sequences.
    controller.name = "Width"
    sync_key(key, obj)
    assert all(key.key_blocks.get(f"Width@{weight}") is not None for weight in (25, 50, 75, 100))
    controller.name = "Depth"
    key.key_blocks["Width@25"].name = "Depth@25"
    sync_key(key, obj)

    # Arrange/Act: discard all transient group tracking, as happens across an
    # add-on/file reload, then bootstrap from valid names in the scattered list.
    from in_between_shape_key.runtime import get_state

    state = get_state()
    assert state is not None
    state["group_tracks"].clear()
    sync_key(key, obj)
    controller.name = "Height"
    sync_key(key, obj)

    # Assert: all names form one valid group, all rows resolve their sliders,
    # and no invalid intermediate spelling such as the reported @@0 survives.
    group = next(group for group in read_groups(key) if group["controller"] == "Height")
    assert {member["weight"] for member in group["members"]} == {25.0, 50.0, 75.0, 100.0}
    _assert_managed_drivers(
        obj,
        key,
        "Height",
        {"Height@25", "Height@50", "Height@75", "Height@100"},
    )
    for member in group["members"]:
        name = member["name"]
        spec = parse_target_name(name)
        assert spec is not None and 1.0 <= spec.weight <= 100.0
        assert "@@" not in name
        assert find_entry(bpy.context.window_manager, obj, name) is not None
    obj.active_shape_key_index = key.key_blocks.find("Height@75")
    for block in key.key_blocks:
        block.select = block.name == "Height@75"
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)
    labels = [event[1] for event in panel.layout.events if event[0] == "label"]
    assert "Position unavailable" not in labels, panel.layout.events
    assert sum(event[0] == "prop" and event[2] == "position" for event in panel.layout.events) == 4

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

    assert key.key_blocks.get("Smile@50") is not None
    assert key.key_blocks.get("Smile@100") is not None
    controller = key.key_blocks["Smile"]
    first = key.key_blocks["Smile@50"]
    second = key.key_blocks["Smile@100"]
    assert abs(controller.data[1].co.y) < 1e-6
    assert abs(first.data[1].co.y - 0.5) < 1e-6, first.data[1].co.y
    assert abs(second.data[1].co.y - 1.0) < 1e-6
    _assert_managed_drivers(obj, key, "Smile", {"Smile@50", "Smile@100"})

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

    order_before_add = [block.as_pointer() for block in key.key_blocks]
    result = bpy.ops.fbx_shape_inbetween.add_existing_key(
        controller_name="Smile",
        source_name="Smile High",
    )
    assert result == {"FINISHED"}, result
    assert key.key_blocks.get("Smile@75") is not None
    assert abs(key.key_blocks["Smile@75"].data[1].co.y - 0.75) < 1e-6
    assert [block.as_pointer() for block in key.key_blocks] == order_before_add

    normal = obj.shape_key_add(name="Blink")
    normal.data[2].co.x = 0.25
    obj.active_shape_key_index = key.key_blocks.find("Blink")
    convert_result = bpy.ops.fbx_shape_inbetween.convert_to_inbetween()
    assert convert_result == {"FINISHED"}, convert_result
    assert key.key_blocks.get("Blink@100") is not None
    assert abs(key.key_blocks["Blink@100"].data[2].co.x - 0.25) < 1e-6
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
    assert abs(key.key_blocks["Smile@50"].value - 1.0) < 1e-6
    assert abs(key.key_blocks["Smile@75"].value - 1.0) < 1e-6
    assert abs(key.key_blocks["Smile@100"].value) < 1e-6

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
    assert abs(key.key_blocks["Smile@50"].value - 0.5) < 1e-6, key.key_blocks["Smile@50"].value
    scene.frame_set(10)
    bpy.context.view_layer.update()
    assert abs(controller.value - 0.75) < 1e-6
    assert abs(key.key_blocks["Smile@100"].value) < 1e-6

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
        {"Smile@0", "Smile@50", "Smile@75", "Smile@100"},
    )
    _assert_managed_drivers(obj, key, "Blink", {"Blink@100"})
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
    obj.shape_key_add(name="Smile@25", from_mix=False)
    sync_key(key, obj)
    assert key.key_blocks.get("Smile@25") is not None

    key.key_blocks["Smile@50"].name = "Smile@60"
    sync_key(key, obj)
    assert key.key_blocks.get("Smile@60") is not None, [block.name for block in key.key_blocks]
    assert key.key_blocks.get("Smile@50") is None

    obj.shape_key_remove(key.key_blocks["Smile@25"])
    sync_key(key, obj)
    assert key.key_blocks.get("Smile@25") is None

    key.key_blocks["Smile"].name = "Happy"
    key.key_blocks["Smile@60"].name = "Happy@60"
    key.key_blocks["Smile@75"].name = "Happy@75"
    key.key_blocks["Smile@100"].name = "Happy@100"
    bpy.context.view_layer.update()
    sync_key(key, obj)
    assert key.key_blocks.get("Happy") is not None
    assert key.key_blocks.get("Happy@60") is not None
    assert key.key_blocks.get("Smile") is None
    assert not list(key.keys()), "Shape Key metadata was persisted by the add-on"

    _assert_position_slider_operations()
    _assert_zero_weight_target()
    _assert_manual_group_rename_keeps_slider()
    _assert_add_reorder_and_rename_order_independence()
    bpy.data.objects.remove(obj, do_unlink=True)
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
