# 再読込耐性のあるアドオンランタイム

モジュール再読込後も RNA / ハンドラ / メニュー登録は残る一方、モジュールグローバルは差し替わる。`unregister()` が新しい参照しか知らないと古い登録が残り、再インストールで競合する。

登録ハンドルは再読込後も残る `bpy.app.driver_namespace` に置く。

## 契約

1. `register()` の先頭で durable uninstall する
2. 子モジュールの `reload` は `register()` 内・uninstall 後のみ（import 時禁止）
3. Blender 側の登録はすべて `driver_namespace["<package>.runtime.v1"]` に保存する
4. `unregister()` は durable state だけを見る（モジュールグローバル禁止）
5. uninstall 後に runtime key を `pop` する

`.blend` 内データ（カスタムプロパティ、ノード、ドライバ）は残してよい。消すのは Python / RNA 登録だけ。

## 配置

個別 ZIP は自己完結。共有ライブラリは作らず、各ツールに `runtime.py` を置く。

```
addons/<tool>/
  __init__.py
  runtime.py    # RUNTIME_KEY, begin_state, uninstall
```

参照: `in_between_shape_key/runtime.py`、`uv_island_mask/runtime.py`、suite は `__init__.py` の `blender_addon_suite.runtime.v1`

## 形

```python
def register():
    runtime.uninstall()
    _reload_children()
    state = runtime.begin_state()
    # 登録し、ハンドルを state に追記

def unregister():
    runtime.uninstall()
```

`uninstall()` は欠落・二重呼びでも落ちないこと。

## 保存するもの

- `register_class` → クラス一覧
- `app.handlers` → `(list, fn)`
- `menu.append` → `(menu, draw_fn)`
- msgbus → `owner`
- RNA プロパティ → 名前文字列
- 動的クラス / メニュー差し替え → クラスと custom・original 両方
- host / i18n → unregister コールバック

## 禁止

- import 時の子モジュール reload
- モジュールグローバルの identity で handler / class を外す
- reload で `_export_class = None` になり unregister をスキップする
- durable uninstall なしの `register()`

## テスト

`scripts/blender_smoke_test.py`: 有効のまま reload → disable/enable、`register()` 二重呼び出し、runtime key / handler / RNA の残骸なしを断言。

新ツール追加時は runtime-key マップと断言を足す。層全体は [testing.md](testing.md)。
