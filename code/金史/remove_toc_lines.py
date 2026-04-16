# -*- coding: utf-8 -*-
"""__TOC__ だけの行（またはその文字列）を .txt から削除する。

使い方:
  python remove_toc_lines.py
  python remove_toc_lines.py --folders 原文
詳細は テキスト整備手順.md を参照。
"""
from __future__ import annotations

import argparse
from pathlib import Path


def _parse_args() -> tuple[Path, tuple[str, ...]]:
    p = argparse.ArgumentParser(description="__TOC__ 行の削除")
    p.add_argument("--folders", default="和訳,原文", help="カンマ区切り（例: 原文）")
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    folders = tuple(x.strip() for x in args.folders.split(",") if x.strip())
    return root, folders


def main() -> None:
    ROOT, FOLDERS = _parse_args()
    changed = 0
    for name in FOLDERS:
        d = ROOT / name
        if not d.is_dir():
            print(f"skip (not found): {d}")
            continue
        for p in sorted(d.glob("*.txt")):
            s = p.read_text(encoding="utf-8")
            if "__TOC__" not in s:
                continue
            new = s.replace("__TOC__\n", "").replace("__TOC__\r\n", "")
            if new == s:
                new = s.replace("__TOC__", "")
            p.write_text(new, encoding="utf-8", newline="")
            changed += 1
            print(p.relative_to(ROOT))
    print(f"done. updated {changed} files.")


if __name__ == "__main__":
    main()
