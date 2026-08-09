# Additional Conventions Beyond the Built-in Functions

As this project's AI coding tool, you must follow the additional conventions below, in addition to the built-in functions.

# Project

Blender アドオン集約リポジトリ。未リリース扱いのため互換性は気にしない。

# Docs

Document: ./docs/index.md
* 文章は簡潔に記述する
* 図(mermaid, svg)を多用する
* 考えればわかることを記述しない

# Rules

- `C:\Users\wyndf\Documents\blender-addon` は参照用。変更しない
- ツール版の正は `addons/<tool>/__init__.py` の `bl_info["version"]`
- パッケージ: `scripts/make_zip.py`（`uv run make-zip`）
- リリース検証: `scripts/prepare_release.py`（`uv run prepare-release`）
- Blender ランタイムテストは background モード。埋め込み Blender MCP では実行しない
- テスト手順: [`docs/testing.md`](docs/testing.md)。全自動は Docker（`scripts/run_ci.py`）
- 新規・更新ツールは [`docs/reload-safe-runtime.md`](docs/reload-safe-runtime.md) に従う（`runtime.py` + durable な `driver_namespace` uninstall）。`unregister()` をモジュールグローバルに依存させない
- 新規・更新するアドオンは日本語UI翻訳を必須とし、`blender-addon-i18n` スキルに従って全ユーザー向け文字列とreload-safeな翻訳ライフサイクルを実装する

# Workflow

```
let code;
do {
  code = coding()
} while(test(code));
generateZip();
```

* 仕様にないフォールバックは禁止。エラーで即時中断を優先
* 常にロバストなアルゴリズムを使う
* コメントは必要十分に（Linux カーネル流）
* 気づいたことはユーザーに報告する

# Directory

- tmp: 一時ファイル置き場

# testing

- テストケース毎に「背景情報」「なぜやるか」を記載する
- 互換層は維持しない。移行期間を設けず、移行までやり切る
