"""
単巻・範囲の和訳パイプライン（fetch → split → DeepSeek → merge）。

金史では先に bulk_preflight_fetch.py と cleanup_raw_pipeline.py で 原文/ を整え、
本スクリプトは既定で 原文/巻*.txt のみを読んで分割・翻訳する（Wikisource は取りに行かない）。
Wikisource から取り直すときだけ --fetch を付ける。
"""
import argparse
import json
import os
import re
import subprocess
import sys

from shiji_text import canonical_vol_suffix


def run(cmd, cwd):
    print("+", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"コマンド失敗: {' '.join(cmd)}")


def _vol_sort_key(s: str) -> tuple:
    if s == "序":
        return (-1, 0, 0, s)
    m = re.match(r"^(\d+)(上|中|下)?$", s)
    if m:
        n = int(m.group(1))
        suf = m.group(2) or ""
        order = {"上": 0, "中": 1, "下": 2, "": 3}
        return (0, n, order.get(suf, 9), s)
    return (2, 0, 0, s)


def _discover_volumes(base_dir: str) -> list[str]:
    raw_dir = os.path.join(base_dir, "原文")
    if not os.path.isdir(raw_dir):
        return []
    vols = []
    pat = re.compile(r"^巻(.+)\.txt$")
    for name in os.listdir(raw_dir):
        m = pat.match(name)
        if m:
            vols.append(m.group(1))
    vols.sort(key=_vol_sort_key)
    return vols


def _resolve_vol(args, base_dir: str) -> str:
    if args.vol:
        return args.vol
    if args.vol_opt:
        return args.vol_opt

    vols = _discover_volumes(base_dir)
    if vols:
        print("巻番号を入力してください（例: 1 / 01 / 001 / 130）")
        print("利用可能例:", ", ".join(vols[:12]) + (" ..." if len(vols) > 12 else ""))
    else:
        print(
            "巻番号を入力してください（例: 1 / 001）※ 先に fetch で原文を取得すると候補が表示されます。"
        )
    val = input("> ").strip()
    if not val:
        raise RuntimeError("巻番号が未入力です。")
    return val


def _load_failed_chunks(base_dir: str, chunk_root: str, vol: str) -> list[str]:
    vol_suffix = canonical_vol_suffix(vol)
    progress_path = os.path.join(base_dir, chunk_root, vol_suffix, "progress.json")
    if not os.path.exists(progress_path):
        return []
    try:
        with open(progress_path, "r", encoding="utf-8-sig", newline="") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    failed = obj.get("failed_chunks", [])
    if isinstance(failed, list):
        return [str(x) for x in failed]
    return []


def main():
    parser = argparse.ArgumentParser(description="金史: fetch -> split -> Deepseek翻訳 -> merge")
    parser.add_argument("vol", nargs="?", help="巻番号（例: 1, 001, 130, 巻001）")
    parser.add_argument("--vol", dest="vol_opt", default=None, help="巻番号（位置引数の代替）")
    parser.add_argument("--base-dir", default=r"E:\マイドライブ\史書\金史", help="プロジェクトルート")
    parser.add_argument("--chunk-root", default="temp_chunks_deepseek", help="チャンク親フォルダ")
    parser.add_argument(
        "--max-lines",
        type=int,
        default=15,
        help="split時の1チャンク最大行数（巻頭で行数不一致が続く場合は 5～8 や --fast-stable も試す）",
    )
    parser.add_argument("--max-chars", type=int, default=1900, help="split時の1チャンク最大文字数")
    parser.add_argument("--model", default="deepseek-chat", help="Deepseekモデル名")
    parser.add_argument("--temperature", type=float, default=0.2, help="翻訳温度")
    parser.add_argument("--sleep-sec", type=float, default=0.6, help="API呼び出し間隔")
    parser.add_argument("--max-retries", type=int, default=5, help="通常翻訳の最大リトライ回数")
    parser.add_argument("--retry-base-sec", type=float, default=1.5, help="リトライ待機の基準秒")
    parser.add_argument("--line-fix-retries", type=int, default=5, help="行数不一致時の修正試行回数")
    parser.add_argument("--fix-temperature", type=float, default=0.05, help="行数修正フェーズの温度")
    parser.add_argument("--timeout-sec", type=float, default=240.0, help="API タイムアウト秒")
    parser.add_argument(
        "--fast-stable",
        action="store_true",
        help="安定重視プリセット（max-lines=5, max-chars=1000, max-retries=5）",
    )
    parser.add_argument("--overwrite", action="store_true", help="既存 translated/chunk_*.txt を上書き")
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="実行前に wikisource_fetch で Wikisource から原文を取得する（省略時は 原文/ の既存 TXT のみ使用）",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--fetch-url",
        default=None,
        help="wikisource_fetch に渡す完全 URL（通常は不要）",
    )
    parser.add_argument(
        "--prompt-file",
        default=r"E:\マイドライブ\史書\金史\翻訳プロンプト2.txt",
        help="翻訳プロンプトファイル",
    )
    parser.add_argument(
        "--output-format",
        choices=("json", "lines"),
        default="json",
        help="DeepSeek 応答形式: json=translations 配列（既定）、lines=改行区切り",
    )
    args = parser.parse_args()

    base_dir = os.path.normpath(args.base_dir)
    vol = _resolve_vol(args, base_dir)
    py = sys.executable

    if args.fast_stable:
        args.max_lines = 5
        args.max_chars = 1000
        if args.max_retries < 5:
            args.max_retries = 5
        if args.line_fix_retries < 6:
            args.line_fix_retries = 6
        print(
            "preset: fast-stable (max-lines=5, max-chars=1000, "
            "max-retries>=5, line-fix-retries>=6)"
        )

    if args.fetch:
        fetch_cmd = [
            py,
            os.path.join(base_dir, "wikisource_fetch.py"),
            vol,
            "--base-dir",
            base_dir,
        ]
        if args.fetch_url:
            fetch_cmd.extend(["--url", args.fetch_url])
        run(fetch_cmd, base_dir)

    split_cmd = [
        py,
        os.path.join(base_dir, "splitter.py"),
        vol,
        "--base-dir",
        base_dir,
        "--chunk-root",
        args.chunk_root,
        "--max-lines",
        str(args.max_lines),
        "--max-chars",
        str(args.max_chars),
    ]
    run(split_cmd, base_dir)

    trans_cmd = [
        py,
        os.path.join(base_dir, "deepseek_translate.py"),
        vol,
        "--base-dir",
        base_dir,
        "--chunk-root",
        args.chunk_root,
        "--model",
        args.model,
        "--temperature",
        str(args.temperature),
        "--sleep-sec",
        str(args.sleep_sec),
        "--max-retries",
        str(args.max_retries),
        "--retry-base-sec",
        str(args.retry_base_sec),
        "--line-fix-retries",
        str(args.line_fix_retries),
        "--fix-temperature",
        str(args.fix_temperature),
        "--timeout-sec",
        str(args.timeout_sec),
        "--prompt-file",
        args.prompt_file,
        "--output-format",
        args.output_format,
    ]
    if args.overwrite:
        trans_cmd.append("--overwrite")
    run(trans_cmd, base_dir)

    failed = _load_failed_chunks(base_dir, args.chunk_root, vol)
    if failed:
        print("翻訳は完了しましたが、未解決の失敗チャンクがあるため merge をスキップします。")
        print("failed_chunks:", ", ".join(failed))
        print(f"確認: python \"{os.path.join(base_dir, 'status.py')}\" \"{vol}\"")
        return

    merge_cmd = [
        py,
        os.path.join(base_dir, "merger.py"),
        vol,
        "--base-dir",
        base_dir,
        "--chunk-root",
        args.chunk_root,
    ]
    run(merge_cmd, base_dir)

    print("一括処理完了")


if __name__ == "__main__":
    main()
