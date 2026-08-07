from __future__ import annotations

import sys
from importlib import import_module, reload

import bpy

bl_info = {
    "name": "Slide Relax",
    "author": "Mushus",
    "version": (2026, 8, 7),
    "blender": (5, 1, 0),
    "location": "3D View > Sidebar > Edit",
    "description": "Relax selected Edit Mode vertices along their local tangent planes.",
    "category": "Mesh",
}

_tool_id = "slide_relax"

# reload 順: 依存先を先に読む。runtime は register 側で別途取り直す。
_CHILD_MODULES = (
    "runtime",
    "embedded_host.registry",
    "embedded_host.ui",
    "embedded_host",
    "properties",
    "operator",
    "ui",
)


def _reload_child_modules() -> None:
    """再読込後の実装モジュールへ差し替える。"""
    for module_name in _CHILD_MODULES:
        module = sys.modules.get(f"{__package__}.{module_name}")
        if module is not None:
            reload(module)


def _bindings():
    host = import_module(f"{__package__}.embedded_host")
    operator_module = import_module(f"{__package__}.operator")
    properties_module = import_module(f"{__package__}.properties")
    ui_module = import_module(f"{__package__}.ui")
    return host, operator_module, properties_module, ui_module


def register() -> None:
    # モジュール再読込でローカル参照は消えるが、RNA / host 登録は残る。
    # 先に durable uninstall してから reload しないと二重登録になる。
    runtime_mod = import_module(f"{__package__}.runtime")
    runtime_mod.uninstall()
    _reload_child_modules()
    runtime_mod = import_module(f"{__package__}.runtime")

    host, operator_module, properties_module, ui_module = _bindings()
    classes = (properties_module.SR_Settings, operator_module.SR_OT_slide_relax)

    # 以後の登録ハンドルはすべて state に保存し、uninstall はこれだけを見る。
    state = runtime_mod.begin_state()
    for cls in classes:
        bpy.utils.register_class(cls)
        state["classes"].append(cls)

    bpy.types.Scene.slide_relax = bpy.props.PointerProperty(type=properties_module.SR_Settings)
    state["scene_prop"] = "slide_relax"
    state["tool_id"] = _tool_id
    state["owner_id"] = __package__
    # host.unregister_tool は reload 後に差し替わるため、登録時点の関数を保持する。
    state["unregister_tool"] = host.unregister_tool

    host.register_tool(
        host.ToolSpec(
            tool_id=_tool_id,
            owner_id=__package__,
            display_name="Slide Relax",
            group_id="mesh_utility",
            group_label="Mesh Utility",
            sort_order=100,
            space_type="VIEW_3D",
            region_type="UI",
            category="Edit",
            poll=ui_module.tool_poll,
            draw=ui_module.draw_tool,
        )
    )


def unregister() -> None:
    # モジュールグローバルに依存しない。durable state だけを辿る。
    runtime_mod = sys.modules.get(f"{__package__}.runtime")
    if runtime_mod is None:
        runtime_mod = import_module(f"{__package__}.runtime")
    runtime_mod.uninstall()
