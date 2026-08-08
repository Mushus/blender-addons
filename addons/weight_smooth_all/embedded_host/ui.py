"""既存ユーティリティツールと揃えたサイドバー用レイアウトヘルパ。"""


def draw_action_row(column, settings, expanded_prop, operator_id, *, text, split_factor=0.15):
    """折りたたみ矢印 + 実行ボタンを 1 行に並べる。"""
    split = column.split(factor=split_factor, align=True)
    icon_name = "DOWNARROW_HLT" if getattr(settings, expanded_prop) else "RIGHTARROW"
    split.prop(settings, expanded_prop, text="", icon=icon_name)
    return split.operator(operator_id, text=text)


def draw_settings_box(column):
    return column.column(align=True).box().column()
