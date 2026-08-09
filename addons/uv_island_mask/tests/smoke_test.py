from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from zip_utils import extract_zip


def parse_args():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    return parser.parse_args(raw)


def test_empty_image_editor_display():
    from uv_island_mask.context import show_image_in_image_editor

    class FakeSpace:
        type = "IMAGE_EDITOR"
        mode = "UV"
        image = None

    class FakeArea:
        type = "IMAGE_EDITOR"

        def __init__(self) -> None:
            self.spaces = type("Spaces", (), {"active": FakeSpace()})()
            self.redraw_count = 0

        def tag_redraw(self):
            self.redraw_count += 1

    image_area = FakeArea()
    console_area = type("ConsoleArea", (), {"type": "CONSOLE"})()
    context = type(
        "ConsoleContext",
        (),
        {
            "area": console_area,
            "screen": type("Screen", (), {"areas": [console_area, image_area]})(),
            "window_manager": None,
        },
    )()
    image = object()

    assert show_image_in_image_editor(context, image)
    assert image_area.spaces.active.image is image
    assert image_area.redraw_count == 1

    second_area = FakeArea()
    context.screen.areas.append(second_area)
    assert show_image_in_image_editor(context, image)
    assert second_area.spaces.active.image is image
    assert second_area.redraw_count == 1


def main():
    options = parse_args()
    temp_dir = Path(tempfile.mkdtemp(prefix="blender-uv-mask-smoke-"))
    extract_zip(Path(options.zip).resolve(), temp_dir)
    sys.path.insert(0, str(temp_dir))

    addon = importlib.import_module("uv_island_mask")
    addon.register()
    test_empty_image_editor_display()

    settings = bpy.context.scene.uv_island_mask
    assert settings.mask_resolution == "1024"
    assert settings.mask_margin == 16
    settings.mask_resolution = "2048"
    assert settings.mask_margin == 32
    settings.mask_margin_locked = False
    settings.mask_resolution = "4096"
    assert settings.mask_margin == 32
    settings.mask_margin_locked = True
    settings.use_custom_resolution = True
    settings.custom_width = 2048
    settings.custom_height = 512
    assert settings.mask_margin == 32

    from uv_island_mask.embedded_host import ToolSpec, register_tool, unregister_tool
    from uv_island_mask.mask import bake_selected_uv_mask

    fake_tool = ToolSpec(
        tool_id="test_uv_tool",
        owner_id="smoke-test",
        display_name="Test UV Tool",
        group_id="uv_utility",
        group_label="UV Utility",
        sort_order=200,
        space_type="IMAGE_EDITOR",
        region_type="UI",
        category="Edit",
        poll=lambda context: True,
        draw=lambda context, layout: None,
    )
    register_tool(fake_tool)
    state = bpy.app.driver_namespace["blender_addon_tools.embedded_host.v1"]
    assert len(state["tools"]) == 2
    assert "uv_utility" in state["groups"]
    unregister_tool("test_uv_tool", "smoke-test")

    empty_image, empty_warning = bake_selected_uv_mask(bpy.context, [], "Unused", 16, 1)
    assert empty_image is None
    assert empty_warning == "Select at least one UV face"

    mesh = bpy.data.meshes.new("UV Mask Smoke Mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new("UV Mask Smoke Object", mesh)
    bpy.context.collection.objects.link(obj)

    second_mesh = bpy.data.meshes.new("UV Mask Smoke Second Mesh")
    second_mesh.from_pydata([(2, 0, 0), (3, 0, 0), (3, 1, 0), (2, 1, 0)], [], [(0, 1, 2, 3)])
    second_mesh.update()
    second_obj = bpy.data.objects.new("UV Mask Smoke Second Object", second_mesh)
    bpy.context.collection.objects.link(second_obj)

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    second_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bmesh = __import__("bmesh")
    for edit_mesh in (mesh, second_mesh):
        bm = bmesh.from_edit_mesh(edit_mesh)
        uv_layer = bm.loops.layers.uv.verify()
        for face in bm.faces:
            face.select = True
            for loop in face.loops:
                loop[uv_layer].uv = (0.1 + loop.vert.index * 0.2, 0.1)
                loop.uv_select_vert_set(True)
        bmesh.update_edit_mesh(edit_mesh)
    image, warning = bake_selected_uv_mask(bpy.context, [obj, second_obj], "UV Mask Smoke", (16, 32), 1)
    assert warning is None
    assert image is not None
    assert image.size[0] == 16 and image.size[1] == 32
    bpy.data.images.remove(image)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.objects.remove(second_obj, do_unlink=True)
    addon.unregister()
    print("UV Island Mask functional smoke test passed")


if __name__ == "__main__":
    main()
