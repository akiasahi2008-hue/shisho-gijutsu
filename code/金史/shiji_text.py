"""
金史 Wikisource 由来テキストの正規化。

0. 「校勘記」を含む行以降（当該行を含む）を除去（Wikisource の校勘セクション）
1. 行中の「►」以降（ナビゲーション）を除去
2. PUA のみの行 → 直前行末尾に結合
3. 行内に残る PUA → 〓（欠字）に置換
4. 。！？ 等の直後にだけ付いた末尾 〓 を除去（冗長プレースホルダ。語中の「生〓」等は残す）
"""
from __future__ import annotations

import re

# 学術テキストで欠字によく使う記号（geta）
PUA_PLACEHOLDER = "〓"
_BLOCK_OPEN_TO_CLOSE = {
    "〈": "〉",
    "《": "》",
    "（": "）",
    "(": ")",
}


def _char_is_pua(ch: str) -> bool:
    o = ord(ch)
    if 0xE000 <= o <= 0xF8FF:
        return True
    if 0xF0000 <= o <= 0xFFFFD:
        return True
    if 0x100000 <= o <= 0x10FFFD:
        return True
    return False


def is_pua_only_line(s: str) -> bool:
    """行が PUA と空白だけで構成されるか（Wikisource の欠字プレースホルダ等）。"""
    s = s.replace("\uFEFF", "").strip()
    if not s:
        return True
    for ch in s:
        if ch.isspace():
            continue
        if not _char_is_pua(ch):
            return False
    return True


def merge_pua_only_lines(lines: list[str]) -> list[str]:
    """
    PUA のみの行を直前行の末尾に結合する。先頭に孤立した PUA 行は捨てる。
    翻訳の「1行＝1要素」とモデルの行省略を防ぐ。
    """
    out: list[str] = []
    for line in lines:
        if is_pua_only_line(line):
            raw = line.replace("\uFEFF", "")
            frag = "".join(ch for ch in raw if not ch.isspace())
            if not frag:
                continue
            if out:
                out[-1] = out[-1].rstrip() + frag
            continue
        out.append(line)
    return out


def merge_standalone_bracket_blocks(lines: list[str]) -> list[str]:
    """
    独立行の注釈ブロック（例: 〈 ... 〉）を前行へ畳み込む。
    手動コピペ時の改行崩れによる段落分割を減らす。
    """
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        close = _BLOCK_OPEN_TO_CLOSE.get(line)
        if close and out:
            i += 1
            inner: list[str] = []
            while i < n:
                cur = lines[i].strip()
                if cur == close:
                    break
                inner.append(cur)
                i += 1

            if i < n and lines[i].strip() == close:
                out[-1] = out[-1].rstrip() + line + "".join(inner) + close
                i += 1
                continue

            # 閉じが見つからない場合は元の形を保つ
            out.append(line)
            out.extend(inner)
            continue

        out.append(lines[i])
        i += 1
    return out


def merge_broken_continuations(lines: list[str]) -> list[str]:
    """
    行末が「。及」で切れて次行へ続く崩れを結合する。
    Wikisource raw で見られる段落分割ノイズ対策。
    """
    if not lines:
        return lines
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        cur = lines[i]
        if i + 1 < n:
            nxt = lines[i + 1].lstrip()
            if cur.endswith("。及") and nxt:
                out.append(cur + nxt)
                i += 2
                continue
        out.append(cur)
        i += 1
    return out


def replace_embedded_pua(text: str, repl: str = PUA_PLACEHOLDER) -> str:
    """行の途中・末尾に残った私用領域文字をプレースホルダに置き換える。"""
    if not any(_char_is_pua(ch) for ch in text):
        return text
    return "".join(repl if _char_is_pua(ch) else ch for ch in text)


# 句読点の直後に付いた 〓 は、Wiki 由来の冗長プレースホルダであることが多い（意味上の欠字ではない）
_TAIL_GETA_OK_BEFORE = frozenset("。！？」』…")


def truncate_before_kokan_ki(lines: list[str]) -> list[str]:
    """「校勘記」を含む行およびそれ以降の行を捨てる（本文外の校勘欄）。"""
    out: list[str] = []
    for line in lines:
        if "校勘記" in line:
            break
        out.append(line)
    return out


def strip_nav_after_triangle(line: str) -> str:
    """行中の '►' 以降を除去する（例: 『... ► 次巻』）。"""
    return re.sub(r"\s*►.*$", "", line).rstrip()


def strip_redundant_tail_geta(line: str) -> str:
    """『…。〓』のように、文末のあとにだけ付いた 〓 を落とす。『生〓』のように語中の 〓 は残す。"""
    s = line.rstrip()
    plen = len(PUA_PLACEHOLDER)
    while s.endswith(PUA_PLACEHOLDER) and len(s) >= 1 + plen:
        prev = s[-1 - plen]
        if prev in _TAIL_GETA_OK_BEFORE:
            s = s[: -plen]
        else:
            break
    return s


def normalize_source_lines(lines: list[str]) -> list[str]:
    """取得・分割の直前に呼ぶ。校勘記以降の除去 + ►以降除去 + PUA処理 + 文末冗長〓除去。"""
    lines = truncate_before_kokan_ki(lines)
    lines = [strip_nav_after_triangle(line) for line in lines]
    merged = merge_pua_only_lines(lines)
    merged = merge_standalone_bracket_blocks(merged)
    merged = merge_broken_continuations(merged)
    out: list[str] = []
    for line in merged:
        t = replace_embedded_pua(line)
        t = strip_redundant_tail_geta(t)
        if t.strip():
            out.append(t)
    return out


def canonical_vol_suffix(vol: str) -> str:
    """
    原文ファイル・temp_chunks フォルダ・和訳ファイルで共通の巻接尾辞。
    1〜135 の巻は桁埋めなし（例: 1 -> 1）。上中下付きは wikisource_fetch の保存名と揃え 43上 等。
    「巻」「卷」プレフィックスは除去してから解釈する。
    """
    s = vol.strip()
    if s.startswith("巻"):
        s = s[1:]
    elif s.startswith("卷"):
        s = s[1:]

    m = re.fullmatch(r"0*(\d+)(上|中|下)?", s)
    if m:
        n = int(m.group(1))
        part = m.group(2) or ""
        if 1 <= n <= 135:
            return f"{n}{part}"
    return s
