from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
import zipfile
from pathlib import Path

import bpy


def args():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--module", required=True)
    return parser.parse_args(raw)


def main():
    options = args()
    zip_path = Path(options.zip).resolve()
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="blender-addon-smoke-"))
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(temp_dir)
    sys.path.insert(0, str(temp_dir))
    module = importlib.import_module(options.module)
    for _ in range(2):
        module.register()
        if not getattr(module, "bl_info", None):
            raise AssertionError(f"{options.module} did not load")
        module.unregister()
        if "blender_addon_tools.embedded_host.v1" in getattr(bpy.app, "driver_namespace", {}):
            raise AssertionError("Embedded host state was not cleaned up")
        module = importlib.reload(module)
    print(f"Smoke test passed: {options.module}")


if __name__ == "__main__":
    main()
