"""
原文（または指定フォルダ）内の .txt を走査し、調査用レポートを出力する。

- 行内に [A-Za-z] を含む箇所（ウィキ・URL・タグ残骸の手掛かり）
- Unicode 置換文字 U+FFFD（文字化けの可能性）

自動修正は行わない。レポートを見て手修正するか、別スクリプトで対応する。

  python scan_raw_text_issues.py --base-dir "E:\\マイドライブ\\史書\\金史" --folders 原文
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

_LATIN = re.compile(r"[A-Za-z]")


def main() -> int:
    parser = argparse.ArgumentParser(description="原文の英字・置換文字レポート")
    parser.add_argument(
        "--base-dir",
        default=r"E:\マイドライブ\史書\金史",
        help="プロジェクトルート",
    )
    parser.add_argument(
        "--folders",
        default="原文",
        help="カンマ区切り（既定: 原文）",
    )
    parser.add_argument(
        "--out",
        default="",
        help="出力レポートパス（空なら base-dir 直下の 原文_テキスト調査.txt）",
    )
    args = parser.parse_args()
    base = Path(args.base_dir).resolve()
    out_path = Path(args.out) if args.out else base / "原文_テキスト調査.txt"
    folders = [x.strip() for x in args.folders.split(",") if x.strip()]

    lines_out: list[str] = []
    for fname in folders:
        d = base / fname
        if not d.is_dir():
            lines_out.append(f"# skip (not found): {d}\n")
            continue
        for path in sorted(d.glob("*.txt")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as e:
                lines_out.append(f"# read error {path}: {e}\n")
                continue
            if "\ufffd" in text:
                lines_out.append(f"{path.name}\tREPLACEMENT_CHAR\tcount={text.count(chr(0xFFFD))}\n")
            for i, line in enumerate(text.splitlines(), 1):
                if _LATIN.search(line):
                    snippet = line.strip()[:200]
                    lines_out.append(f"{path.name}\tline {i}\t{snippet}\n")

    out_path.write_text("".join(lines_out), encoding="utf-8", newline="\n")
    print(f"wrote {out_path} ({len(lines_out)} report lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
