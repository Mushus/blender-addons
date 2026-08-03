import bmesh
import bpy


def uv_vertex_selected(loop, uv_layer) -> bool:
    if hasattr(loop, "uv_select_vert"):
        return loop.uv_select_vert
    return loop[uv_layer].select


def selected_uv_face_indices(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.verify()
    use_uv_select_sync = bpy.context.scene.tool_settings.use_uv_select_sync
    return {
        face.index
        for face in bm.faces
        if face.select
        and (
            use_uv_select_sync
            or all(uv_vertex_selected(loop, uv_layer) for loop in face.loops)
        )
    }


def selected_uv_face_indices_by_object(objects):
    selected = {}
    for obj in objects:
        indices = selected_uv_face_indices(obj)
        if indices:
            selected[obj] = indices
    return selected
