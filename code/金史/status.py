import argparse
import json
import os
import re

from shiji_text import canonical_vol_suffix


def normalize_vol(vol: str) -> str:
    return canonical_vol_suffix(vol)


def list_source_chunks(vol_dir: str):
    pat = re.compile(r"^chunk_(\d+)\.txt$")
    items = []
    if not os.path.isdir(vol_dir):
        return items
    for name in os.listdir(vol_dir):
        m = pat.match(name)
        if m:
            items.append((int(m.group(1)), name))
    items.sort()
    return [name for _, name in items]


def list_translated_chunks(trans_dir: str):
    return list_source_chunks(trans_dir)


def load_progress(progress_path: str) -> dict:
    if not os.path.exists(progress_path):
        return {}
    try:
        with open(progress_path, "r", encoding="utf-8-sig", newline="") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def main():
    parser = argparse.ArgumentParser(description="翻訳進捗の確認（金史）")
    parser.add_argument("vol", help="巻番号（例: 001, 130）")
    parser.add_argument("--base-dir", default=r"E:\マイドライブ\史書\金史", help="プロジェクトルート")
    parser.add_argument("--chunk-root", default="temp_chunks_deepseek", help="チャンク親フォルダ")
    args = parser.parse_args()

    vol_suffix = normalize_vol(args.vol)
    vol_dir = os.path.join(args.base_dir, args.chunk_root, vol_suffix)
    trans_dir = os.path.join(vol_dir, "translated")
    progress_path = os.path.join(vol_dir, "progress.json")
    failed_log_path = os.path.join(vol_dir, "failed_chunks.txt")
    wayaku_path = os.path.join(args.base_dir, "和訳", f"巻{vol_suffix}.txt")

    source_chunks = list_source_chunks(vol_dir)
    translated_chunks = list_translated_chunks(trans_dir)
    progress = load_progress(progress_path)

    total = len(source_chunks)
    done = len(translated_chunks)
    remain = max(total - done, 0)
    failed = progress.get("failed_chunks", []) if isinstance(progress, dict) else []
    status = progress.get("status", "unknown") if isinstance(progress, dict) else "unknown"
    last_success = progress.get("last_success_chunk", "") if isinstance(progress, dict) else ""
    updated_at = progress.get("updated_at", "") if isinstance(progress, dict) else ""

    print(f"巻: {vol_suffix}")
    print(f"status: {status}")
    print(f"total_chunks: {total}")
    print(f"translated_chunks: {done}")
    print(f"remaining_chunks: {remain}")
    print(f"failed_chunks: {len(failed)}")
    if failed:
        print("failed_list: " + ", ".join(failed))
    if last_success:
        print(f"last_success_chunk: {last_success}")
    if updated_at:
        print(f"updated_at: {updated_at}")
    print(f"progress_file: {progress_path}")
    print(f"failed_log: {failed_log_path}")
    print(f"wayaku_file: {wayaku_path}")


if __name__ == "__main__":
    main()
