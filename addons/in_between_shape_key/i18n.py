"""Japanese UI translations for the In-Between Shape Key add-on."""

import bpy

TRANSLATIONS = {
    "ja_JP": {
        ("*", "In Between Shape Key"): "インビトウィーン・シェイプキー",
        ("*", "In-Between Shape Key"): "インビトウィーン・シェイプキー",
        ("*", "Export Name@Position Shape Keys as FBX in-between blend shapes."):
            "名前@位置形式のシェイプキーをFBXのインビトウィーンとして出力します。",
        ("*", "Position"): "位置",
        ("*", "Position of this in-between Shape Key"): "このインビトウィーン・シェイプキーの位置",
        ("*", "Value"): "値",
        ("*", "Controller"): "コントローラー",
        ("*", "Shape Key"): "シェイプキー",
        ("*", "Target"): "ターゲット",
        ("*", "Add Existing Shape Key"): "既存シェイプキーを追加",
        ("*", "Add to In-Between"): "インビトウィーンに追加",
        ("*", "Value unavailable"): "値を取得できません",
        ("*", "Missing controller: {controller}"): "コントローラーがありません: {controller}",
        ("*", "Shape Key: {name}"): "シェイプキー: {name}",
        ("*", "Select an In-Between controller first"): "先にインビトウィーンのコントローラーを選択してください",
        ("*", "In-Between controller is unavailable"): "インビトウィーンのコントローラーを取得できません",
        ("*", "No existing Shape Keys available"): "追加できる既存シェイプキーがありません",
        ("*", "Controller: {controller}"): "コントローラー: {controller}",
        ("*", "Value: {value:.3f}"): "値: {value:.3f}",
        ("*", "Value for In-Between controller {channel}"):
            "インビトウィーンコントローラー{channel}の値",
        ("*", "In-Between controller value is unavailable: {channel}"):
            "インビトウィーンコントローラーの値を取得できません: {channel}",
        ("*", "Shape Key target position must be finite"):
            "シェイプキーターゲットの位置は有限値で指定してください",
        ("*", "Shape Key name does not contain a canonical position"):
            "シェイプキー名に正規化された位置が含まれていません",
        ("*", "In-Between position must be between 0.000 and 1.000"):
            "インビトウィーンの位置は0.000から1.000の範囲にしてください",
        ("*", "In-Between target positions must be strictly increasing"):
            "インビトウィーンターゲットの位置は昇順で重複なく指定してください",
        ("*", "In-Between runtime is unavailable"):
            "インビトウィーンのランタイムを利用できません",
        ("*", "Failed to rebuild Shape Key driver: {name}"):
            "シェイプキーのドライバーを再構築できませんでした: {name}",
        ("*", "Cannot resolve renamed In-Between controller {channel}"):
            "名前を変更したインビトウィーンコントローラー{channel}を特定できません",
        ("*", "Shape Key already exists: {name}"):
            "シェイプキーは既に存在します: {name}",
        ("*", "Existing Shape Key to add as an In-Between"): "インビトウィーンとして追加する既存シェイプキー",
        ("*", "Add this existing Shape Key as an In-Between"): "この既存シェイプキーをインビトウィーンとして追加",
        ("*", "FBX (.fbx) - In Between Shape Key"): "FBX (.fbx) - インビトウィーン・シェイプキー",
        ("Operator", "Rescan In-Between Groups"): "インビトウィーングループを再スキャン",
        ("Operator", "Re-evaluate Shape Key groups from current names"): "現在の名前からシェイプキーグループを再評価",
        ("Operator", "Validate In-Between Shape Keys"): "インビトウィーン・シェイプキーを検証",
        ("Operator", "Validate Shape Key names and in-between positions"):
            "シェイプキー名とインビトウィーンの位置を検証",
        ("Operator", "Add to In-Between"): "インビトウィーンに追加",
        ("Operator", "Choose an existing Shape Key to add at the controller's current value"):
            "コントローラーの現在値に追加する既存シェイプキーを選択",
        ("Operator", "Convert to In-Between Shape Key"): "インビトウィーン・シェイプキーに変換",
        ("*", "Convert to In-Between Shape Key"): "インビトウィーン・シェイプキーに変換",
        ("Operator", "Convert this Shape Key into an in-between controller with an initial @1 target"):
            "このシェイプキーを初期@1ターゲット付きのインビトウィーンコントローラーに変換",
        ("Operator", "Remove In-Between Target"): "インビトウィーンターゲットを削除",
        ("Operator", "Remove this in-between Shape Key target"): "このインビトウィーン・シェイプキーのターゲットを削除",
        ("Operator", "Select In-Between Target"): "インビトウィーンターゲットを選択",
        ("Operator", "Select this Shape Key target"): "このシェイプキーターゲットを選択",
        ("Operator", "Export In Between Shape Key"): "インビトウィーン・シェイプキーを出力",
        ("*", "Shape Key in-between groups re-evaluated"): "シェイプキーのインビトウィーングループを再評価しました",
        ("*", "Shape Key in-between validation passed"): "インビトウィーン・シェイプキーの検証に合格しました",
        ("*", "No ordinary existing Shape Keys are available"): "追加できる通常のシェイプキーがありません",
        ("*", "The selected Shape Key is no longer available"): "選択したシェイプキーは利用できません",
        ("*", "Select an In-Between controller"): "インビトウィーンのコントローラーを選択してください",
        ("*", "Select an ordinary existing Shape Key"): "通常の既存シェイプキーを選択してください",
        ("*", "An In-Between controller cannot be used as a target"): "インビトウィーンのコントローラーはターゲットにできません",
        ("*", "Set the controller Value between 0.0 and 1.0 before adding an in-between"):
            "追加前にコントローラーの値を0.0から1.0の範囲に設定してください",
        ("*", "Set the Shape Key Value between 0.0 and 1.0 before conversion"):
            "変換前にシェイプキーの値を0.0から1.0の範囲に設定してください",
        ("*", "In-between already exists: {name}"): "インビトウィーンは既に存在します: {name}",
        ("*", "Added existing Shape Key as {name}"): "既存シェイプキーを{name}として追加しました",
        ("*", "Select a Shape Key controller first"): "先にシェイプキーのコントローラーを選択してください",
        ("*", "The active Shape Key is already an in-between target"): "アクティブなシェイプキーは既にインビトウィーンターゲットです",
        ("*", "Controller name must not be empty"): "コントローラー名を空にはできません",
        ("*", "Cannot convert controller because {name} already exists"):
            "{name}が既に存在するためコントローラーを変換できません",
        ("*", "Converted {channel} to In-Between Shape Key"):
            "{channel}をインビトウィーン・シェイプキーに変換しました",
        ("*", "Select an in-between target"): "インビトウィーンターゲットを選択してください",
        ("*", "Removed {name}"): "{name}を削除しました",
        ("*", "Select an existing Shape Key target"): "既存のシェイプキーターゲットを選択してください",
        ("*", "Invalid shape key name at index {index}: {name}"): "インデックス{index}のシェイプキー名が不正です: {name}",
        ("*", "Position must be between 0 and 1: {name}"): "位置は0から1の範囲にしてください: {name}",
        ("*", "Duplicate in-between position in {channel}"): "{channel}に重複するインビトウィーン位置があります",
        ("*", "Targets in {channel} will be sorted by position on export"):
            "{channel}のターゲットは出力時に位置順へ並べ替えられます",
        ("*", "Batch FBX export is not supported by Shape Key In-Between"):
            "シェイプキー・インビトウィーンはFBXのバッチ出力に対応していません",
        ("*", "Shape Key In-Between export failed: {error}"): "シェイプキー・インビトウィーンの出力に失敗しました: {error}",
        ("*", "Exported FBX with Shape Key In-Betweens: {path}"):
            "インビトウィーン付きFBXを出力しました: {path}",
        ("*", "FBX filepath is empty"): "FBXの出力先が空です",
        ("*", "Shape Keys were not copied for FBX export: {name}"):
            "FBX出力用にシェイプキーを複製できませんでした: {name}",
        ("*", "FBX is missing Objects or Connections"): "FBXにObjectsまたはConnectionsがありません",
        ("*", "Duplicate in-between position in FBX channel {channel}"):
            "FBXチャンネル{channel}に重複するインビトウィーン位置があります",
        ("*", "Animation already exists for In-Between controller path: {path}"):
            "インビトウィーンコントローラーのパスには既にアニメーションがあります: {path}",
    }
}


def register():
    bpy.app.translations.register(__name__, TRANSLATIONS)


def unregister():
    bpy.app.translations.unregister(__name__)
