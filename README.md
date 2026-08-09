# Blender Add-ons

3D モデリングやセットアップ作業を速くする、Blender 向けアドオン集です。

各アドオンは個別の ZIP としてインストールできます。まとめて入れる Suite パッケージも用意しています。

## ダウンロード

- [ダウンロード一覧（日本語）](https://mushus.github.io/blender-addons/downloads/)
- [Download list (English)](https://mushus.github.io/blender-addons/en/downloads/)
- [GitHub Releases](https://github.com/Mushus/blender-addons/releases/latest)
- Extensions リポジトリ（個別アドオン）: `https://mushus.github.io/blender-addons/index.json`
  （Blender: Edit > Preferences > Get Extensions > Repositories > Add Remote Repository）

## アドオン一覧

| アドオン | できること |
| :--- | :--- |
| [**UV Island Mask**](https://mushus.github.io/blender-addons/addons/uv-island-mask/) | 選択した UV 面からマスク画像を生成します |
| [**In Between Shape Key**](https://mushus.github.io/blender-addons/addons/in-between-shape-key/) | `Name@Weight` 形式のシェイプキーを FBX のインビトウィーンとして書き出します |
| [**Slide Relax**](https://mushus.github.io/blender-addons/addons/slide-relax/) | 編集モードで形状を保ちながら、選択頂点の配置を滑らかにします |
| [**Smooth Weight**](https://mushus.github.io/blender-addons/addons/weight-smooth/) | ウェイトペイントで選択頂点の全ボーンウェイトをスムーズし正規化します |

## インストール

### 拡張リポジトリ（推奨）

1. Blender で **編集 > プリファレンス > Get Extensions** を開きます
2. **Repositories > + > Add Remote Repository** に次の URL を追加します  
   `https://mushus.github.io/blender-addons/index.json`
3. 一覧からアドオンをインストールして有効化します

### ZIP 手動インストール

1. 上記から目的のアドオン ZIP をダウンロードします（**解凍しないでください**）
2. Blender で **編集 > プリファレンス > アドオン** を開きます
3. **インストール...** から ZIP を選びます
4. 一覧でアドオンにチェックを入れて有効化します

更新時は、古い版を **削除** してから新しい ZIP を入れ直してください。

詳しい手順・トラブル対処はドキュメントを参照してください。

- [インストール方法](https://mushus.github.io/blender-addons/guides/installation/)
- [FAQ](https://mushus.github.io/blender-addons/guides/faq/)

## ドキュメント

- [日本語](https://mushus.github.io/blender-addons/)
- [English](https://mushus.github.io/blender-addons/en/)

## 開発者向け

環境構築・検証・ブランチ運用は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。
