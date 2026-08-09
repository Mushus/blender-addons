from __future__ import annotations

from scaffold.embedded_host.ui import draw_action_row, draw_settings_box

from .operator import SR_OT_slide_relax


def draw_tool(context, layout):
    """host パネルから呼ばれる 1 ツール分の描画。"""
    settings = context.scene.slide_relax
    column = layout.column(align=True)
    draw_action_row(
        column,
        settings,
        "expanded",
        SR_OT_slide_relax.bl_idname,
        text="Slide Relax",
    )
    if settings.expanded:
        box = draw_settings_box(column)
        box.prop(settings, "strength")
        box.prop(settings, "iterations")
        box.prop(settings, "preserve_boundaries")


def tool_poll(context) -> bool:
    """オペレータと同じ条件でパネル行の活性を揃える。"""
    return SR_OT_slide_relax.poll(context)
