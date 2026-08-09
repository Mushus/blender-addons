from __future__ import annotations

from scaffold.embedded_host.ui import draw_action_row, draw_settings_box

from .operator import WS_OT_smooth


def draw_tool(context, layout):
    """host パネルから呼ばれる 1 ツール分の描画。"""
    settings = context.scene.weight_smooth
    column = layout.column(align=True)
    draw_action_row(
        column,
        settings,
        "expanded",
        WS_OT_smooth.bl_idname,
        text="Smooth Weight",
    )
    if settings.expanded:
        box = draw_settings_box(column)
        box.prop(settings, "factor")
        box.prop(settings, "iterations")


def tool_poll(context) -> bool:
    """オペレータと同じ条件でパネル行の活性を揃える。"""
    return WS_OT_smooth.poll(context)
