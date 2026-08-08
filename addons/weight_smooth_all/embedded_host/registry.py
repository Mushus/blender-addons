"""複数ツールを 1 つのサイドバーパネルに束ねる埋め込みホスト。

各アドオン ZIP は自己完結のため host を同梱する。実体の共有は
driver_namespace 上の durable dict で行い、最後のツールが外れたら
パネルと state ごと消す。
"""

from dataclasses import dataclass

import bpy

_STATE_KEY = "blender_addon_tools.embedded_host.v1"


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    owner_id: str
    display_name: str
    group_id: str
    group_label: str
    sort_order: int
    space_type: str
    region_type: str
    category: str
    poll: object
    draw: object


def _state():
    state = bpy.app.driver_namespace.get(_STATE_KEY)
    if state is None:
        state = {"tools": {}, "groups": {}}
        bpy.app.driver_namespace[_STATE_KEY] = state
    return state


def _group_specs(state, group_id):
    """グループ内ツールを sort_order → tool_id で安定ソートする。"""
    return sorted(
        [
            spec
            for tool_id, owners in state["tools"].items()
            if state["groups"].get(group_id, {}).get("tool_ids", {}).get(tool_id)
            for spec in owners.values()
        ],
        key=lambda spec: (spec.sort_order, spec.tool_id),
    )


def _safe_poll(spec, context):
    # 1 ツールの poll 例外でパネル全体を落とさない。
    try:
        return bool(spec.poll(context))
    except Exception:
        return False


def _make_panel(state, group_id, spec):
    """グループ初回登録時だけ Panel クラスを動的生成する。"""
    panel_name = f"BLENDER_ADDON_TOOLS_PT_{group_id}"

    def poll(cls, context):
        return any(_safe_poll(tool, context) for tool in _group_specs(state, group_id))

    def draw(self, context):
        for tool in _group_specs(state, group_id):
            tool.draw(context, self.layout)

    return type(
        panel_name,
        (bpy.types.Panel,),
        {
            "bl_idname": panel_name,
            "bl_label": spec.group_label,
            "bl_space_type": spec.space_type,
            "bl_region_type": spec.region_type,
            "bl_category": spec.category,
            "poll": classmethod(poll),
            "draw": draw,
        },
    )


def _ensure_group(state, spec):
    group = state["groups"].get(spec.group_id)
    if group is not None:
        group["tool_ids"][spec.tool_id] = True
        return

    panel = _make_panel(state, spec.group_id, spec)
    bpy.utils.register_class(panel)
    state["groups"][spec.group_id] = {"panel": panel, "tool_ids": {spec.tool_id: True}}


def register_tool(spec: ToolSpec):
    state = _state()
    # 同一 tool_id を複数 owner が持てる（再インストール中の過渡状態向け）。
    owners = state["tools"].setdefault(spec.tool_id, {})
    owners[spec.owner_id] = spec
    _ensure_group(state, spec)


def unregister_tool(tool_id: str, owner_id: str):
    state = bpy.app.driver_namespace.get(_STATE_KEY)
    if state is None:
        return

    owners = state["tools"].get(tool_id)
    if owners is None:
        return
    owners.pop(owner_id, None)
    # 他 owner が残っている間はパネルを維持する。
    if owners:
        return

    state["tools"].pop(tool_id, None)
    for group_id, group in list(state["groups"].items()):
        group["tool_ids"].pop(tool_id, None)
        if group["tool_ids"]:
            continue
        try:
            bpy.utils.unregister_class(group["panel"])
        except RuntimeError:
            pass
        state["groups"].pop(group_id, None)

    if not state["tools"]:
        bpy.app.driver_namespace.pop(_STATE_KEY, None)
