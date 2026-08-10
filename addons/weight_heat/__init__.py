from __future__ import annotations

import sys
from importlib import import_module, reload
from pathlib import Path

# Repo checkout: addons/<tool> → parents[2] is the monorepo root (scaffold lives there).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if (_REPO_ROOT / "scaffold" / "embedded_host").is_dir():
    _root = str(_REPO_ROOT)
    if _root not in sys.path:
        sys.path.insert(0, _root)

import bpy

bl_info = {
    "name": "Heat Weight",
    "author": "Mushus",
    "version": (2026, 8, 10),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > Edit",
    "description": "Diffuse deform weights by heat diffusion for decisive blur",
    "category": "Paint",
}

_tool_id = "weight_heat"

# reload 順: 依存先を先に読む。runtime は register 側で別途取り直す。
# scaffold.* は make_zip 時に embedded_host.* へ書き換えられ、_qualname 経由で __package__ 配下になる。
_CHILD_MODULES = (
    "runtime",
    "scaffold.embedded_host.registry",
    "scaffold.embedded_host.ui",
    "scaffold.embedded_host",
    "properties",
    "i18n",
    "operator",
    "ui",
)


def _qualname(module_name: str) -> str:
    if module_name.startswith("scaffold."):
        return module_name
    return f"{__package__}.{module_name}"


def _reload_child_modules() -> None:
    """再読込後の実装モジュールへ差し替える。"""
    for module_name in _CHILD_MODULES:
        module = sys.modules.get(_qualname(module_name))
        if module is not None:
            reload(module)


def _bindings():
    host = import_module(_qualname("scaffold.embedded_host"))
    operator_module = import_module(_qualname("operator"))
    properties_module = import_module(_qualname("properties"))
    ui_module = import_module(_qualname("ui"))
    i18n_module = import_module(_qualname("i18n"))
    return host, operator_module, properties_module, ui_module, i18n_module


def register() -> None:
    runtime_mod = import_module(_qualname("runtime"))
    runtime_mod.uninstall()
    _reload_child_modules()
    runtime_mod = import_module(_qualname("runtime"))

    host, operator_module, properties_module, ui_module, i18n_module = _bindings()
    classes = (properties_module.WH_Settings, operator_module.WH_OT_heat)

    # 以後の登録ハンドルはすべて state に保存し、uninstall はこれだけを見る。
    state = runtime_mod.begin_state()
    i18n_module.register()
    state["i18n_unregister"] = i18n_module.unregister

    for cls in classes:
        bpy.utils.register_class(cls)
        state["classes"].append(cls)

    bpy.types.Scene.weight_heat = bpy.props.PointerProperty(type=properties_module.WH_Settings)
    state["scene_prop"] = "weight_heat"
    state["tool_id"] = _tool_id
    state["owner_id"] = __package__
    state["unregister_tool"] = host.unregister_tool

    host.register_tool(
        host.ToolSpec(
            tool_id=_tool_id,
            owner_id=__package__,
            display_name="Heat Weight",
            group_id="weight_utility",
            group_label="Weight Utility",
            sort_order=110,
            space_type="VIEW_3D",
            region_type="UI",
            category="Edit",
            poll=ui_module.tool_poll,
            draw=ui_module.draw_tool,
        )
    )


def unregister() -> None:
    runtime_mod = sys.modules.get(_qualname("runtime"))
    if runtime_mod is None:
        runtime_mod = import_module(_qualname("runtime"))
    runtime_mod.uninstall()
