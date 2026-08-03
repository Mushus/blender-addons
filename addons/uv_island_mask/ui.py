from .context import is_uv_editor
from .embedded_host.ui import draw_action_row, draw_settings_box
from .operator import UVIM_OT_bake_mask


def draw_tool(context, layout):
    settings = context.scene.uv_island_mask
    column = layout.column(align=True)
    draw_action_row(
        column,
        settings,
        "expanded",
        UVIM_OT_bake_mask.bl_idname,
        text="Bake UV Island Mask",
    )
    if settings.expanded:
        box = draw_settings_box(column)
        resolution_row = box.row(align=True)
        resolution_row.label(text="Resolution")
        if settings.use_custom_resolution:
            resolution_row.prop(settings, "custom_width", text="W")
            resolution_row.prop(settings, "custom_height", text="H")
        else:
            resolution_row.prop(settings, "mask_resolution", text="")
        resolution_row.prop(
            settings,
            "use_custom_resolution",
            text="",
            icon="PREFERENCES",
            toggle=True,
        )

        margin_row = box.row(align=True)
        margin_row.prop(settings, "mask_margin", text="Margin")
        margin_row.prop(
            settings,
            "mask_margin_locked",
            text="",
            icon="LOCKED" if settings.mask_margin_locked else "UNLOCKED",
            toggle=True,
        )


def tool_poll(context) -> bool:
    return is_uv_editor(context)
