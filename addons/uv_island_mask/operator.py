import bpy

from .context import edit_mesh_objects, is_uv_editor, show_image_in_image_editor
from .mask import bake_selected_uv_mask
from .properties import get_resolution


def _schedule_image_display(image_name: str):
    def update_image_editors():
        image = bpy.data.images.get(image_name)
        if image is None:
            return
        show_image_in_image_editor(bpy.context, image)

    try:
        bpy.app.timers.register(update_image_editors, first_interval=0.1)
    except ValueError:
        pass


class UVIM_OT_bake_mask(bpy.types.Operator):
    bl_idname = "uv_island_mask.bake_mask"
    bl_label = "Bake UV Island Mask"
    bl_description = "Bake a mask image for selected UV faces with seam margin"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context) -> bool:
        obj = context.active_object
        return (
            is_uv_editor(context)
            and obj is not None
            and obj.type == "MESH"
            and obj.mode == "EDIT"
        )

    def execute(self, context):
        settings = context.scene.uv_island_mask
        try:
            image, warning = bake_selected_uv_mask(
                context,
                edit_mesh_objects(context),
                "UV Island Mask",
                get_resolution(settings),
                settings.mask_margin,
            )
        except Exception as exc:
            message = bpy.app.translations.pgettext_iface("Failed to bake UV island mask")
            self.report({"ERROR"}, f"{message}: {exc}")
            return {"CANCELLED"}

        if warning is not None:
            self.report({"WARNING"}, bpy.app.translations.pgettext_iface(warning))
            return {"CANCELLED"}

        if not show_image_in_image_editor(context, image):
            message = bpy.app.translations.pgettext_iface(
                "Mask image was created, but no Image Editor area is available"
            )
            self.report({"WARNING"}, message)
        _schedule_image_display(image.name)
        message = bpy.app.translations.pgettext_iface("Baked UV island mask")
        self.report({"INFO"}, f"{message}: {image.name}")
        return {"FINISHED"}
