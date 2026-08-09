from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import bpy
from bpy.app.translations import pgettext_iface
from bpy_extras.io_utils import axis_conversion
from mathutils import Matrix

from .postprocess import process_file
from .validation import validate_all_meshes


def _message(source: str, **values) -> str:
    return pgettext_iface(source).format(**values)


def _has_annotated_shape_keys() -> bool:
    return any(
        obj.type == "MESH"
        and obj.data.shape_keys is not None
        and any("@" in block.name for block in obj.data.shape_keys.key_blocks)
        for obj in bpy.data.objects
    )


def _standard_export(operator, context, filepath: str):
    original_filepath = operator.filepath
    operator.filepath = filepath
    try:
        if not operator.filepath:
            raise RuntimeError(_message("FBX filepath is empty"))
        global_matrix = (
            axis_conversion(to_forward=operator.axis_forward, to_up=operator.axis_up).to_4x4()
            if operator.use_space_transform
            else Matrix()
        )
        keywords = operator.as_keywords(ignore=("check_existing", "filter_glob", "ui_tab"))
        keywords["global_matrix"] = global_matrix
        from io_scene_fbx import export_fbx_bin

        return export_fbx_bin.save(operator, context, **keywords)
    finally:
        operator.filepath = original_filepath


def _has_addon_drivers(key) -> bool:
    animation_data = key.animation_data
    return animation_data is not None and any(
        any(variable.name == "fbxi_controller" for variable in fcurve.driver.variables)
        for fcurve in animation_data.drivers
    )


def _remove_addon_drivers(key) -> None:
    animation_data = key.animation_data
    if animation_data is None:
        return
    for fcurve in list(animation_data.drivers):
        if not any(variable.name == "fbxi_controller" for variable in fcurve.driver.variables):
            continue
        block = next(
            (
                block
                for block in key.key_blocks
                if block.path_from_id("value") == fcurve.data_path
            ),
            None,
        )
        if block is None:
            animation_data.drivers.remove(fcurve)
        else:
            block.driver_remove("value")


@contextmanager
def _driver_free_mesh_copies(context):
    originals = []
    copies = {}
    try:
        for obj in bpy.data.objects:
            if obj.type != "MESH" or obj.data.shape_keys is None:
                continue
            original_key = obj.data.shape_keys
            if not _has_addon_drivers(original_key):
                continue
            key_id = original_key.session_uid
            copied_mesh = copies.get(key_id)
            if copied_mesh is None:
                copied_mesh = obj.data.copy()
                copied_key = copied_mesh.shape_keys
                if copied_key is None:
                    raise RuntimeError(
                        _message("Shape Keys were not copied for FBX export: {name}", name=obj.name)
                    )
                values = {block.name: float(block.value) for block in original_key.key_blocks}
                _remove_addon_drivers(copied_key)
                for block in copied_key.key_blocks:
                    block.value = values[block.name]
                copies[key_id] = copied_mesh
            originals.append((obj, obj.data))
            obj.data = copied_mesh
        context.view_layer.update()
        yield
    finally:
        for obj, original_mesh in originals:
            obj.data = original_mesh
        context.view_layer.update()
        for copied_mesh in copies.values():
            bpy.data.meshes.remove(copied_mesh)


def export_with_inbetweens(operator, context) -> set[str]:
    if getattr(operator, "batch_mode", "OFF") != "OFF":
        operator.report(
            {"ERROR"},
            _message("Batch FBX export is not supported by Shape Key In-Between"),
        )
        return {"CANCELLED"}
    validation = validate_all_meshes(bpy.data)
    if validation.errors:
        operator.report({"ERROR"}, validation.errors[0])
        return {"CANCELLED"}
    destination = Path(operator.filepath).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="fbxi-export-", suffix=".fbx", dir=str(destination.parent))
    os.close(fd)
    try:
        with _driver_free_mesh_copies(context):
            result = _standard_export(operator, context, temporary)
        if result != {"FINISHED"}:
            return result
        if _has_annotated_shape_keys():
            process_file(temporary, str(destination))
        else:
            os.replace(temporary, destination)
    except Exception as exc:
        operator.report(
            {"ERROR"},
            _message("Shape Key In-Between export failed: {error}", error=exc),
        )
        return {"CANCELLED"}
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    operator.report(
        {"INFO"},
        _message("Exported FBX with Shape Key In-Betweens: {path}", path=destination),
    )
    return {"FINISHED"}
