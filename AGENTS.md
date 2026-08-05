# Repository instructions

- `main` contains release-ready tools only. Use `work` and `feature/<tool>-<topic>` branches for development.
- Do not modify `C:\Users\wyndf\Documents\blender-addon`; it is the source reference for future extractions.
- Treat each `addons/<tool>/__init__.py` `bl_info["version"]` as the tool version source of truth.
- Build packages with `scripts/make_zip.py` (or `uv run make-zip`) and validate release metadata with `scripts/prepare_release.py` (or `uv run prepare-release`).
- Blender runtime tests must run in Blender background mode, not through the embedded Blender MCP session.
- テストの層・実行場所・追加手順は [`docs/testing.md`](docs/testing.md)。全自動テストは Docker（`scripts/run_ci.py`）で実行する。
- 新規・更新ツールは [`docs/reload-safe-runtime.md`](docs/reload-safe-runtime.md) の再読込耐性ランタイムに従う（`runtime.py` + durable な `driver_namespace` uninstall）。`unregister()` をモジュールグローバルに依存させない。

# 作業フロー

1. 実装
2. 品質ゲート(すべて通るまで修正)
3. zip生成