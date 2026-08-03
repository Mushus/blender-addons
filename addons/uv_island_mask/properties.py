import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty

_RESOLUTION_ITEMS = (
    ("64", "64", "64 x 64 pixels"),
    ("128", "128", "128 x 128 pixels"),
    ("256", "256", "256 x 256 pixels"),
    ("512", "512", "512 x 512 pixels"),
    ("1024", "1024", "1024 x 1024 pixels"),
    ("2048", "2048", "2048 x 2048 pixels"),
    ("4096", "4096", "4096 x 4096 pixels"),
    ("8192", "8192", "8192 x 8192 pixels"),
)


def _auto_margin(settings) -> int:
    if settings.use_custom_resolution:
        resolution = max(settings.custom_width, settings.custom_height)
    else:
        resolution = int(settings.mask_resolution)
    return max(1, resolution // 64)


def _update_auto_margin(settings, _context):
    if settings.mask_margin_locked:
        settings.mask_margin = _auto_margin(settings)


def get_resolution(settings) -> tuple[int, int]:
    if settings.use_custom_resolution:
        return settings.custom_width, settings.custom_height
    resolution = int(settings.mask_resolution)
    return resolution, resolution


class UVIM_Settings(bpy.types.PropertyGroup):
    expanded: BoolProperty(
        name="UV Island Mask settings",
        description="Display UV Island Mask settings",
        default=False,
    )
    mask_resolution: EnumProperty(
        name="Resolution",
        description="Choose a square mask resolution",
        items=_RESOLUTION_ITEMS,
        default="1024",
        update=_update_auto_margin,
    )
    use_custom_resolution: BoolProperty(
        name="Custom",
        description="Specify width and height independently",
        default=False,
        update=_update_auto_margin,
    )
    custom_width: IntProperty(
        name="Width",
        description="Custom mask width in pixels",
        default=1024,
        min=4,
        max=8192,
        update=_update_auto_margin,
    )
    custom_height: IntProperty(
        name="Height",
        description="Custom mask height in pixels",
        default=1024,
        min=4,
        max=8192,
        update=_update_auto_margin,
    )
    mask_margin: IntProperty(
        name="Margin",
        description="Bake margin in pixels",
        default=16,
        min=0,
        max=32767,
        subtype="PIXEL",
    )
    mask_margin_locked: BoolProperty(
        name="Auto Margin",
        description="Update margin automatically when the resolution changes",
        default=True,
    )
