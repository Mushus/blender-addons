from __future__ import annotations

import bpy


class WSA_Settings(bpy.types.PropertyGroup):
    # サイドバーの折りたたみ状態。ツール UI の開閉アイコンと連動する。
    expanded: bpy.props.BoolProperty(default=True)
    factor: bpy.props.FloatProperty(
        name="Factor",
        description="Blend amount toward neighboring bone weights each iteration",
        default=0.5,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    iterations: bpy.props.IntProperty(
        name="Iterations",
        description="Number of weight smoothing passes",
        default=5,
        min=1,
        max=50,
    )
