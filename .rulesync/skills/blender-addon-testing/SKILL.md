---
name: blender-addon-testing
description: Blenderアドオンのテスト手法（背景smoke/GUI smoke）の構築・実行手順。テスト新規追加や修正時に参照・適用する。
---
# Blender Add-on Testing

Blenderアドオンのテスト手法と実行手順。全テストはDocker（Linux環境）上で実行する。

> [!IMPORTANT]
> 埋め込みBlender MCP上でのテスト実行は禁止。テストは背景（`--background`）またはDocker内で実行すること。

## テスト層

| 層 | 内容 | 実行環境 |
|---|---|---|
| 静的 | lint / 型チェック / ZIPレイアウト | Docker |
| background smoke | enable/disable/reload/残骸確認, `bpy.ops`, RNA, UI擬似レイアウト | Docker (`--background`) |
| GUI smoke | ウィンドウ操作, イベント送信, スクショ比較 | Docker (`Xvfb` + `SoftGL`) |

## 実行コマンド

```bash
# 全テスト実行 (CI同等)
uv run run-docker --build --exec -- python ./scripts/run_ci.py

# 個別実行
uv run run-docker --exec -- python ./scripts/run_background_smokes.py
uv run run-docker --exec -- python ./scripts/run_gui_smokes.py
```

## 新規ツール追加時の契約

1. `release/packages.json` に追加する。
2. `scripts/<id>_smoke_test.py` を追加する（`release/packages.json` の stable パッケージと 1:1 対応必須）。
3. 必要に応じて `scripts/<id>_ui_smoke_test.py` を追加する。
4. `scripts/blender_smoke_test.py` の runtime-key マップとクリーンアップ検証を追加する。

## 開発・記述ルール

- **AAAパターン**: テストシナリオは Arrange / Act / Assert を明示して記述する。
- **即時中断**: 仕様にないフォールバックは禁止。エラー時は即時中断する。
- **独立性**: シナリオ間で状態を共有しない。有効化・シナリオ実行・無効化のクリーンアップは `finally` で保証する。
