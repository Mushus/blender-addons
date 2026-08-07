---
name: Agents Rules
description: General rules for the project
root: true
---
# Project

このプロジェクトはまだリリースされていないものとみなし、互換性を気にするべきではない

# Docs

Document: ./docs/index.md
* 文章は簡潔に記述する
* 図(mermaid, svg)を多用する
* 考えればわかることを記述しない

# Workflow
1. Modify Code
2. Pre-compile & Static Analysis
   - コンパイルエラー/警告が発生した場合: コードを修正して手順2へ戻る

* 仕様にないフォールバックは禁止されています。エラーによって即時中断するのが好ましい
* 常にロバストなアルゴリズムを使用する
* Linuxカーネルのコードのようにコメントを必要十分記述する
* 気づいたことがあれば、ユーザーに報告すること

# Directory

- tmp: 一時ファイル置き場

# testing

- テストケース毎に「背景情報」「なぜやるか」を記載してください。
- 互換層を維持することは技術負債を増やすことになるため、互換層を維持しない。移行期間を設けない。移行まで責任を持ってやり切る。
