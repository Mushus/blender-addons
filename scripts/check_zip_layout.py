from __future__ import annotations

import json
import zipfile
from pathlib import Path


def main() -> None:
    dist = Path("dist")
    package_zips = {
        "uv_island_mask": {
            "uv_island_mask/__init__.py",
            "uv_island_mask/runtime.py",
            "uv_island_mask/embedded_host/registry.py",
            "uv_island_mask/tool_manifest.json",
        },
        "in_between_shape_key": {"in_between_shape_key/__init__.py", "in_between_shape_key/runtime.py", "in_between_shape_key/postprocess.py"},
    }
    for package_id, required in package_zips.items():
        path = dist / f"{package_id}.zip"
        if not path.exists():
            raise SystemExit(f"Missing {path}")
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            missing = required - names
            if missing:
                raise SystemExit(f"{path}: missing {sorted(missing)}")

    suite_zip = dist / "blender_addon_suite.zip"
    if not suite_zip.exists():
        raise SystemExit(f"Missing {suite_zip}")
    with zipfile.ZipFile(suite_zip) as archive:
        names = set(archive.namelist())
        required_suite = {
            "blender_addon_suite/__init__.py",
            "blender_addon_suite/addons/uv_island_mask/__init__.py",
            "blender_addon_suite/addons/uv_island_mask/runtime.py",
            "blender_addon_suite/addons/in_between_shape_key/__init__.py",
            "blender_addon_suite/addons/in_between_shape_key/runtime.py",
        }
        missing = required_suite - names
        if missing:
            raise SystemExit(f"{suite_zip}: missing {sorted(missing)}")

    catalog = json.loads(Path("release/packages.json").read_text(encoding="utf-8"))
    if [item["id"] for item in catalog["packages"]] != ["uv_island_mask", "in_between_shape_key"]:
        raise SystemExit("Unexpected stable package catalog")
    print("ZIP layout check passed")


if __name__ == "__main__":
    main()
