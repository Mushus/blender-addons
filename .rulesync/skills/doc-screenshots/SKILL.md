---
name: doc-screenshots
description: Docker + Xvfb でアドオン UI のドキュメント用スクリーンショットを撮影する。 docs 用 PNG の撮影・追加・再生成時に使用する。
---
# ドキュメント用スクリーンショット

Docker + Xvfb 上で撮影する（ホストの実ウィンドウに依存しない）。

## 実行コマンド

```bash
# 一括撮影 (make-zip 事前実行が必要)
uv run run-docker --build --exec -- python ./scripts/make_zip.py
uv run run-docker --exec -- python ./scripts/run_doc_screenshots.py

# 個別撮影 / 一覧表示
uv run run-docker --exec -- python ./scripts/run_doc_screenshots.py --only <package_id>
uv run run-docker --exec -- python ./scripts/run_doc_screenshots.py --list
```

## 出力・サイト配置

- 出力先: `artifacts/doc-screenshots/<package_id>/*.png`
- サイト掲載時: `site/src/assets/addons/<package_id>/` にコピーし各アドオン MDX から参照する。

## SoftGL キャプチャ制約

SoftGL 環境では Blender のスクショ演算子が空バッファになるため、ディスプレイ全域を ImageMagick `import` し `crop` 切り出しする。

- **切り出し指定**:
  - 左側エディタ領域を 160px 含める（位置把握用）。
  - 縦は上端タブを残し、最小高さ 220px と「中身下端 + 32px」の大きい方で切り出す。

## 新規エントリ追加手順

1. `scripts/<id>_doc_screenshot.py` を追加する。
2. `doc_screenshot_lib.run_doc_shot` で ZIP 有効化 → UI 状態準備 → `capture_region` を実装する。
3. 生成した PNG パスのリストを返す（失敗時は例外で即時中断）。
4. `--only <id>` で Docker 上の動作品質を確認する。
