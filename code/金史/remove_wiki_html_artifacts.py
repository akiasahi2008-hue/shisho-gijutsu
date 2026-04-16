# -*- coding: utf-8 -*-
"""__FORCETOC__、<onlyinclude>、<poem>、{{ul|…}} 等のウィキ／HTML残骸を除去する。

和訳・原文の各 .txt を対象（`--folders` で指定）。チャンクフォルダは対象外。
詳細は テキスト整備手順.md を参照。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def _parse_args() -> tuple[Path, tuple[str, ...]]:
    p = argparse.ArgumentParser(description="ウィキ/HTML 残骸の除去")
    p.add_argument("--folders", default="和訳,原文", help="カンマ区切り（例: 原文）")
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    folders = tuple(x.strip() for x in args.folders.split(",") if x.strip())
    return root, folders

_LINE_REMOVE_RES = (
    re.compile(r"^\s*__FORCETOC__\s*$"),
    re.compile(r"^\s*__TOC__\s*$"),
    re.compile(r"^\s*<onlyinclude>\s*$", re.IGNORECASE),
    re.compile(r"^\s*</onlyinclude>.*$", re.IGNORECASE),
)

_SUBSTRIP = (
    "<poem>",
    "</poem>",
    "<Poem>",
    "</Poem>",
    "<blockquote>",
    "</blockquote>",
    "<BLOCKQUOTE>",
    "</BLOCKQUOTE>",
    "{{footer}}",
    "{{五代作品}}",
)

_TEMPLATE_PREFIXES = ("{{ul|", "{{SKchar|")

_EXTRA_BRACE = re.compile(
    r"\{\{(?:footer|header|五代作品|姊妹计划|姊妹計劃|Textquality|header2)\}\}",
    re.IGNORECASE,
)

_STYLE_LINE_HEAD = re.compile(r"^style=[^|]*\|", re.IGNORECASE)


def strip_ul_skchar_templates(s: str) -> str:
    while True:
        best = -1
        which = ""
        for p in _TEMPLATE_PREFIXES:
            j = s.find(p)
            if j != -1 and (best == -1 or j < best):
                best = j
                which = p
        if best == -1:
            break
        start_inner = best + len(which)
        end = s.find("}}", start_inner)
        if end == -1:
            break
        inner = s[start_inner:end]
        repl = "〓" if which == "{{SKchar|" else inner
        s = s[:best] + repl + s[end + 2 :]
    return s


def clean_text(raw: str) -> str:
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out_lines: list[str] = []
    for line in lines:
        if any(rx.match(line) for rx in _LINE_REMOVE_RES):
            continue
        line = line.replace("__FORCETOC__", "").replace("__TOC__", "")
        line = _STYLE_LINE_HEAD.sub("", line)
        out_lines.append(line)
    s = "\n".join(out_lines)
    for sub in _SUBSTRIP:
        s = s.replace(sub, "")
    while True:
        t = strip_ul_skchar_templates(s)
        if t == s:
            break
        s = t
    while True:
        t = _EXTRA_BRACE.sub("", s)
        if t == s:
            break
        s = t
    for br in ("<br/>", "<BR/>", "<br />", "<BR />", "<br>", "<BR>"):
        s = s.replace(br, "")
    s = s.replace("'''", "")
    s = re.sub(r"\n{4,}", "\n\n\n", s)
    return s


def main() -> None:
    ROOT, FOLDERS = _parse_args()
    changed = 0
    for name in FOLDERS:
        d = ROOT / name
        if not d.is_dir():
            print(f"skip (not found): {d}")
            continue
        for p in sorted(d.glob("*.txt")):
            raw = p.read_text(encoding="utf-8")
            new = clean_text(raw)
            if new != raw:
                p.write_text(new, encoding="utf-8", newline="\n")
                changed += 1
                print(p.relative_to(ROOT))
    print(f"done. updated {changed} files.")


if __name__ == "__main__":
    main()
