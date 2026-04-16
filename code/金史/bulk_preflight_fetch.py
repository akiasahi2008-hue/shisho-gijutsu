"""
URLリスト.txt に列挙された全巻を Wikisource から取得し、原文/ に保存する。

wikitext に表構文 ({| または HTML <table>) がある巻は:
  - 原文ファイルを作成しない
  - URLリスト.txt から当該行を削除する（和訳対象外）

実行例:
  python bulk_preflight_fetch.py --base-dir "E:\\マイドライブ\\史書\\金史"

前提: regen_url_list.py 等で URLリスト.txt が最新であること。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

from run_range import URL_LIST_NAME, parse_vol_from_line
from wikisource_fetch import (
    fetch_wikitext,
    materialize_volume_lines,
    normalize_wiki_url,
    resolve_fetch_vol,
    save_volume_text,
    wikitext_has_table_markup,
)


def split_url_list_lines(text: str) -> tuple[list[str], list[str]]:
    """(先頭コメント等のヘッダ行, データ行) に分割。データ行は http を含む行のみ。"""
    header: list[str] = []
    data: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            header.append(raw)
            continue
        if s.startswith("#"):
            header.append(raw)
            continue
        if re.search(r"https?://", raw):
            data.append(raw)
        else:
            header.append(raw)
    return header, data


def first_url_in_line(line: str) -> str | None:
    m = re.search(r"https?://[^\s]+", line)
    return m.group(0) if m else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="URLリストに従い一括取得。表あり巻は除外し URLリスト を更新"
    )
    parser.add_argument(
        "--base-dir",
        default=r"E:\マイドライブ\史書\金史",
        help="プロジェクトルート",
    )
    parser.add_argument(
        "--url-list",
        default=URL_LIST_NAME,
        help="URLリストファイル名（ルート相対）",
    )
    parser.add_argument(
        "--sleep-sec",
        type=float,
        default=0.45,
        help="リクエスト間隔（秒）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="取得・書き換えを行わず、表検出のみ表示",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="先頭 N 件だけ処理（0 で全件。動作確認用）",
    )
    args = parser.parse_args()
    base = os.path.normpath(args.base_dir)
    list_path = os.path.join(base, args.url_list)
    if not os.path.isfile(list_path):
        print(f"error: not found {list_path}", file=sys.stderr)
        return 1

    with open(list_path, encoding="utf-8-sig", newline="") as f:
        raw_text = f.read()
    header_lines, data_lines = split_url_list_lines(raw_text)
    if args.limit > 0:
        data_lines = data_lines[: args.limit]

    excluded: list[tuple[str, str, str]] = []  # (wiki_vol, reason, original_line)
    kept_lines: list[str] = []
    errors: list[tuple[str, str]] = []

    for line in data_lines:
        url = first_url_in_line(line)
        vol = parse_vol_from_line(line) if url else None
        if not url or not vol:
            errors.append((line[:80], "no url or vol"))
            kept_lines.append(line)
            continue

        raw_url = normalize_wiki_url(url)
        try:
            wikitext = fetch_wikitext(raw_url)
        except RuntimeError as e:
            errors.append((vol, str(e)))
            kept_lines.append(line)
            time.sleep(args.sleep_sec)
            continue

        if wikitext_has_table_markup(wikitext):
            excluded.append((vol, "table_markup", line))
            print(f"skip (table): {vol}")
            if not args.dry_run:
                try:
                    _, suf, _ = resolve_fetch_vol(vol)
                    stale = os.path.join(base, "原文", f"巻{suf}.txt")
                    if os.path.isfile(stale):
                        os.remove(stale)
                        print(f"  removed file: {stale}")
                except ValueError:
                    pass
            time.sleep(args.sleep_sec)
            continue

        lines, err, suf = materialize_volume_lines(
            vol, url, wikitext_override=wikitext, quiet_html_warning=True
        )
        if err or not lines:
            errors.append((vol, err or "empty"))
            kept_lines.append(line)
            time.sleep(args.sleep_sec)
            continue

        if not args.dry_run:
            out = save_volume_text(base, suf, lines)
            print(f"ok {vol} -> {out} ({len(lines)} lines)")
        else:
            print(f"dry-run ok {vol}")

        kept_lines.append(line)
        time.sleep(args.sleep_sec)

    log_path = os.path.join(base, "表検出_除外巻.txt")
    if not args.dry_run and args.limit <= 0:
        new_body = "\n".join(header_lines + kept_lines) + "\n"
        with open(list_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_body)
    elif args.limit > 0:
        print("note: --limit 指定時は URLリスト.txt は書き換えません。", file=sys.stderr)

    with open(log_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 表マークアップ検出により URLリスト・和訳対象から外した巻\n")
        for vol, reason, orig in excluded:
            f.write(f"{vol}\t{reason}\t{orig.strip()}\n")
        f.write("\n# fetch / normalize エラー（URLリストには残した）\n")
        for key, msg in errors:
            f.write(f"{key}\t{msg}\n")

    print(f"\nkept url lines: {len(kept_lines)} / data {len(data_lines)}")
    print(f"excluded (tables): {len(excluded)}")
    print(f"errors (kept in list): {len(errors)}")
    print(f"wrote {log_path}")
    if not args.dry_run and args.limit <= 0:
        print(f"updated {list_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
