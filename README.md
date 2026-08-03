# Blender Add-on Tools

Small Blender tools released independently and grouped in the UI by purpose.

## Download

Download the current stable versions from the [Blender Add-on Tools download page](https://wyndf.github.io/blender-addons/).

The first extracted tool is `UV Island Mask`. It creates a mask image from selected UV faces and supports multiple edit-mode mesh objects, image name, resolution, and bake margin settings.

## UI model

Each tool is its own installable add-on. Tools declare a `group_id`, such as `uv_utility`; the embedded host combines installed tools with the same group into one Blender panel. One installed tool produces one action row; additional tools add rows to that same group panel.

## Development

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m basedpyright
.\scripts\make_zip.ps1
```

The Windows CI runs Blender smoke tests. Docker is used for static checks and ZIP-layout tests that do not require Blender.

## Release model

- `main` is release-ready.
- `work` is the shared development branch.
- `feature/<tool>-<topic>` branches hold focused changes.
- Tool versions use `YYYY.MM.DD` and are updated in each tool's `bl_info`.
- A successful `main` CI run creates or updates one daily Draft Release.
- Only changed tool ZIPs are attached; the generated manifest and download page point to the latest asset for every tool.
