from __future__ import annotations

import bmesh
import bpy


def edit_mesh_objects(context) -> list:
    return [obj for obj in context.objects_in_mode if obj.type == "MESH" and obj.mode == "EDIT"]


def boundary_inward_direction(vert, positions):
    """Estimate the in-surface direction from a boundary vertex toward its faces."""
    face_verts = [face_vert for face in vert.link_faces for face_vert in face.verts]
    if not face_verts:
        return None

    center = positions[face_verts[0].index].copy()
    for face_vert in face_verts[1:]:
        center += positions[face_vert.index]
    center /= len(face_verts)
    inward = center - positions[vert.index]

    boundary_neighbours = [edge.other_vert(vert) for edge in vert.link_edges if edge.is_boundary]
    if len(boundary_neighbours) == 2:
        boundary_tangent = positions[boundary_neighbours[1].index] - positions[boundary_neighbours[0].index]
        if boundary_tangent.length_squared > 0.0:
            boundary_tangent.normalize()
            inward -= boundary_tangent * inward.dot(boundary_tangent)

    return inward.normalized() if inward.length_squared > 0.0 else None


def relax_selected_vertices(mesh, strength: float, iterations: int, preserve_boundaries: bool) -> tuple[int, int]:
    """Relax visible selected vertices along their local tangent planes.

    Each pass uses a position snapshot, so results do not depend on BMesh
    traversal order. With boundary preservation enabled, only the component
    that moves a boundary vertex toward its adjacent faces is removed.
    """
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    selected = [vert for vert in bm.verts if vert.select and not vert.hide]
    if not selected:
        return 0, 0

    movable = [vert for vert in selected if vert.link_edges]
    if not movable:
        return len(selected), 0
    if strength == 0.0:
        return len(selected), len(movable)

    for _ in range(iterations):
        bm.normal_update()
        positions = [vert.co.copy() for vert in bm.verts]
        displacements = []
        for vert in movable:
            neighbours = [edge.other_vert(vert) for edge in vert.link_edges]
            average = positions[neighbours[0].index].copy()
            for neighbour in neighbours[1:]:
                average += positions[neighbour.index]
            average /= len(neighbours)
            displacement = average - positions[vert.index]
            tangent_displacement = displacement - vert.normal * displacement.dot(vert.normal)
            if preserve_boundaries and any(edge.is_boundary for edge in vert.link_edges):
                inward = boundary_inward_direction(vert, positions)
                if inward is not None:
                    inward_amount = tangent_displacement.dot(inward)
                    if inward_amount > 0.0:
                        tangent_displacement -= inward * inward_amount
            displacements.append((vert, tangent_displacement * strength))

        for vert, displacement in displacements:
            vert.co += displacement

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    return len(selected), len(movable)


class EVR_OT_relax_selected_vertices(bpy.types.Operator):
    bl_idname = "edit_vertex_relax.relax_selected_vertices"
    bl_label = "Relax Selected Vertices"
    bl_description = "Relax selected vertices while preserving their local surface shape"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context) -> bool:
        return context.mode == "EDIT_MESH" and bool(edit_mesh_objects(context))

    def execute(self, context):
        settings = context.scene.edit_vertex_relax
        selected_count = 0
        movable_count = 0
        for obj in edit_mesh_objects(context):
            selected, movable = relax_selected_vertices(
                obj.data,
                settings.strength,
                settings.iterations,
                settings.preserve_boundaries,
            )
            selected_count += selected
            movable_count += movable

        if selected_count == 0:
            self.report({"WARNING"}, "Select at least one visible vertex")
            return {"CANCELLED"}
        if movable_count == 0:
            self.report({"WARNING"}, "Selected vertices need connected edges")
            return {"CANCELLED"}
        if settings.strength == 0.0:
            self.report({"INFO"}, "Strength is 0; mesh unchanged")
            return {"FINISHED"}

        self.report({"INFO"}, f"Relaxed {movable_count} selected vertices")
        return {"FINISHED"}