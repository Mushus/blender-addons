from __future__ import annotations

import bmesh
import bpy


class WeightIsolateError(Exception):
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
        raise WeightIsolateError(f"{obj.name}: Armature not found")

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


def isolate_weights(obj, target_name: str) -> tuple[int, int]:
    """選択頂点のウェイトを target ボーン=1、その他変形ボーン=0 にする。

    - 未選択頂点・非ボーン VG は書き込まない。
    - ロック VG は温存し、target へは残り (1 - locked_sum) を割り当てる。
    - Weight Paint では Mesh.vertices.select を正とし、bmesh は deform 更新に使う。
    """
    unlocked, locked = deform_group_indices(obj)
    if not unlocked and not locked:
        raise WeightIsolateError(f"{obj.name}: No deform bone vertex groups")

    target_group = obj.vertex_groups.get(target_name)
    if target_group is None:
        raise WeightIsolateError(f"{obj.name}: Active bone '{target_name}' not found")
    target_index = target_group.index

    # target が変形ボーンか判定
    if target_index not in unlocked and target_index not in locked:
        raise WeightIsolateError(f"{obj.name}: Active bone '{target_name}' is not a deform bone")
    if target_index in locked:
        raise WeightIsolateError(f"{obj.name}: Active bone '{target_name}' is locked")
    if target_index not in unlocked:
        raise WeightIsolateError(f"{obj.name}: No unlocked deform bone vertex groups")

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

    for vert in selected:
        dvert = vert[deform_layer]
        locked_sum = sum(_weight(dvert, group) for group in locked)
        remaining = max(0.0, 1.0 - locked_sum)
        for group in unlocked:
            if group == target_index:
                _set_weight(dvert, group, remaining)
            else:
                _set_weight(dvert, group, 0.0)

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return len(selected), len(selected)


def active_bone_name(context, objects: list) -> str | None:
    """現在指定ボーン名を active vertex group から取得する。"""
    # 1) active object の active vertex group を優先
    active_obj = context.object
    if active_obj is not None and active_obj.type == "MESH" and active_obj in objects:
        vg = active_obj.vertex_groups.active
        if vg is not None:
            return vg.name
    # 2) fallback: weight paint objects の中で最初に見つかった active
    for obj in objects:
        vg = obj.vertex_groups.active
        if vg is not None:
            return vg.name
    return None


class WI_OT_isolate(bpy.types.Operator):
    bl_idname = "weight_isolate.isolate"
    bl_label = "Isolate Weight"
    bl_description = (
        "Set active bone weight to 1 and other deform bone weights to 0 on selected vertices. "
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

        target_name = active_bone_name(context, objects)
        if target_name is None:
            self.report({"ERROR"}, "No active bone / vertex group selected")
            return {"CANCELLED"}

        selected_count = 0
        try:
            for obj in objects:
                selected, _ = isolate_weights(obj, target_name)
                selected_count += selected
        except WeightIsolateError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        if selected_count == 0:
            self.report({"WARNING"}, "Select at least one visible vertex")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Isolated {target_name} weight on {selected_count} selected vertices")
        return {"FINISHED"}
