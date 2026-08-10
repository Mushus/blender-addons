from __future__ import annotations

import bpy


class WH_Settings(bpy.types.PropertyGroup):
    expanded: bpy.props.BoolProperty(default=True)
    iterations: bpy.props.IntProperty(
        name="Iterations",
        description="Number of heat diffusion passes",
        default=5,
        min=1,
        max=50,
    )
