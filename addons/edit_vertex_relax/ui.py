from __future__ import annotations

from .embedded_host.ui import draw_action_row, draw_settings_box
from .operator import EVR_OT_relax_selected_vertices


def draw_tool(context, layout):
    """host パネルから呼ばれる 1 ツール分の描画。"""
    settings = context.scene.edit_vertex_relax
    column = layout.column(align=True)
    draw_action_row(
        column,
        settings,
        "expanded",
        EVR_OT_relax_selected_vertices.bl_idname,
        text="Relax Selected Vertices",
    )
    if settings.expanded:
        box = draw_settings_box(column)
        box.prop(settings, "strength")
        box.prop(settings, "preserve_boundaries")
        box.prop(settings, "iterations")


def tool_poll(context) -> bool:
    """オペレータと同じ条件でパネル行の活性を揃える。"""
    return EVR_OT_relax_selected_vertices.poll(context)
