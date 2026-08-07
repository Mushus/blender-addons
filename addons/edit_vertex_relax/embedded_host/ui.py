"""Shared UI layout helpers matching the existing utility tools."""


def draw_action_row(column, settings, expanded_prop, operator_id, *, text, split_factor=0.15):
    split = column.split(factor=split_factor, align=True)
    icon_name = "DOWNARROW_HLT" if getattr(settings, expanded_prop) else "RIGHTARROW"
    split.prop(settings, expanded_prop, text="", icon=icon_name)
    return split.operator(operator_id, text=text)


def draw_settings_box(column):
    return column.column(align=True).box().column()
