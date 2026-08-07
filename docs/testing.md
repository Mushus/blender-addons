# テスト実装パターン

Blender アドオンは Playwright 相当の安定 UI セレクタを持たない。そのため検証は層に分け、GUI は仮想ディスプレイ上の最小 smoke にとどめる。

自動テストはすべて `Dockerfile` の Linux イメージ内で実行する。埋め込み Blender MCP セッションでは走らせない。

## 層

| 層 | 何を見るか | 実行 |
|----|------------|------|
| 静的 | lint / 型 / ZIP レイアウト | Docker |
| ライフサイクル smoke | enable/disable、reload、残骸なし | Docker `--background` |
| 機能 smoke | `bpy.ops` / RNA / 出力物 | Docker `--background` |
| UI draw（擬似） | パネルが何を描くか | background 内のフェイクレイアウト |
| GUI smoke | 仮想ウィンドウでの操作・スクショ | Docker + Xvfb + `--enable-event-simulate` |
| Docs スクショ | ドキュメント用 PNG | Docker + Xvfb（CI 外。[`doc-screenshots.md`](doc-screenshots.md)） |

## 実行

CI / ローカルとも `scripts/run_ci.py` が静的 → ZIP → background → GUI を順に回す。

```bash
uv run run-docker --build --exec -- python ./scripts/run_ci.py
```

ドキュメント用スクショ（CI には含めない）:

```bash
uv run run-docker --exec -- python ./scripts/make_zip.py
uv run run-docker --exec -- python ./scripts/run_doc_screenshots.py
```

発見:

| ランナー | 対象 |
|----------|------|
| `run_background_smokes.py` | `release/packages.json` の stable + suite ライフサイクル、`scripts/<id>_smoke_test.py` |
| `run_gui_smokes.py` | `scripts/<id>_ui_smoke_test.py`（`xvfb-run` + SoftGL） |
| `run_doc_screenshots.py` | `scripts/<id>_doc_screenshot.py`（`xvfb-run` + SoftGL） |

契約: stable パッケージには必ず `scripts/<id>_smoke_test.py` がある。逆に、その命名の smoke は packages.json に無いと失敗する。

新ツール追加時:

1. `release/packages.json` に足す
2. `scripts/<id>_smoke_test.py` を足す（`--zip`）
3. 必要なら `scripts/<id>_ui_smoke_test.py` を足す
4. `blender_smoke_test.py` の runtime-key マップとクリーンアップ断言を足す

再読込耐性の契約は [reload-safe-runtime.md](reload-safe-runtime.md)。

## 機能 smoke の書き方

- 1 シナリオ = 1 関数。関数名で仕様を表す
- Arrange / Act / Assert を分ける
- メッシュ作成・アドオン有効化はヘルパーへ
- シナリオ同士で状態を引き継がない
- `main()` は有効化 → シナリオ列挙 → `finally` で無効化

## UI draw（擬似レイアウト）

本物のウィンドウなしで「何を描いたか」を見る。`UILayout` の代わりにイベントを記録するスタブを渡し、`label` / `operator` / `prop` の有無を断言する。

参照: `scripts/in_between_shape_key_smoke_test.py` の `_RecordingLayout`。

## GUI smoke

`xvfb-run` 上で Blender ウィンドウを開き、`--enable-event-simulate` でオペレータ検索・クリックを送り、X11 キャプチャ（ImageMagick `import`）で Properties 領域を比較する。失敗時の PNG は `artifacts/` に残る。

参照: `scripts/in_between_shape_key_ui_smoke_test.py`。

制約: 名前セレクタはない。操作はオペレータ検索・座標クリック・固定ウィンドウサイズ（1920x1080）前提。

## やらないこと

- ホスト Windows の実ウィンドウや Win32 クリックに依存すること
- MCP セッション上で Blender ランタイムテストを回すこと
- シナリオを 1 本の `main()` に全部直書きし続けること（新規・大幅更新時は関数分割）
