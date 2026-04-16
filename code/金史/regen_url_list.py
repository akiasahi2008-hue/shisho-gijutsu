"""
zh.wikisource 金史 索引ページから 金史/卷* へのリンクを収集し URLリスト.txt を生成する。

再生成: python regen_url_list.py
"""
from __future__ import annotations

import html as html_module
import os
import re
import urllib.parse
import urllib.request

BOOK = "\u91d1\u53f2"  # 金史
INDEX_URL = "https://zh.wikisource.org/wiki/" + urllib.parse.quote(BOOK, safe="")
USER_AGENT = "Mozilla/5.0 (compatible; JinShiURLList/1.0)"

# 卷1 / 卷43上 / 卷135 など（索引に載る形式。桁埋めの有無は索引に従う）
_VOL_PAGE = re.compile(r"^\u5377\d+[\u4e0a\u4e2d\u4e0b]?$")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def extract_volume_links(page_html: str) -> list[tuple[str, str]]:
    """
    戻り値: (正規化 wiki URL, ラベル) 例:
    ("https://zh.wikisource.org/wiki/金史/卷1", "卷1")
    """
    pat = re.compile(r'href="(/wiki/[^"#]+)"[^>]*>', re.IGNORECASE)
    seen: dict[str, str] = {}
    for m in pat.finditer(page_html):
        path = html_module.unescape(m.group(1))
        if not path.startswith("/wiki/"):
            continue
        title = urllib.parse.unquote(path[len("/wiki/") :])
        title = title.replace("_", " ")
        if not title.startswith(BOOK + "/"):
            continue
        rest = title[len(BOOK) + 1 :]
        if not _VOL_PAGE.match(rest):
            continue
        norm_url = "https://zh.wikisource.org/wiki/" + urllib.parse.quote(title, safe="/")
        seen[norm_url] = rest

    return [(u, seen[u]) for u in seen]


def sort_key_label(label: str) -> tuple:
    """卷043上 → 数値順（上 < 中 < 下 < 無接尾辞は同巻内で先に来るよう 0）"""
    m = re.match(r"^\u53770*(\d+)([\u4e0a\u4e2d\u4e0b]?)$", label)
    if not m:
        return (1, 9999, 9, label)
    n = int(m.group(1))
    suf = m.group(2) or ""
    order = {"": 0, "\u4e0a": 1, "\u4e2d": 2, "\u4e0b": 3}
    return (0, n, order.get(suf, 9), label)


def main() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(root, "URLリスト.txt")

    print("GET", INDEX_URL)
    page = fetch(INDEX_URL)
    pairs = extract_volume_links(page)
    if not pairs:
        raise SystemExit("no volume links found — HTML structure changed?")

    by_url = {u: lab for u, lab in pairs}
    urls_sorted = sorted(by_url.keys(), key=lambda u: sort_key_label(by_url[u]))

    lines = [
        "# 金史 Wikisource URL 一覧（索引ページから自動生成）",
        "# 再生成: python regen_url_list.py",
        "# 形式: <URL> <半角スペース> <卷ラベル>  ※右は Wikisource サブページ名（原文・和訳の巻番号部分と対応）",
    ]
    for u in urls_sorted:
        lines.append(f"{u} {by_url[u]}")

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    print(f"wrote {out_path} ({len(urls_sorted)} URLs)")


if __name__ == "__main__":
    main()
