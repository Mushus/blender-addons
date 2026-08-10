"""Japanese UI translations for the Heat Weight add-on."""

import bpy

TRANSLATIONS = {
    "ja_JP": {
        ("*", "Heat Weight"): "ヒートウェイト",
        ("*", "Weight Utility"): "ウェイトユーティリティ",
        ("*", "Heat Weight settings"): "ヒートウェイト設定",
        ("*", "Display Heat Weight settings"): "ヒートウェイト設定を表示",
        ("*", "Iterations"): "反復回数",
        ("*", "Number of heat diffusion passes"): "熱拡散パス数",
        ("*", "Diffuse deform weights by heat diffusion for decisive blur"):
            "熱拡散で変形ウェイトを拡散し、決定的にぼかします",
        ("Operator", "Heat Weight"): "ヒートウェイト",
        ("Operator", "Diffuse all deform bone weights on selected vertices by pure neighbor averaging"):
            "選択頂点の全変形ボーンウェイトを純粋な近傍平均で拡散します",
        ("*", "Enabled vertex selection; select vertices and run again"):
            "頂点選択を有効化しました。頂点を選択して再実行してください",
        ("*", "Select at least one visible vertex"): "可視頂点を1つ以上選択してください",
        ("*", "Selected vertices need connected edges"): "選択した頂点は接続された辺が必要です",
        ("*", "Diffused weights on {count} selected vertices"):
            "{count}個の選択頂点のウェイトを拡散しました",
    }
}


def register():
    bpy.app.translations.register(__name__, TRANSLATIONS)


def unregister():
    bpy.app.translations.unregister(__name__)
