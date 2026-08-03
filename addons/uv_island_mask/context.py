def is_uv_editor(context) -> bool:
    area = context.area
    space_data = context.space_data
    return (
        area is not None
        and area.type == "IMAGE_EDITOR"
        and space_data is not None
        and getattr(space_data, "mode", getattr(space_data, "ui_mode", None)) == "UV"
    )


def edit_mesh_objects(context):
    objects = [
        obj
        for obj in getattr(context, "objects_in_mode_unique_data", ())
        if obj.type == "MESH" and obj.mode == "EDIT"
    ]
    if objects:
        return objects

    obj = context.active_object
    return [obj] if obj is not None and obj.type == "MESH" and obj.mode == "EDIT" else []


def _candidate_image_editor_areas(context):
    candidate_areas = []
    if getattr(context, "area", None) is not None:
        candidate_areas.append(context.area)
    if getattr(context, "screen", None) is not None:
        candidate_areas.extend(area for area in context.screen.areas if area not in candidate_areas)
    window_manager = getattr(context, "window_manager", None)
    for window in getattr(window_manager, "windows", ()):
        for area in window.screen.areas:
            if area not in candidate_areas:
                candidate_areas.append(area)

    return candidate_areas


def show_image_in_image_editor(context, image) -> bool:
    """Assign an image to every visible UV/Image Editor and redraw them."""
    candidate_areas = _candidate_image_editor_areas(context)

    def area_priority(area):
        if area.type != "IMAGE_EDITOR":
            return 2
        space = area.spaces.active
        mode = getattr(space, "mode", getattr(space, "ui_mode", None))
        return 0 if mode == "UV" else 1

    updated = False
    for area in sorted(candidate_areas, key=area_priority):
        if area.type != "IMAGE_EDITOR":
            continue
        space = area.spaces.active
        if space.type != "IMAGE_EDITOR":
            continue
        space.image = image
        area.tag_redraw()
        updated = True

    return updated
