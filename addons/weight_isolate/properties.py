from __future__ import annotations

import bpy


class WI_Settings(bpy.types.PropertyGroup):
    # サイドバーの折りたたみ状態。ツール UI の開閉アイコンと連動する。
    expanded: bpy.props.BoolProperty(default=True)
