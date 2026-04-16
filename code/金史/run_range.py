import argparse
import os
import re
import subprocess
import sys
import urllib.parse

URL_LIST_NAME = "URLリスト.txt"
BOOK_WIKI = "\u91d1\u53f2"  # 金史
MAX_JUAN = 135


def parse_vol_from_line(line: str) -> str | None:
    m = re.search(r"https?://[^\s]+", line)
    if not m:
        return None
    p = urllib.parse.urlparse(m.group(0))
    parts = [urllib.parse.unquote(x) for x in p.path.split("/") if x]
    if len(parts) >= 3 and parts[0].lower() == "wiki" and parts[1] == BOOK_WIKI:
        return parts[2]
    um = re.search(r"/" + BOOK_WIKI + r"/(\u5377[^\s#/]+)", line)
    if um:
        return um.group(1)
    for u in re.finditer(r"https?://[^\s]+", line):
        p2 = urllib.parse.urlparse(u.group(0))
        seg = urllib.parse.unquote(p2.path.rstrip("/").split("/")[-1])
        if seg and seg != BOOK_WIKI:
            return seg
    return None


def normalize_vol_token_for_match(t: str) -> str:
    s = t.strip().strip('"').replace("\u5dfb", "").replace("\u5377", "")
    return s


def load_volumes_from_url_list(path: str) -> list[str]:
    if not os.path.isfile(path):
        return []
    vols: list[str] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            v = parse_vol_from_line(line)
            if v:
                vols.append(v)
    return vols


def _split_vol(vol: str) -> tuple[int, str] | None:
    m = re.match(r"^\u53770*(\d+)(\u4e0a|\u4e2d|\u4e0b)?$", vol)
    if not m:
        return None
    return int(m.group(1)), (m.group(2) or "")


def _vol_to_num(vol: str) -> int | None:
    s = _split_vol(vol)
    return s[0] if s else None


def vol_to_sort_key(vol: str) -> tuple:
    xu = "\u5e8f"
    if vol == xu:
        return (-1, 0, vol)
    sp = _split_vol(vol)
    if sp is not None:
        n, suf = sp
        order = {"": 0, "上": 1, "中": 2, "下": 3}
        return (0, n, order.get(suf, 9), vol)
    return (2, 0, vol)


def _canonical_vol_id(raw: str, vols_all: list[str]) -> str:
    t = normalize_vol_token_for_match(raw)
    xu = "\u5e8f"
    juan = "\u5377"
    if t in vols_all:
        return t
    if raw.strip() in vols_all:
        return raw.strip()
    if t == xu and xu in vols_all:
        return xu
    m_num_part = re.fullmatch(r"(\d+)(上|中|下)?", t)
    if m_num_part:
        n = int(m_num_part.group(1))
        suf = m_num_part.group(2) or ""
        if 1 <= n <= MAX_JUAN:
            for cand in (
                f"{juan}{n}{suf}",
                f"{juan}{n:02d}{suf}",
                f"{juan}{n:03d}{suf}",
            ):
                if cand in vols_all:
                    return cand
    return t if t in vols_all else raw.strip()


def _vol_number(vol: str) -> int:
    xu = "\u5e8f"
    if vol == xu:
        return 0
    sp = _split_vol(vol)
    return sp[0] if sp is not None else 99999


def load_all_volumes_sorted(base_dir: str) -> list[str]:
    list_path = os.path.join(base_dir, URL_LIST_NAME)
    vols = load_volumes_from_url_list(list_path)
    xu = "\u5e8f"
    juan = "\u5dfb"
    yuan = "\u539f\u6587"
    ju = "\u5377"
    if not vols:
        raw_dir = os.path.join(base_dir, yuan)
        if not os.path.isdir(raw_dir):
            raise FileNotFoundError(
                f"{URL_LIST_NAME} / {yuan} not found.\n{list_path}"
            )
        pat = re.compile(r"^" + juan + r"(.+)\.txt$")
        for name in os.listdir(raw_dir):
            m = pat.match(name)
            if m:
                inner = m.group(1)
                if inner == xu:
                    vols.append(xu)
                elif re.fullmatch(r"\d+", inner):
                    n = int(inner)
                    if 1 <= n <= MAX_JUAN:
                        vols.append(f"{ju}{n:03d}")
                else:
                    vols.append(inner)
        vols = sorted(set(vols), key=vol_to_sort_key)
    else:
        vols = sorted(set(vols), key=vol_to_sort_key)
    return vols


def _normalize_vol_token(s: str) -> str:
    raw = s.strip().strip('"')
    xu = "\u5e8f"
    if raw == xu:
        return xu
    n = _vol_to_num(raw)
    if n is not None:
        return str(n)
    t = raw.replace("\u5dfb", "").replace("\u5377", "")
    if t == xu:
        return xu
    m = re.match(r"^(\d+)(\u4e0a|\u4e2d|\u4e0b)?$", t)
    if not m:
        raise ValueError(f"bad volume token: {s}")
    return m.group(1) + (m.group(2) or "")


def collect_volumes(base_dir: str, start_s: str, end_s: str) -> list[str]:
    vols_all = load_all_volumes_sorted(base_dir)
    if not vols_all:
        return []

    start_c = _canonical_vol_id(start_s, vols_all)
    end_c = _canonical_vol_id(end_s, vols_all)

    start_v = _normalize_vol_token(start_c)
    end_v = _normalize_vol_token(end_c)

    start_plain = re.match(r"^(\d+)$", start_v)
    end_plain = re.match(r"^(\d+)$", end_v)
    if start_plain and end_plain:
        n0, n1 = int(start_plain.group(1)), int(end_plain.group(1))
        if n0 > n1:
            raise ValueError("start must be <= end")
        out = [v for v in vols_all if n0 <= _vol_number(v) <= n1]
        return sorted(out, key=vol_to_sort_key)

    xu = "\u5e8f"
    if start_v == xu and end_v == xu:
        if xu in vols_all:
            return [xu]
        raise ValueError("preface xu not in URL list")

    try:
        i0 = vols_all.index(start_c)
    except ValueError as e:
        raise ValueError(
            f"start not in list ({start_s}). Check {URL_LIST_NAME}."
        ) from e

    end_plain_only = re.match(r"^(\d+)$", end_v)
    if end_plain_only:
        n_end = int(end_plain_only.group(1))
        i1 = -1
        for i, v in enumerate(vols_all):
            if i < i0:
                continue
            if _vol_number(v) <= n_end:
                i1 = i
        if i1 < 0:
            raise ValueError(f"no volume up to {n_end}")
    else:
        try:
            i1 = vols_all.index(end_c)
        except ValueError as e:
            raise ValueError(
                f"end not in list ({end_s}). Check {URL_LIST_NAME}."
            ) from e
    if i0 > i1:
        raise ValueError("start after end")
    return vols_all[i0 : i1 + 1]


def wiki_vol_to_fetch_arg(vol: str) -> str:
    xu = "\u5e8f"
    if vol == xu:
        return xu
    sp = _split_vol(vol)
    if sp is not None:
        n, suf = sp
        return f"{n}{suf}"
    return vol


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run workflow.py for Jin Shi (金史) volume range"
    )
    parser.add_argument("start", help="start: 1 or 01")
    parser.add_argument("end", help="end: 135 など")
    parser.add_argument(
        "--base-dir",
        default=r"E:\マイドライブ\史書\金史",
        help="project root",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="各巻で workflow 実行前に Wikisource から原文を取得する（省略時は 原文/ の TXT のみ使用）",
    )
    args = parser.parse_args()
    args.base_dir = os.path.normpath(args.base_dir.strip().strip('"'))

    try:
        vols = collect_volumes(args.base_dir, args.start, args.end)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not vols:
        print("no volumes matched")
        return 1

    fetch_args = [wiki_vol_to_fetch_arg(v) for v in vols]
    print("volumes:", ", ".join(fetch_args))
    py = sys.executable
    workflow = os.path.join(args.base_dir, "workflow.py")
    for vol_arg in fetch_args:
        print("-" * 40)
        print(f"running: {vol_arg}")
        cmd = [py, workflow, vol_arg, "--base-dir", args.base_dir]
        if args.fetch:
            cmd.append("--fetch")
        rc = subprocess.call(cmd, cwd=args.base_dir)
        if rc != 0:
            print(f"error: {vol_arg} exit={rc}")
            return rc
    print("range done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
