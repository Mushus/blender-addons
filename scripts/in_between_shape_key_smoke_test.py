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

    def template_color_ramp(self, data, property_name, **_kwargs):
        self.events.append(("color_ramp", data.name, property_name))

    def operator(self, operator_id, **_kwargs):
        self.events.append(("operator", operator_id))
        return SimpleNamespace()


class _RecordingPanel:
    def __init__(self) -> None:
        self.layout = _RecordingLayout()


def _assert_inbetween_panel_draws(obj):
    from in_between_shape_key.operator import FBXI_OT_drag_target
    from in_between_shape_key.ui import draw_shape_key_inbetween

    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)
    labels = [event[1] for event in panel.layout.events if event[0] == "label"]
    assert "Shape Key Controllers" not in labels, panel.layout.events
    assert not any(event[0] == "color_ramp" for event in panel.layout.events), panel.layout.events
    assert ("label", "Timeline") in panel.layout.events, panel.layout.events
    assert sum(event[0] == "box" for event in panel.layout.events) >= 5, panel.layout.events
    assert any(event == ("operator", FBXI_OT_drag_target.bl_idname) for event in panel.layout.events), (
        panel.layout.events
    )
    assert any(event[0] == "operator" for event in panel.layout.events), panel.layout.events

    # The controller row is also a valid context for the panel.  This is the
    # case users need when they want to add the first new timeline key.
    obj.active_shape_key_index = obj.data.shape_keys.key_blocks.find("Smile")
    panel = _RecordingPanel()
    draw_shape_key_inbetween(panel, bpy.context)
    labels = [event[1] for event in panel.layout.events if event[0] == "label"]
    assert "Shape Key Controllers" not in labels, panel.layout.events
    print("Shape Key panel draw test passed (in-between and controller selection)")


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
    result = bpy.ops.fbx_shape_inbetween.add_at_current_value()
    assert result == {"FINISHED"}, result

    custom_props_before_draw = set(key.keys())
    node_groups_before_draw = {node_group.name for node_group in bpy.data.node_groups}
    _assert_inbetween_panel_draws(obj)
    assert set(key.keys()) == custom_props_before_draw, "UI draw mutated Shape Key custom properties"
    assert {node_group.name for node_group in bpy.data.node_groups} == node_groups_before_draw, (
        "UI draw created or removed a node group"
    )

    # Exercise the shared mutation path used by the modal drag operator. The
    # GUI smoke covers the rendered marker track; background Blender covers the
    # data update without relying on platform-specific mouse event delivery.
    from in_between_shape_key.operator import FBXI_OT_drag_target

    drag_probe = SimpleNamespace(
        target_name="Smile@50",
        weight=50.0,
        _target=lambda _context: (key, key.key_blocks.get(drag_probe.target_name)),
    )
    assert FBXI_OT_drag_target._apply_weight(drag_probe, bpy.context, 60.0)
    assert key.key_blocks.get("Smile@60") is not None
    assert drag_probe.target_name == "Smile@60"
    assert FBXI_OT_drag_target._apply_weight(drag_probe, bpy.context, 50.0)
    assert key.key_blocks.get("Smile@50") is not None

    # A click must not move a key. The modal drag path starts only after the
    # pointer crosses the small press threshold, then uses the continuous
    # mouse position for the new value.
    applied_weights = []
    modal_probe = SimpleNamespace(
        _press_x=50,
        _track_start_x=0,
        _track_end_x=100,
        _start_weight=50.0,
        _dragging=False,
        _moved=False,
        _button_down=True,
        _DRAG_THRESHOLD_PX=3,
        _apply_weight=lambda _context, weight: applied_weights.append(weight) or True,
    )
    assert FBXI_OT_drag_target.modal(
        modal_probe,
        bpy.context,
        SimpleNamespace(type="MOUSEMOVE", mouse_region_x=51),
    ) == {"RUNNING_MODAL"}
    assert not modal_probe._dragging and not applied_weights
    assert FBXI_OT_drag_target.modal(
        modal_probe,
        bpy.context,
        SimpleNamespace(type="MOUSEMOVE", mouse_region_x=60),
    ) == {"RUNNING_MODAL"}
    assert modal_probe._dragging and applied_weights == [60.0]

    assert key.key_blocks.get("Smile@50") is not None
    assert key.key_blocks.get("Smile@100") is not None
    controller = key.key_blocks["Smile"]
    first = key.key_blocks["Smile@50"]
    second = key.key_blocks["Smile@100"]
    assert abs(controller.data[1].co.y) < 1e-6
    assert abs(first.data[1].co.y - 0.5) < 1e-6, first.data[1].co.y
    assert abs(second.data[1].co.y - 1.0) < 1e-6
    assert key.animation_data is None or len(key.animation_data.drivers) == 0

    controller.value = 0.25
    bpy.context.view_layer.update()
    assert abs(first.value - 0.5) < 1e-6
    assert abs(second.value) < 1e-6
    controller.value = 0.75
    bpy.context.view_layer.update()
    assert abs(first.value - 1.0) < 1e-6
    assert abs(second.value - 0.5) < 1e-6

    result = bpy.ops.fbx_shape_inbetween.add_at_current_value()
    assert result == {"FINISHED"}, result
    assert key.key_blocks.get("Smile@75") is not None
    assert abs(key.key_blocks["Smile@75"].data[1].co.y - 0.75) < 1e-6
    assert [key.key_blocks[index].name for index in range(1, 5)] == [
        "Smile",
        "Smile@50",
        "Smile@75",
        "Smile@100",
    ]

    normal = obj.shape_key_add(name="Blink")
    normal.data[2].co.x = 0.25
    obj.active_shape_key_index = key.key_blocks.find("Smile")
    bpy.context.view_layer.update()
    assert abs(key.key_blocks["Smile@50"].value - 1.0) < 1e-6
    assert abs(key.key_blocks["Smile@75"].value - 1.0) < 1e-6
    assert abs(key.key_blocks["Smile@100"].value) < 1e-6

    scene = bpy.context.scene
    scene.frame_set(1)
    controller.value = 0.25
    key.keyframe_insert(data_path='key_blocks["Smile"].value')
    scene.frame_set(10)
    controller.value = 0.75
    key.keyframe_insert(data_path='key_blocks["Smile"].value')
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
    assert abs(controller.data[1].co.y) < 1e-6

    obj.active_shape_key_index = key.key_blocks.find("Smile")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.view_layer.update()
    assert obj.active_shape_key.name != "Smile"
    bpy.ops.object.mode_set(mode="OBJECT")

    controller = key.key_blocks["Smile"]
    controller.value = 0.75
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
    assert weights.prop(0) == [50.0, 75.0, 100.0], weights.prop(0)
    assert any(str(node.prop(1)).startswith("Blink\x00\x01") for node in channels)

    assert any(group.get("controller") == "Smile" for group in read_groups(key))
    assert not list(key.keys()), "Shape Key metadata was persisted by the add-on"
    assert not any(name.startswith("FBXI_") for name in bpy.data.node_groups), (
        "Timeline storage node group was created"
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

    print("FBX Shape Key In-Between functional smoke test passed")


if __name__ == "__main__":
    main()
