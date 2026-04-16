"""
既に 原文/ にある巻ファイルについて、表マークアップを検出したらファイルを削除し、
URLリスト.txt から当該行を除く。

検出方法（wikisource_fetch.wikitext_has_table_markup と同じ基準）:
  - 保存済み .txt の本文に `{|` または `<table` または `{{table` が含まれる
  - （既定）さらに Wikisource raw を再取得し、同様に表があれば削除

一括取得（bulk_preflight_fetch）直後は、再取得を省略するなら --local-only を付ける。

  python purge_volumes_with_tables.py --base-dir "E:\\マイドライブ\\史書\\金史"
  python purge_volumes_with_tables.py --base-dir "E:\\マイドライブ\\史書\\金史" --local-only
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

from run_range import URL_LIST_NAME, parse_vol_from_line
from wikisource_fetch import (
    build_url,
    fetch_wikitext,
    normalize_wiki_url,
    resolve_fetch_vol,
    wikitext_has_table_markup,
)


def split_url_list_lines(text: str) -> tuple[list[str], list[str]]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="原文＋URLリストから表あり巻を除去")
    parser.add_argument(
        "--base-dir",
        default=r"E:\マイドライブ\史書\金史",
        help="プロジェクトルート",
    )
    parser.add_argument("--sleep-sec", type=float, default=0.45)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="保存済み原文の内容のみ検査（Wikisource へ再取得しない）",
    )
    args = parser.parse_args()
    base = os.path.normpath(args.base_dir)
    raw_dir = os.path.join(base, "原文")
    list_path = os.path.join(base, URL_LIST_NAME)
    if not os.path.isdir(raw_dir):
        print(f"error: {raw_dir} not found", file=sys.stderr)
        return 1
    if not os.path.isfile(list_path):
        print(f"error: {list_path} not found", file=sys.stderr)
        return 1

    pat = re.compile(r"^巻(\d+[上中下]?)\.txt$")
    excluded_wiki_vols: set[str] = set()

    for name in sorted(os.listdir(raw_dir)):
        m = pat.match(name)
        if not m:
            continue
        suf_token = m.group(1)
        path = os.path.join(raw_dir, name)
        try:
            wiki_juan, _, _ = resolve_fetch_vol(suf_token)
        except ValueError:
            continue

        try:
            with open(path, encoding="utf-8", errors="replace") as rf:
                saved = rf.read()
        except OSError as e:
            print(f"read fail {name}: {e}", file=sys.stderr)
            continue

        if wikitext_has_table_markup(saved):
            print(f"table in file: {name} ({wiki_juan})")
            excluded_wiki_vols.add(wiki_juan)
            if not args.dry_run:
                os.remove(path)
            time.sleep(args.sleep_sec)
            continue

        if args.local_only:
            time.sleep(args.sleep_sec)
            continue

        raw_url = normalize_wiki_url(build_url(suf_token))
        try:
            wikitext = fetch_wikitext(raw_url)
        except RuntimeError as e:
            print(f"fetch fail {name}: {e}", file=sys.stderr)
            time.sleep(args.sleep_sec)
            continue

        if not wikitext_has_table_markup(wikitext):
            time.sleep(args.sleep_sec)
            continue

        print(f"table on remote: {name} ({wiki_juan})")
        excluded_wiki_vols.add(wiki_juan)
        if not args.dry_run:
            os.remove(path)
        time.sleep(args.sleep_sec)

    with open(list_path, encoding="utf-8-sig", newline="") as f:
        raw_text = f.read()
    header_lines, data_lines = split_url_list_lines(raw_text)
    kept = [
        ln
        for ln in data_lines
        if parse_vol_from_line(ln) not in excluded_wiki_vols
    ]

    log_path = os.path.join(base, "表検出_除外巻_purge.txt")
    with open(log_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# purge_volumes_with_tables で削除した巻（wiki サブページ名）\n")
        for v in sorted(excluded_wiki_vols):
            f.write(v + "\n")

    if excluded_wiki_vols and not args.dry_run:
        with open(list_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(header_lines + kept) + "\n")
        print(f"updated {list_path} ({len(data_lines)} -> {len(kept)} url lines)")
    elif args.dry_run:
        print(f"dry-run: would remove {len(excluded_wiki_vols)} files / url lines")
    else:
        print("no table volumes found; URLリストは未変更")
    print(f"wrote {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
