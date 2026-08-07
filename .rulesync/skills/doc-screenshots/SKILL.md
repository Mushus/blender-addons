---
name: doc-screenshots
description: >-
  Docker + Xvfb でアドオン UI のドキュメント用スクリーンショットを撮影する。
  docs 用 PNG の撮影・追加・再生成時に使用する。
metadata:
  version: 1.0.0
---
# ドキュメント用スクリーンショット

Docker 上で撮影する。ホストの実ウィンドウには依存しない。詳細は `docs/doc-screenshots.md`。

## 実行

```bash
uv run run-docker --build --exec -- python ./scripts/make_zip.py
uv run run-docker --exec -- python ./scripts/run_doc_screenshots.py
```

個別: `--only <package_id>` / 一覧: `--list`

出力: `artifacts/doc-screenshots/<package_id>/*.png`

## 新規エントリ

1. `scripts/<id>_doc_screenshot.py` を追加
2. `doc_screenshot_lib.run_doc_shot` で ZIP 有効化 → UI 状態準備 → `capture_region`
3. PNG パスのリストを返し、失敗は例外で即時中断
4. `--only <id>` で Docker 上の通否を確認

参照: 既存の `scripts/*_doc_screenshot.py`
