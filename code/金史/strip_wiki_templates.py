# -*- coding: utf-8 -*-
"""MediaWiki 系テンプレのラッパーを除去し、本文に残す文字だけ残す。

対象の例:
  {{YL|…}} {{PUA|…}} {{*|…}}
  {{!|異体字|説明}} → 第1フィールド（表示字形）のみ
  {{--|子}} {{--|昉子}} 等 → 内側全文（譜系ラベル）
  {{udots|…}} {{ProperNoun|…}} {{?|…}}
  {{?}} → 欠字プレースホルダ（〓）

使い方:
  python strip_wiki_templates.py
  python strip_wiki_templates.py --folders 原文
詳細は テキスト整備手順.md を参照。
"""
from __future__ import annotations

import argparse
from pathlib import Path

# (prefix, mode)  mode: "inner"=|}} までをそのまま, "bang"={{!| の第1フィールドのみ
_SPECS: list[tuple[str, str]] = [
    ("{{ProperNoun|", "inner"),
    ("{{udots|", "inner"),
    ("{{--|", "inner"),
    ("{{-|", "inner"),
    ("{{YL|", "inner"),
    ("{{PUA|", "inner"),
    ("{{*|", "inner"),
    ("{{!|", "bang"),
    ("{{?|", "inner"),
]


def _inner_to_text(prefix: str, inner: str, mode: str) -> str:
    if mode == "bang":
        if not inner:
            return ""
        # {{!|𠼪|口移}} → 𠼪
        first = inner.split("|", 1)[0].strip()
        return first
    if prefix == "{{YL|" and "|" in inner:
        first, rest = inner.split("|", 1)
        first, rest = first.strip(), rest.strip()
        if rest:
            return f"{first}（{rest}）"
        return first
    return inner


def _find_earliest(s: str, start: int) -> tuple[int, str, str] | None:
    """次のテンプレ開始位置、prefix、mode。無ければ None。"""
    best: tuple[int, int, str, str] | None = None  # j, -len(prefix), prefix, mode
    for prefix, mode in _SPECS:
        j = s.find(prefix, start)
        if j < 0:
            continue
        key = (j, -len(prefix))
        if best is None or key < (best[0], best[1]):
            best = (j, -len(prefix), prefix, mode)
    if best is None:
        return None
    return best[0], best[2], best[3]


def strip_templates(s: str) -> str:
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        found = _find_earliest(s, i)
        if found is None:
            out.append(s[i:])
            break
        pos, prefix, mode = found
        out.append(s[i:pos])
        start_inner = pos + len(prefix)
        end = s.find("}}", start_inner)
        if end == -1:
            out.append(s[pos:])
            break
        inner = s[start_inner:end]
        out.append(_inner_to_text(prefix, inner, mode))
        i = end + 2
    text = "".join(out)
    # 引数なしの欠字マーク（例: 昭{{?}}昭遜）
    if "{{?}}" in text:
        text = text.replace("{{?}}", "〓")
    return text


def main() -> None:
    p = argparse.ArgumentParser(description="ウィキテンプレラッパー除去（金史拡張）")
    p.add_argument(
        "--folders",
        default="和訳,原文",
        help="カンマ区切りのサブフォルダ名（原文のみなら 原文）",
    )
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    folders = tuple(x.strip() for x in args.folders.split(",") if x.strip())

    changed_files = 0
    for name in folders:
        d = root / name
        if not d.is_dir():
            print(f"skip (not found): {d}")
            continue
        for path in sorted(d.glob("*.txt")):
            raw = path.read_text(encoding="utf-8")
            text = raw
            while True:
                new = strip_templates(text)
                if new == text:
                    break
                text = new
            if text != raw:
                path.write_text(text, encoding="utf-8", newline="")
                changed_files += 1
                print(path.relative_to(root))
    print(f"done. updated {changed_files} files.")


if __name__ == "__main__":
    main()
