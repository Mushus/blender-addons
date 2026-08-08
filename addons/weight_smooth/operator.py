from __future__ import annotations

import bmesh
import bpy


class WeightSmoothError(Exception):
    """仕様違反・前提不足。オペレータは即時 CANCELLED にする。"""


def weight_paint_objects(context) -> list:
    """Weight Paint 中のメッシュだけを対象にする（マルチオブジェクト対応）。"""
    return [
        obj
        for obj in context.objects_in_mode
        if obj.type == "MESH" and obj.mode == "WEIGHT_PAINT"
    ]


def find_armature(obj) -> bpy.types.Object | None:
    for modifier in obj.modifiers:
        if modifier.type == "ARMATURE" and modifier.object is not None:
            return modifier.object
    if obj.parent is not None and obj.parent.type == "ARMATURE":
        return obj.parent
    return None


def deform_group_indices(obj) -> tuple[list[int], list[int]]:
    """ボーン変形用 VG を (unlocked, locked) の index リストで返す。"""
    armature = find_armature(obj)
    if armature is None:
        raise WeightSmoothError(f"{obj.name}: Armature not found")

    deform_names = {bone.name for bone in armature.data.bones if bone.use_deform}
    unlocked: list[int] = []
    locked: list[int] = []
    for group in obj.vertex_groups:
        if group.name not in deform_names:
            continue
        if group.lock_weight:
            locked.append(group.index)
        else:
            unlocked.append(group.index)
    return unlocked, locked


def ensure_vertex_select_mask(mesh) -> bool:
    """Weight Paint の頂点選択マスクを有効化する。変更したら True。"""
    changed = False
    # 面マスクと頂点マスクは同時に使えない前提で、頂点側へ寄せる。
    if mesh.use_paint_mask:
        mesh.use_paint_mask = False
        changed = True
    if not mesh.use_paint_mask_vertex:
        mesh.use_paint_mask_vertex = True
        changed = True
    return changed


def _weight(dvert, group_index: int) -> float:
    return dvert.get(group_index, 0.0)


def _set_weight(dvert, group_index: int, value: float) -> None:
    if value <= 0.0:
        if group_index in dvert:
            del dvert[group_index]
        return
    dvert[group_index] = value


def smooth_all_weights(obj, factor: float, iterations: int) -> tuple[int, int]:
    """選択頂点の全アンロック変形ウェイトを近傍平均へ寄せ、最後に正規化する。

    未選択頂点・ロック VG・非ボーン VG は書き込まない。
    Weight Paint では Mesh.vertices.select を正とし、bmesh は近傍・deform 更新に使う。
    """
    unlocked, locked = deform_group_indices(obj)
    if not unlocked and not locked:
        raise WeightSmoothError(f"{obj.name}: No deform bone vertex groups")
    if not unlocked:
        raise WeightSmoothError(f"{obj.name}: No unlocked deform bone vertex groups")

    mesh = obj.data
    selected_indices = {
        vert.index for vert in mesh.vertices if vert.select and not vert.hide
    }
    if not selected_indices:
        return 0, 0

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    deform_layer = bm.verts.layers.deform.verify()

    selected = [bm.verts[index] for index in sorted(selected_indices)]
    # 孤立頂点は近傍平均が取れないのでスムーズ対象外（Normalize は行う）。
    smoothable = [vert for vert in selected if vert.link_edges]
    tracked = unlocked + locked

    if factor > 0.0 and smoothable:
        for _ in range(iterations):
            # 同一パス内は更新前ウェイトだけを見る。順番依存のバイアスを避ける。
            snapshot = {
                vert.index: {group: _weight(vert[deform_layer], group) for group in tracked}
                for vert in bm.verts
            }
            updates: list[tuple[object, int, float]] = []
            for vert in smoothable:
                neighbours = [edge.other_vert(vert) for edge in vert.link_edges]
                dvert = vert[deform_layer]
                for group in unlocked:
                    average = sum(snapshot[neighbour.index][group] for neighbour in neighbours)
                    average /= len(neighbours)
                    old = snapshot[vert.index][group]
                    updates.append((dvert, group, (1.0 - factor) * old + factor * average))
            for dvert, group, value in updates:
                _set_weight(dvert, group, value)

    # ロック分を温存し、残りをアンロック VG へ再配分する（Blender Normalize All と同型）。
    for vert in selected:
        dvert = vert[deform_layer]
        locked_sum = sum(_weight(dvert, group) for group in locked)
        remaining = max(0.0, 1.0 - locked_sum)
        unlocked_sum = sum(_weight(dvert, group) for group in unlocked)
        if unlocked_sum > 0.0:
            scale = remaining / unlocked_sum
            for group in unlocked:
                _set_weight(dvert, group, _weight(dvert, group) * scale)
        elif remaining == 0.0:
            for group in unlocked:
                _set_weight(dvert, group, 0.0)

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return len(selected), len(smoothable)


class WS_OT_smooth(bpy.types.Operator):
    bl_idname = "weight_smooth.smooth"
    bl_label = "Smooth Weight"
    bl_description = (
        "Smooth and normalize all deform bone weights on selected vertices. "
        "Enables Weight Paint vertex selection when it is off"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context) -> bool:
        return context.mode == "PAINT_WEIGHT" and bool(weight_paint_objects(context))

    def execute(self, context):
        objects = weight_paint_objects(context)
        # 頂点選択マスクが切れていると選択が効かない。先に有効化して終了する。
        enabled_masks = False
        for obj in objects:
            if ensure_vertex_select_mask(obj.data):
                enabled_masks = True
        if enabled_masks:
            self.report({"INFO"}, "Enabled vertex selection; select vertices and run again")
            return {"FINISHED"}

        settings = context.scene.weight_smooth
        selected_count = 0
        smoothable_count = 0
        try:
            for obj in objects:
                selected, smoothable = smooth_all_weights(
                    obj,
                    settings.factor,
                    settings.iterations,
                )
                selected_count += selected
                smoothable_count += smoothable
        except WeightSmoothError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        if selected_count == 0:
            self.report({"WARNING"}, "Select at least one visible vertex")
            return {"CANCELLED"}
        if smoothable_count == 0 and settings.factor > 0.0:
            self.report({"WARNING"}, "Selected vertices need connected edges")
            return {"CANCELLED"}
        if settings.factor == 0.0:
            self.report({"INFO"}, f"Normalized weights on {selected_count} selected vertices")
            return {"FINISHED"}

        self.report({"INFO"}, f"Smoothed weights on {smoothable_count} selected vertices")
        return {"FINISHED"}
