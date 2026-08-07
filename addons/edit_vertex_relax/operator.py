from __future__ import annotations

import bmesh
import bpy


def edit_mesh_objects(context) -> list:
    """マルチオブジェクト編集時も、Edit Mode 中のメッシュだけを対象にする。"""
    return [obj for obj in context.objects_in_mode if obj.type == "MESH" and obj.mode == "EDIT"]


def boundary_inward_direction(vert, positions):
    """境界頂点から隣接面側へ向かう、接線平面上の内向き方向を推定する。

    隣接面頂点の重心方向を内向き候補とし、境界辺が 2 本あるときは
    境界接線成分を差し引く。境界に沿った移動は「内向き」ではないため。
    """
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
    """選択頂点を局所接線平面上で緩和する。

    各パスは座標スナップショット上で変位を計算する。BMesh 走査順に依存しない。
    境界保持時は、境界頂点を隣接面側へ押し込む接線成分だけを除去する。
    境界に沿った移動は残し、輪郭の収縮を防ぐ。
    """
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    selected = [vert for vert in bm.verts if vert.select and not vert.hide]
    if not selected:
        return 0, 0

    # 孤立頂点は近傍平均が取れないので緩和対象外。
    movable = [vert for vert in selected if vert.link_edges]
    if not movable:
        return len(selected), 0
    if strength == 0.0:
        return len(selected), len(movable)

    for _ in range(iterations):
        bm.normal_update()
        # 同一パス内は更新前座標だけを見る。順番依存のバイアスを避ける。
        positions = [vert.co.copy() for vert in bm.verts]
        displacements = []
        for vert in movable:
            neighbours = [edge.other_vert(vert) for edge in vert.link_edges]
            average = positions[neighbours[0].index].copy()
            for neighbour in neighbours[1:]:
                average += positions[neighbour.index]
            average /= len(neighbours)
            displacement = average - positions[vert.index]
            # 法線成分を落とし、表面形状（厚み方向）を保つ。
            tangent_displacement = displacement - vert.normal * displacement.dot(vert.normal)
            if preserve_boundaries and any(edge.is_boundary for edge in vert.link_edges):
                inward = boundary_inward_direction(vert, positions)
                if inward is not None:
                    inward_amount = tangent_displacement.dot(inward)
                    # 外向きや境界沿いの成分は削らない。収縮方向だけ除去。
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
