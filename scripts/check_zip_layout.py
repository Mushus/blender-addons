from __future__ import annotations

import json
import zipfile
from pathlib import Path


def main() -> None:
    dist = Path("dist")
    package_zip = dist / "uv_island_mask.zip"
    suite_zip = dist / "blender_addon_suite.zip"
    for path in (package_zip, suite_zip):
        if not path.exists():
            raise SystemExit(f"Missing {path}")
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if path == package_zip:
                required = {
                    "uv_island_mask/__init__.py",
                    "uv_island_mask/embedded_host/registry.py",
                    "uv_island_mask/tool_manifest.json",
                }
            else:
                required = {
                    "blender_addon_suite/__init__.py",
                    "blender_addon_suite/addons/uv_island_mask/__init__.py",
                }
            missing = required - names
            if missing:
                raise SystemExit(f"{path}: missing {sorted(missing)}")

    catalog = json.loads(Path("release/packages.json").read_text(encoding="utf-8"))
    if [item["id"] for item in catalog["packages"]] != ["uv_island_mask"]:
        raise SystemExit("Unexpected stable package catalog")
    print("ZIP layout check passed")


if __name__ == "__main__":
    main()

