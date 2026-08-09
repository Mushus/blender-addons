from __future__ import annotations

from scaffold.embedded_host.ui import draw_action_row, draw_settings_box
from .operator import WI_OT_isolate


def draw_tool(context, layout):
    """host パネルから呼ばれる 1 ツール分の描画。"""
    settings = context.scene.weight_isolate
    column = layout.column(align=True)
    draw_action_row(
        column,
        settings,
        "expanded",
        WI_OT_isolate.bl_idname,
        text="Isolate Weight",
    )
    if settings.expanded:
        box = draw_settings_box(column)
        box.label(text="Active bone → 1, others → 0", icon="INFO")


def tool_poll(context) -> bool:
    """オペレータと同じ条件でパネル行の活性を揃える。"""
    return WI_OT_isolate.poll(context)
