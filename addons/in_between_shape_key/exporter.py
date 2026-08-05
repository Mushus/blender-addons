from __future__ import annotations

import os
import tempfile
from pathlib import Path

import bpy
from bpy_extras.io_utils import axis_conversion
from mathutils import Matrix

from .postprocess import process_file
from .validation import validate_all_meshes


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
            raise RuntimeError("FBX filepath is empty")
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


def export_with_inbetweens(operator, context) -> set[str]:
    if getattr(operator, "batch_mode", "OFF") != "OFF":
        operator.report({"ERROR"}, "Batch FBX export is not supported by Shape Key In-Between")
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
        result = _standard_export(operator, context, temporary)
        if result != {"FINISHED"}:
            return result
        if _has_annotated_shape_keys():
            process_file(temporary, str(destination))
        else:
            os.replace(temporary, destination)
    except Exception as exc:
        operator.report({"ERROR"}, f"Shape Key In-Between export failed: {exc}")
        return {"CANCELLED"}
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    operator.report({"INFO"}, f"Exported FBX with Shape Key In-Betweens: {destination}")
    return {"FINISHED"}
