---
name: blender-addon-coding-rules
description: Blenderアドオンのコーディング規約（再読込耐性、durable runtime管理、後始末など）。アドオンの実装・更新時に参照・適用する。
---
# Blender Add-on コーディング規約

Blenderアドオン実装におけるコーディング規約。主にアドオンの有効化・無効化・再読込（reload）時にRNA / ハンドラ / メニュー等の登録残骸を残さないためのルールを定義する。

## 基本構造

登録ハンドルはモジュールグローバルではなく `bpy.app.driver_namespace["<package>.runtime.v1"]` にて耐久（durable）管理する。

### ディレクトリ構成
```
addons/<tool>/
  __init__.py
  runtime.py    # RUNTIME_KEY, begin_state, uninstall
```

### ライフサイクルテンプレート
```python
def register():
    runtime.uninstall()       # 1. 冒頭で durable uninstall を実行
    _reload_children()        # 2. uninstall 後に子モジュールを reload
    state = runtime.begin_state()
    # 3. 登録を行い、ハンドルを state に記録

def unregister():
    runtime.uninstall()       # durable state のみを参照して削除
```

## 実装規約

1. **durable 管理の徹底**:
   - `register()` の先頭で必ず `runtime.uninstall()` を実行する。
   - `unregister()` はモジュールグローバルを参照せず、`driver_namespace` 内の状態だけを見て削除する。
   - `uninstall()` 処理後に `driver_namespace` から runtime key を `pop` する。
   - `uninstall()` は未登録・二重呼び出し時でも例外を出さずに安全に終了する。

2. **保存対象**:
   - `register_class`（クラス一覧）
   - `app.handlers`（`(list, fn)` ペア）
   - `menu.append`（`(menu, draw_fn)` ペア）
   - msgbus（`owner`）
   - RNAプロパティ（プロパティ名文字列）
   - i18n / host（unregister コールバック）

## 禁止事項

- import 時（モジュール読み込み時）の子モジュール reload 実行。
- モジュールグローバルの参照に依存したハンドラやクラスの解除。
- `register()` 冒頭での durable uninstall の省略。
