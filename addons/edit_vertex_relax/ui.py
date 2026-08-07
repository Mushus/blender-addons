from __future__ import annotations

from .embedded_host.ui import draw_action_row, draw_settings_box
from .operator import EVR_OT_relax_selected_vertices


def draw_tool(context, layout):
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
    return EVR_OT_relax_selected_vertices.poll(context)