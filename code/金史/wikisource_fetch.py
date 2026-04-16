"""
Wikisource から金史の指定巻を取得し、原文/巻*.txt に保存する。

- 本文は wiki text（action=raw）。
- 巻頭2行目の表題は zh.wikisource 索引（金史）の wikitext から取得する
  （例: 本紀第一:　世紀、列傳の人名一覧行 … の形式。索引取得に失敗時のみ従来の HTML / wikitext にフォールバック）。
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from shiji_text import normalize_source_lines
from strip_wiki_templates import strip_templates

BOOK_TITLE = "金史"
BOOK_TITLE_ALT = ""
MAX_JUAN = 135

# 索引ページ（各巻の表題行の出所）
INDEX_PAGE_RAW_URL = (
    "https://zh.wikisource.org/w/index.php?title="
    + urllib.parse.quote(BOOK_TITLE, safe="")
    + "&action=raw"
)

# プロセス内キャッシュ（一括取得時の索引再読込を避ける）
_index_volume_heading_lines: dict[int, str] | None = None

SKIP_PATTERNS = [
    "姊妹计划",
    "姊妹計劃",
    "数据项",
    "数据項",
    "维基百科條目",
    "维基百科条目",
    "编辑",
    "編輯",
    "返回頂部",
    "Public domain",
    "公有領域",
    "版本信息",
    "参阅",
    "維基大典",
    "维基大典",
    "检索自",
]


def _clean_index_title_tail(raw: str) -> str:
    """索引行の ]] 以降から、'''・<sub>・テンプレを除き「本紀第一:　太祖上」形式に整える。"""
    s = raw.strip()
    s = re.sub(r"<sub\b[^>]*>.*?</sub>", "", s, flags=re.IGNORECASE | re.DOTALL)
    s = s.replace("'''", "").replace("''", "")
    s = strip_templates(s).strip()
    s = re.sub(r"\s+", " ", s).strip()
    if ":" in s:
        left, right = s.split(":", 1)
        s = f"{left.strip()}:　{right.strip()}"
    return s


def parse_volume_titles_from_index_wikitext(text: str) -> dict[int, str]:
    """索引 wikitext の `*[[金史/卷N|…]]　表題` 行を巻番号→2行目用文字列に変換。"""
    book = re.escape(BOOK_TITLE)
    pat = re.compile(
        rf"^\*\s*\[\[{book}/卷(\d+)(?:\|[^\]]*)?\]\]\s*(.+?)\s*$",
        re.MULTILINE,
    )
    out: dict[int, str] = {}
    for m in pat.finditer(text):
        n = int(m.group(1))
        tail = _clean_index_title_tail(m.group(2))
        if tail:
            out[n] = tail
    return out


def get_index_volume_headings() -> dict[int, str]:
    """索引ページを1回取得して辞書を返す（同一プロセス内はキャッシュ）。"""
    global _index_volume_heading_lines
    if _index_volume_heading_lines is not None:
        return _index_volume_heading_lines
    try:
        text = fetch_wikitext(INDEX_PAGE_RAW_URL)
    except RuntimeError:
        _index_volume_heading_lines = {}
        return _index_volume_heading_lines
    _index_volume_heading_lines = parse_volume_titles_from_index_wikitext(text)
    return _index_volume_heading_lines


def extract_header_prefix(text: str) -> list[str]:
    """
    raw 冒頭の {{header2|…}} または {{header …}} から section= を取り、
    HTML見出し相当の巻頭2行目を復元する。
    例:
      金史
      卷一 本紀第一 …
    """
    lines = text.replace("\r", "").split("\n")

    def polish_section(sec: str) -> str:
        sec = sec.strip()
        sec = sec.replace("'''", "").replace("''", "")
        sec = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", sec)
        sec = re.sub(r"\[\[([^\]]+)\]\]", r"\1", sec)
        return re.sub(r"\s+", " ", sec).strip()

    def section_from_line(s: str) -> str | None:
        """1行に | section = がある場合（同一行で次引数が続く／}} で閉じる）。"""
        m = re.search(r"\|\s*section\s*=\s*(.+?)\s*\|", s)
        if not m:
            m = re.search(r"\|\s*section\s*=\s*(.+?)\s*\}\}", s)
        if not m:
            # 改行区切りの次行が | key = のとき（値に | を含まない想定）
            m = re.search(r"\|\s*section\s*=\s*([^\n|]+)", s)
        return polish_section(m.group(1)) if m else None

    section = ""
    head_limit = min(len(lines), 120)
    in_header_block = False

    for i in range(head_limit):
        s = lines[i].strip()
        # {{header …}}（2 でない）: 列伝後半・外国伝などで使用
        if not in_header_block:
            if "{{header2" in s or "{{header" in s:
                in_header_block = True
                got = section_from_line(s)
                if got:
                    section = got
                    break
                continue
            continue

        # ブロック継続行
        if s == "}}" or s == "}}}":
            break
        m_row = re.match(r"^\|\s*section\s*=\s*(.*)$", s)
        if m_row:
            section = polish_section(m_row.group(1))
            break
        if s.endswith("}}") and not s.startswith("|"):
            break

    out = [BOOK_TITLE]
    if section:
        out.append(section)
    return out


def resolve_fetch_vol(vol_arg: str) -> tuple[str, str, int]:
    raw = vol_arg.strip()
    for head in (f"{BOOK_TITLE}/", f"{BOOK_TITLE_ALT}/"):
        if raw.startswith(head):
            raw = raw[len(head) :].lstrip("/")
    if not raw:
        raise ValueError("巻指定が空です。")

    if raw.startswith("卷"):
        raw = raw[1:]
    m = re.fullmatch(r"0*(\d+)(上|中|下)?", raw)
    if not m:
        raise ValueError(f"巻指定を解釈できません: {vol_arg}")
    n = int(m.group(1))
    part = m.group(2) or ""

    if not (1 <= n <= MAX_JUAN):
        raise ValueError(f"金史の巻番号は 1〜{MAX_JUAN} です: {n}")
    # zh.wikisource の金史は「卷1」形式（桁埋めなし）のサブページ名が多い
    return f"卷{n}{part}", f"{n}{part}", n


def build_wiki_title(vol_arg: str) -> str:
    wiki_juan, _, _ = resolve_fetch_vol(vol_arg)
    return f"{BOOK_TITLE}/{wiki_juan}"


def build_url(vol_arg: str) -> str:
    title = build_wiki_title(vol_arg)
    return (
        "https://zh.wikisource.org/w/index.php?title="
        + urllib.parse.quote(title, safe="/")
        + "&action=raw"
    )


def build_article_url(vol_arg: str) -> str:
    """ブラウザ表示用（見出しテーブルあり）の記事 URL。"""
    title = build_wiki_title(vol_arg)
    return "https://zh.wikisource.org/wiki/" + urllib.parse.quote(title, safe="/")


def wiki_url_to_article_url(url: str) -> str | None:
    """
    raw（action=raw）または /wiki/ の URL から、同じ title の記事ページ URL を得る。
    """
    p = urllib.parse.urlparse(url.strip())
    if "wikisource.org" not in (p.netloc or "").lower():
        return None
    title = ""
    if p.path.startswith("/wiki/"):
        title = urllib.parse.unquote(p.path[len("/wiki/") :])
    else:
        q = urllib.parse.parse_qs(p.query)
        t = q.get("title", [""])[0]
        if t:
            title = urllib.parse.unquote(t)
    if not title:
        return None
    scheme = p.scheme or "https"
    netloc = p.netloc
    return f"{scheme}://{netloc}/wiki/" + urllib.parse.quote(title, safe="/")


def normalize_wiki_url(url: str) -> str:
    url = url.strip()
    p = urllib.parse.urlparse(url)
    if not (p.scheme and "wikisource.org" in p.netloc.lower()):
        return url

    q = urllib.parse.parse_qs(p.query)
    if p.path.startswith("/wiki/"):
        title = urllib.parse.unquote(p.path[len("/wiki/") :])
        return (
            f"{p.scheme}://{p.netloc}/w/index.php?title="
            + urllib.parse.quote(title, safe="/")
            + "&action=raw"
        )

    title = q.get("title", [""])[0]
    if title:
        title = urllib.parse.unquote(title)
        return (
            f"{p.scheme}://{p.netloc}/w/index.php?title="
            + urllib.parse.quote(title, safe="/")
            + "&action=raw"
        )
    return url


def fetch_wikitext(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (compatible; JinShiFetch/1.0)"
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {url}\n{body[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"接続エラー: {url} {e}") from e
    return raw.decode("utf-8", errors="replace")


def extract_heading_lines_from_html(page_html: str) -> list[str] | None:
    """
    ページ HTML 先頭のナビ表（headerContainer）から、
    「書名」「巻見出し」の2行を取り出す。wikitext には無い見出しに相当。
    """
    marker = 'id="headerContainer"'
    i = page_html.find(marker)
    if i < 0:
        return None
    chunk = page_html[i : i + 40000]
    title_alt = "|".join(
        re.escape(t) for t in (BOOK_TITLE, BOOK_TITLE_ALT) if t
    )
    pat = re.compile(
        r'<b><a href="[^"]*" title="(?:'
        + title_alt
        + r')">([^<]+)</a></b>\s*<br\s*/>\s*([^<]+?)\s*<br',
        re.IGNORECASE,
    )
    m = pat.search(chunk)
    if not m:
        return None
    book = html.unescape(m.group(1).strip())
    section = html.unescape(re.sub(r"\s+", " ", m.group(2).strip()))
    if not book or not section:
        return None
    return [book, section]


def _strip_markup(line: str) -> str:
    s = line.strip()
    if not s:
        return ""
    if re.fullmatch(r"</?onlyinclude\s*>", s, re.IGNORECASE):
        return ""
    q = re.fullmatch(r"\{\{(?:quote|Quote|blockquote|Blockquote)\|(.+)\}\}", s)
    if q:
        s = q.group(1).strip()
    else:
        # zh.wikisource 金史などで段落行頭に付く {{gap}}。このままだと直後の
        # 「{{ で始まる行は捨てる」判定で本文ごと消える。
        while re.match(r"^\{\{\s*gap\s*\}\}", s, re.IGNORECASE):
            s = re.sub(
                r"^\{\{\s*gap\s*\}\}\s*",
                "",
                s,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
        # {{YL|…}} 等を本文に展開（行頭だけでなく行内も strip_templates が処理）
        s = strip_templates(s).strip()
    if s.startswith("{{") or s.startswith("}}"):
        return ""
    if s.startswith("[") and s.endswith("]") and len(s) <= 24:
        return ""

    s = re.sub(r"<!--.*?-->", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"</?small>", "", s)
    s = re.sub(r"</?center>", "", s)
    s = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"-\{([^{}]+)\}-", r"\1", s)
    s = s.replace("'''", "").replace("''", "")
    s = s.replace("&nbsp;", " ")
    s = re.sub(r"^=+\s*", "", s)
    s = re.sub(r"\s*=+$", "", s)
    s = re.sub(r"^[*#:;]+\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_lines_from_wikitext(text: str) -> list[str]:
    lines: list[str] = []
    in_template = 0
    in_quote = False
    quote_parts: list[str] = []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue

        if in_quote:
            if line.endswith("}}"):
                quote_parts.append(line[:-2].strip())
                merged = "".join(p for p in quote_parts if p)
                merged = _strip_markup(merged)
                if merged and not any(p in merged for p in SKIP_PATTERNS):
                    lines.append(merged)
                in_quote = False
                quote_parts = []
            else:
                quote_parts.append(line)
            continue

        m_quote_start = re.match(r"^\{\{(?:quote|Quote|blockquote|Blockquote)\|(.+)$", line)
        if m_quote_start:
            tail = m_quote_start.group(1).strip()
            if tail.endswith("}}"):
                merged = tail[:-2].strip()
                merged = _strip_markup(merged)
                if merged and not any(p in merged for p in SKIP_PATTERNS):
                    lines.append(merged)
            else:
                in_quote = True
                quote_parts = [tail]
            continue

        opens = line.count("{{")
        closes = line.count("}}")
        if in_template > 0 or opens > closes:
            in_template += opens - closes
            if in_template < 0:
                in_template = 0
            continue

        line = _strip_markup(line)
        if not line:
            continue
        if any(p in line for p in SKIP_PATTERNS):
            continue
        if re.fullmatch(r"[-=]{3,}", line):
            continue
        lines.append(line)
    return lines


def wikitext_has_table_markup(text: str) -> bool:
    """
    Wikisource の表構文 ({| ... |})、HTML <table>、{{table 系テンプレが含まれるか。
    検出した巻は和訳対象外にし、URLリストから除外する想定。
    """
    if "{|" in text:
        return True
    if re.search(r"<table\b", text, re.IGNORECASE):
        return True
    if re.search(r"\{\{\s*table", text, re.IGNORECASE):
        return True
    return False


def materialize_volume_lines(
    vol_token: str,
    raw_url: str | None = None,
    *,
    wikitext_override: str | None = None,
    quiet_html_warning: bool = False,
) -> tuple[list[str] | None, str, str]:
    """
    raw を取得し、巻頭＋本文行を正規化したリストを返す。

    Returns:
        (lines, error_message, file_suffix)
        成功時 error_message は空。失敗時 lines は None。
    """
    try:
        _, file_suffix, vol_num = resolve_fetch_vol(vol_token)
    except ValueError as e:
        return None, str(e), ""

    url = normalize_wiki_url((raw_url or "").strip() or build_url(vol_token))
    try:
        wikitext = (
            wikitext_override
            if wikitext_override is not None
            else fetch_wikitext(url)
        )
    except RuntimeError as e:
        return None, f"fetch raw: {e}", ""

    prefix: list[str]
    index_heading = get_index_volume_headings().get(vol_num)
    if index_heading:
        prefix = [BOOK_TITLE, index_heading]
        if not quiet_html_warning:
            print(f"巻頭表題: 索引 {INDEX_PAGE_RAW_URL} （巻{vol_num}）")
    else:
        article_url = wiki_url_to_article_url(url) or build_article_url(vol_token)
        try:
            page_html = fetch_wikitext(article_url)
            html_heads = extract_heading_lines_from_html(page_html)
            if html_heads:
                prefix = html_heads
                if not quiet_html_warning:
                    print(f"GET {article_url} (HTML見出し2行)")
            else:
                prefix = extract_header_prefix(wikitext)
                if not quiet_html_warning:
                    print(
                        "警告: 索引に表題なし／HTML からも取得できず。wikitext header2 にフォールバック。",
                        file=sys.stderr,
                    )
        except RuntimeError as e:
            prefix = extract_header_prefix(wikitext)
            if not quiet_html_warning:
                print(
                    f"警告: 索引表題なし・HTML 取得失敗。wikitext header2 にフォールバック: {e}",
                    file=sys.stderr,
                )

    lines = extract_lines_from_wikitext(wikitext)
    filtered = normalize_source_lines(prefix + lines)
    if not filtered:
        return None, "ノイズ除去後に行がありません", file_suffix
    return filtered, "", file_suffix


def save_volume_text(base_dir: str, file_suffix: str, lines: list[str]) -> str:
    """原文/巻<file_suffix>.txt に保存。保存パスを返す。"""
    raw_dir = os.path.join(os.path.normpath(base_dir), "原文")
    os.makedirs(raw_dir, exist_ok=True)
    out_path = os.path.join(raw_dir, f"巻{file_suffix}.txt")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="金史 Wikisource(raw) → 原文/巻*.txt")
    parser.add_argument("vol", help="巻（例: 1, 135, 43上）")
    parser.add_argument(
        "--base-dir", default=r"E:\マイドライブ\史書\金史", help="プロジェクトルート"
    )
    parser.add_argument("--url", default=None, help="完全 URL（指定時は vol の URL 組み立てをスキップ）")
    parser.add_argument(
        "--reject-if-table",
        action="store_true",
        help="wikitext に表 ({| または <table>) がある場合は保存せず終了コード 4",
    )
    args = parser.parse_args()

    base_dir = os.path.normpath(args.base_dir)
    url = (args.url or "").strip() or build_url(args.vol)
    url = normalize_wiki_url(url)
    print(f"GET {url}")

    try:
        wikitext = fetch_wikitext(url)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.reject_if_table and wikitext_has_table_markup(wikitext):
        print("スキップ: wikitext に表マークアップを検出しました。", file=sys.stderr)
        return 4

    lines, err, file_suffix = materialize_volume_lines(
        args.vol, args.url, wikitext_override=wikitext, quiet_html_warning=False
    )
    if err or lines is None:
        print(f"警告: {err}", file=sys.stderr)
        return 1

    out_path = save_volume_text(base_dir, file_suffix, lines)
    print(f"保存: {out_path} ({len(lines)} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
