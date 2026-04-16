"""
原文フォルダのみに対し、テキスト整備手順 2〜4 に相当する処理を順に実行する。

1. strip_wiki_templates.py --folders 原文
2. remove_toc_lines.py --folders 原文
3. remove_wiki_html_artifacts.py --folders 原文
4. scan_raw_text_issues.py（英字・置換文字のレポート。自動削除はしない）

実行前にバックアップまたは Git コミットを推奨。

  python cleanup_raw_pipeline.py --base-dir "E:\\マイドライブ\\史書\\金史"
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="原文のテキスト整備パイプライン")
    parser.add_argument(
        "--base-dir",
        default=r"E:\マイドライブ\史書\金史",
        help="プロジェクトルート",
    )
    parser.add_argument(
        "--skip-scan",
        action="store_true",
        help="最後の英字・置換文字レポートをスキップ",
    )
    args = parser.parse_args()
    base = os.path.normpath(args.base_dir)
    py = sys.executable
    fo = "原文"
    steps: list[tuple[str, list[str]]] = [
        ("strip_wiki_templates.py", ["--folders", fo]),
        ("remove_toc_lines.py", ["--folders", fo]),
        ("remove_wiki_html_artifacts.py", ["--folders", fo]),
    ]
    for script, extra in steps:
        cmd = [py, os.path.join(base, script)] + extra
        print("+", " ".join(cmd))
        r = subprocess.run(cmd, cwd=base)
        if r.returncode != 0:
            print(f"error: {script} exit {r.returncode}", file=sys.stderr)
            return r.returncode

    if not args.skip_scan:
        cmd = [
            py,
            os.path.join(base, "scan_raw_text_issues.py"),
            "--base-dir",
            base,
            "--folders",
            fo,
        ]
        print("+", " ".join(cmd))
        r = subprocess.run(cmd, cwd=base)
        if r.returncode != 0:
            return r.returncode
    print("cleanup_raw_pipeline done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
