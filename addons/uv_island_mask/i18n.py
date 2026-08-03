"""Blender UI translations for the UV Island Mask add-on."""

import bpy

TRANSLATIONS = {
    "ja_JP": {
        ("*", "UV Island Mask"): "UVアイランドマスク",
        ("*", "UV Utility"): "UVユーティリティ",
        ("*", "UV Island Mask settings"): "UVアイランドマスク設定",
        ("*", "Display UV Island Mask settings"): "UVアイランドマスク設定を表示",
        ("*", "Resolution"): "解像度",
        ("*", "Choose a square mask resolution"): "正方形マスクの解像度を選択",
        ("*", "Custom"): "カスタム",
        ("*", "Specify width and height independently"): "幅と高さを個別に指定",
        ("*", "Width"): "幅",
        ("*", "Custom mask width in pixels"): "マスク幅（ピクセル）",
        ("*", "Height"): "高さ",
        ("*", "Custom mask height in pixels"): "マスク高さ（ピクセル）",
        ("*", "Margin"): "マージン",
        ("*", "Bake margin in pixels"): "ベイク時のマージン（ピクセル）",
        ("*", "Auto Margin"): "自動マージン",
        ("*", "Update margin automatically when the resolution changes"):
            "解像度の変更時にマージンを自動更新",
        ("*", "Bake UV Island Mask"): "UVアイランドマスクをベイク",
        ("*", "Bake a mask image from selected UV faces."): "選択したUV面からマスク画像をベイクします。",
        ("Operator", "Bake UV Island Mask"): "UVアイランドマスクをベイク",
        ("Operator", "Bake a mask image for selected UV faces with seam margin"):
            "選択したUV面からシームマージン付きのマスク画像をベイク",
        ("*", "Failed to bake UV island mask"): "UVアイランドマスクのベイクに失敗しました",
        ("*", "Mask image was created, but no Image Editor area is available"):
            "マスク画像を作成しましたが、利用可能なイメージエディター領域がありません",
        ("*", "Baked UV island mask"): "UVアイランドマスクをベイクしました",
        ("*", "Select at least one UV face"): "UV面を1つ以上選択してください",
    }
}


def register():
    bpy.app.translations.register(__name__, TRANSLATIONS)


def unregister():
    bpy.app.translations.unregister(__name__)
