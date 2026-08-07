from __future__ import annotations

import bpy


class SR_Settings(bpy.types.PropertyGroup):
    # サイドバーの折りたたみ状態。ツール UI の開閉アイコンと連動する。
    expanded: bpy.props.BoolProperty(default=True)
    preserve_boundaries: bpy.props.BoolProperty(
        name="Preserve Boundaries",
        description="Prevent boundary vertices from moving toward their adjacent faces",
        default=True,
    )
    strength: bpy.props.FloatProperty(
        name="Strength",
        description="Amount of tangential relaxation applied in each iteration",
        default=0.5,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    iterations: bpy.props.IntProperty(
        name="Iterations",
        description="Number of relaxation passes",
        default=5,
        min=1,
        max=50,
    )
