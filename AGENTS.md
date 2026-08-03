# Repository instructions

- `main` contains release-ready tools only. Use `work` and `feature/<tool>-<topic>` branches for development.
- Do not modify `C:\Users\wyndf\Documents\blender-addon`; it is the source reference for future extractions.
- Treat each `addons/<tool>/__init__.py` `bl_info["version"]` as the tool version source of truth.
- Build packages with `scripts\make_zip.ps1` and validate release metadata with `scripts\prepare_release.ps1`.
- Blender runtime tests must run in Blender background mode, not through the embedded Blender MCP session.

