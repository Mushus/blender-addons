"""Shared UI layout helpers matching the original Loop Utility pattern."""


def draw_action_row(
    column,
    settings,
    expanded_prop,
    operator_id,
    *,
    text,
    icon=None,
    depress=False,
    split_factor=0.15,
):
    split = column.split(factor=split_factor, align=True)
    icon_name = "DOWNARROW_HLT" if getattr(settings, expanded_prop) else "RIGHTARROW"
    split.prop(settings, expanded_prop, text="", icon=icon_name)

    kwargs = {"text": text}
    if icon is not None:
        kwargs["icon"] = icon
    if depress:
        kwargs["depress"] = depress

    return split.operator(operator_id, **kwargs)


def draw_settings_box(column):
    return column.column(align=True).box().column()

