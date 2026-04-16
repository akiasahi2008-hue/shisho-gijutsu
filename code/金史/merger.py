import argparse
import os
import re

from shiji_text import canonical_vol_suffix


def normalize_vol(vol: str) -> str:
    return canonical_vol_suffix(vol)


def collect_chunk_files(path: str):
    pat = re.compile(r"^chunk_(\d+)\.txt$")
    items = []
    for name in os.listdir(path):
        m = pat.match(name)
        if m:
            items.append((int(m.group(1)), name))
    items.sort()
    return items


def assert_contiguous(items):
    if not items:
        raise ValueError("chunk がありません。")
    for idx, (n, _) in enumerate(items):
        if idx != n:
            raise ValueError(f"チャンク番号が連続していません。期待: {idx:03}, 実際: {n:03}")


def main():
    parser = argparse.ArgumentParser(description="金史: translated/chunk_*.txt を結合")
    parser.add_argument("vol", help="巻番号（例: 001, 130）")
    parser.add_argument("--base-dir", default=r"E:\マイドライブ\史書\金史", help="プロジェクトルート")
    parser.add_argument("--chunk-root", default="temp_chunks_deepseek", help="チャンク親フォルダ")
    parser.add_argument("--output-file", default=None, help="出力先（省略時: 和訳/巻<vol>.txt）")
    args = parser.parse_args()

    vol_suffix = normalize_vol(args.vol)
    trans_dir = os.path.join(args.base_dir, args.chunk_root, vol_suffix, "translated")
    if not os.path.isdir(trans_dir):
        raise FileNotFoundError(f"translated フォルダが見つかりません: {trans_dir}")

    items = collect_chunk_files(trans_dir)
    assert_contiguous(items)

    if args.output_file:
        out_path = args.output_file
        if not os.path.isabs(out_path):
            out_path = os.path.join(args.base_dir, out_path)
    else:
        out_path = os.path.join(args.base_dir, "和訳", f"巻{vol_suffix}.txt")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    merged = 0
    with open(out_path, "w", encoding="utf-8-sig", newline="") as out:
        for _, name in items:
            path = os.path.join(trans_dir, name)
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                content = f.read().replace("\r", "")
            out.write(content)
            if not content.endswith("\n"):
                out.write("\n")
            merged += 1

    print(f"結合完了: {merged} chunks")
    print(f"出力先: {out_path}")


if __name__ == "__main__":
    main()
