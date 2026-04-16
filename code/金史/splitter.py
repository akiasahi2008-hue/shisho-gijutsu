import argparse
import os
import re

from shiji_text import canonical_vol_suffix, normalize_source_lines


def normalize_vol_name(vol: str) -> str:
    """原文ファイル名用: 巻001 / 巻130（数字のみの指定は三位に揃える）"""
    return "巻" + canonical_vol_suffix(vol)


def resolve_source_path(base_dir: str, vol: str) -> str:
    vol_name = normalize_vol_name(vol)
    path = os.path.join(base_dir, "原文", f"{vol_name}.txt")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"原文ファイルが見つかりません: {path}\n"
            "bulk_preflight_fetch / wikisource_fetch で 原文/ を用意するか、"
            "workflow.py に --fetch を付けて取得してください。"
        )
    return path


def split_by_lines(lines, max_lines=15, max_chars=1900):
    blocks = []
    current = []
    current_chars = 0

    for line in lines:
        line_len = len(line) + 1
        over_lines = len(current) >= max_lines
        over_chars = current_chars + line_len > max_chars

        if current and (over_lines or over_chars):
            blocks.append("\n".join(current))
            current = []
            current_chars = 0

        current.append(line)
        current_chars += line_len

    if current:
        blocks.append("\n".join(current))

    return blocks


def extract_vol_suffix(vol_name: str) -> str:
    m = re.match(r"^巻(.+)$", vol_name)
    return m.group(1) if m else vol_name


def main():
    parser = argparse.ArgumentParser(description="金史原文をチャンク分割")
    parser.add_argument("vol", help="巻番号（例: 001, 1, 130, 巻001）")
    parser.add_argument("--base-dir", default=r"E:\マイドライブ\史書\金史", help="プロジェクトルート")
    parser.add_argument("--chunk-root", default="temp_chunks_deepseek", help="チャンク親フォルダ名")
    parser.add_argument("--max-lines", type=int, default=15, help="1チャンク最大行数")
    parser.add_argument("--max-chars", type=int, default=1900, help="1チャンク最大文字数")
    args = parser.parse_args()

    source_path = resolve_source_path(args.base_dir, args.vol)
    vol_name = normalize_vol_name(args.vol)
    vol_suffix = extract_vol_suffix(vol_name)

    with open(source_path, "r", encoding="utf-8-sig", newline="") as f:
        src_lines = [line.strip().replace("\r", "") for line in f.read().split("\n") if line.strip()]
    src_lines = normalize_source_lines(src_lines)

    blocks = split_by_lines(src_lines, max_lines=args.max_lines, max_chars=args.max_chars)

    vol_dir = os.path.join(args.base_dir, args.chunk_root, vol_suffix)
    os.makedirs(vol_dir, exist_ok=True)
    trans_dir = os.path.join(vol_dir, "translated")
    os.makedirs(trans_dir, exist_ok=True)

    for name in os.listdir(vol_dir):
        if name.startswith("chunk_") and name.endswith(".txt"):
            os.remove(os.path.join(vol_dir, name))

    for i, block in enumerate(blocks):
        chunk_path = os.path.join(vol_dir, f"chunk_{i:03}.txt")
        with open(chunk_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(block + "\n")

        numbered_path = os.path.join(vol_dir, f"chunk_{i:03}.numbered.txt")
        with open(numbered_path, "w", encoding="utf-8-sig", newline="") as nf:
            for j, line in enumerate(block.split("\n"), start=1):
                nf.write(f"{j:03d}|{line}\n")

    print(f"分割完了: {len(blocks)} チャンク")
    print(f"出力先: {vol_dir}")
    print(f"翻訳保存先: {trans_dir}")


if __name__ == "__main__":
    main()
