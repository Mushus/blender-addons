"""再読込後も生き残る登録ハンドルを driver_namespace に置く。

モジュール再読込でローカル変数・関数 identity は差し替わる一方、
bpy.utils.register_class や Scene プロパティ、host 登録は残る。
unregister が新しい参照しか知らないと古い登録が漏れ、再インストールで衝突する。
"""

from __future__ import annotations

import bpy

RUNTIME_KEY = "edit_vertex_relax.runtime.v1"
HOST_KEY = "blender_addon_tools.embedded_host.v1"


def get_state() -> dict | None:
    return bpy.app.driver_namespace.get(RUNTIME_KEY)


def begin_state() -> dict:
    """新規インストール用の空 state を置き、以降の登録ハンドルをここに追記する。"""
    state = {
        "classes": [],
        "scene_prop": None,
        "tool_id": None,
        "owner_id": None,
        "unregister_tool": None,
    }
    bpy.app.driver_namespace[RUNTIME_KEY] = state
    return state


def uninstall() -> None:
    """durable 参照だけで前回インストールを剥がす。欠落・二重呼びでも落とさない。"""
    state = get_state()
    if state is None:
        # state が消えていても Scene プロパティだけ残っていることがある。
        if hasattr(bpy.types.Scene, "edit_vertex_relax"):
            try:
                del bpy.types.Scene.edit_vertex_relax
            except (AttributeError, TypeError):
                pass
        return

    tool_id = state.get("tool_id")
    owner_id = state.get("owner_id")
    unregister_tool = state.get("unregister_tool")
    if tool_id and owner_id and unregister_tool is not None:
        try:
            unregister_tool(tool_id, owner_id)
        except Exception:
            # 保存した callback が壊れている場合、host の durable dict から直接除去する。
            host_state = bpy.app.driver_namespace.get(HOST_KEY)
            if host_state is not None:
                owners = host_state.get("tools", {}).get(tool_id)
                if owners is not None:
                    owners.pop(owner_id, None)

    scene_prop = state.get("scene_prop")
    if scene_prop and hasattr(bpy.types.Scene, scene_prop):
        try:
            delattr(bpy.types.Scene, scene_prop)
        except (AttributeError, TypeError):
            pass

    for cls in reversed(list(state.get("classes") or [])):
        try:
            bpy.utils.unregister_class(cls)
        except (RuntimeError, ValueError, ReferenceError):
            pass

    bpy.app.driver_namespace.pop(RUNTIME_KEY, None)
