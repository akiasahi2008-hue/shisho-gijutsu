# 金史 — AI 和訳パイプライン

本ディレクトリは、正史和訳プロジェクトで **金史** を処理する際に用いた Python スクリプト・プロンプト・手順書の公開用コピーです。開発中の最新版はローカル作業フォルダ側にある場合があります。

## 必要なもの

- **Python** 3.10 以降を推奨（標準ライブラリ中心。DeepSeek 呼び出しは `urllib`）。
- **DeepSeek API キー** … 環境変数 `DEEPSEEK_API_KEY` に設定してください（リポジトリやスクリプトに直書きしないこと）。

## パスについて

`workflow.py` などの `--base-dir` の既定値は、元の開発環境向けの Windows パスです。**自分のマシン上のプロジェクトルート**に必ず差し替えてください。

```text
python workflow.py 1 --base-dir D:\作業\金史
```

## 主なエントリポイント

| ファイル | 説明 |
|----------|------|
| `run_translate.bat` | **Windows 向け**。対話形式で単巻（`workflow.py`）または範囲（`run_range.py`）を実行。バッチと同じフォルダを `--base-dir` に指定。Wikisource 取得は含まない（先に `原文/` を用意するか別途 fetch）。 |
| `workflow.py` | fetch → split → 翻訳 → merge の一連処理 |
| `splitter.py` | 原文のチャンク分割 |
| `deepseek_translate.py` | DeepSeek API 呼び出し・進捗 `progress.json` |
| `wikisource_fetch.py` | Wikisource からの原文取得（`--reject-if-table` で表マークアップ巻を保存拒否可） |
| `bulk_preflight_fetch.py` | URL リストに従い一括取得。表マークアップ検出巻は除外し `URLリスト.txt` を更新 |
| `purge_volumes_with_tables.py` | 既存 `原文/` 内の表マークアップ巻を削除・リストから除外 |
| `strip_wiki_templates.py` など | ウィキマークアップの除去（詳細は `テキスト整備手順.md`） |
| `翻訳プロンプト2.txt` | 翻訳指示プロンプト |
| `和訳/convert_kyutango_to_premium_html.py` | 和訳テキストから HTML への変換（`史書HTML変換指示書.md` 参照） |

## 「表」の除外について

正史の **「表」という部類の巻**をタイトルだけで弾いているのではありません。**Wikitext に表構文が含まれるか**（`{|`、HTML `<table`、`{{table` など）を `wikisource_fetch.wikitext_has_table_markup` で判定し、該当巻は取得対象外にする設計です。詳しくは同一リポジトリ直下の `index.html`（技術解説ページ）の「表マークアップ」節を参照してください。

## データフォルダ

このリポジトリには **原文・和訳の大量テキストや HTML は含めていません**。実行時には、ローカルで `原文/`・`和訳/` などのディレクトリを用意し、`--base-dir` で指してください。
