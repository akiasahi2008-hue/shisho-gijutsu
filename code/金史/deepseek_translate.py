import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request

from shiji_text import canonical_vol_suffix

API_URL = "https://api.deepseek.com/chat/completions"


def normalize_vol(vol: str) -> str:
    return canonical_vol_suffix(vol)


def list_chunk_files(vol_dir: str):
    pat = re.compile(r"^chunk_(\d+)\.txt$")
    items = []
    for name in os.listdir(vol_dir):
        m = pat.match(name)
        if m:
            items.append((int(m.group(1)), name))
    items.sort()
    return [name for _, name in items]


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return f.read().replace("\r", "").strip()


def build_wayaku_path(base_dir: str, vol_suffix: str) -> str:
    return os.path.join(base_dir, "和訳", f"巻{vol_suffix}.txt")


def merge_translated_chunks(trans_dir: str, out_path: str) -> int:
    chunk_names = list_chunk_files(trans_dir)
    if not chunk_names:
        raise FileNotFoundError(f"translated/chunk_*.txt が見つかりません: {trans_dir}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    merged = 0
    with open(out_path, "w", encoding="utf-8-sig", newline="") as out:
        for name in chunk_names:
            path = os.path.join(trans_dir, name)
            content = read_text(path)
            out.write(content)
            out.write("\n")
            merged += 1
    return merged


def build_progress_path(vol_dir: str) -> str:
    return os.path.join(vol_dir, "progress.json")


def load_progress(progress_path: str) -> dict:
    if not os.path.exists(progress_path):
        return {
            "status": "running",
            "updated_at": "",
            "total_chunks": 0,
            "done_chunks": [],
            "failed_chunks": [],
            "last_success_chunk": "",
            "last_error": "",
        }
    try:
        with open(progress_path, "r", encoding="utf-8-sig", newline="") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {
            "status": "running",
            "updated_at": "",
            "total_chunks": 0,
            "done_chunks": [],
            "failed_chunks": [],
            "last_success_chunk": "",
            "last_error": "",
        }


def save_progress(progress_path: str, progress: dict) -> None:
    progress["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(progress_path, "w", encoding="utf-8-sig", newline="") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
        f.write("\n")


def normalize_done_from_existing(progress: dict, trans_dir: str) -> None:
    existing = list_chunk_files(trans_dir)
    done = set(progress.get("done_chunks", []))
    for name in existing:
        done.add(name)
    progress["done_chunks"] = sorted(done)


def mark_failed(progress: dict, chunk_name: str) -> None:
    failed = set(progress.get("failed_chunks", []))
    failed.add(chunk_name)
    progress["failed_chunks"] = sorted(failed)


def unmark_failed(progress: dict, chunk_name: str) -> None:
    failed = set(progress.get("failed_chunks", []))
    if chunk_name in failed:
        failed.remove(chunk_name)
    progress["failed_chunks"] = sorted(failed)


def append_failed_chunk_log(vol_dir: str, chunk_name: str, err_text: str) -> None:
    path = os.path.join(vol_dir, "failed_chunks.txt")
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {chunk_name} {err_text}\n")


def nonempty_lines(text: str) -> list[str]:
    return [line for line in text.replace("\r", "").split("\n") if line.strip()]


def to_numbered_text(lines: list[str]) -> str:
    return "\n".join(f"{i:03d}|{line}" for i, line in enumerate(lines, start=1))


def strip_markdown_code_fence(text: str) -> str:
    """説明文のあとの ```json ... ``` から JSON 部分だけ取り出す。"""
    t = text.replace("\ufeff", "").strip()
    start = t.find("```")
    if start == -1:
        return t
    rest = t[start + 3 :].lstrip()
    if rest.lower().startswith("json"):
        rest = rest[4:].lstrip()
    if rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("```")
    if end == -1:
        return t
    inner = rest[:end].strip()
    return inner if inner.startswith("{") else t


def strip_wrapping(text: str) -> str:
    """``` で囲まれた出力などを外す（文中フェンスにも対応）。"""
    t = text.replace("\ufeff", "").strip()
    inner = strip_markdown_code_fence(t)
    if inner != t:
        return inner
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _repair_json_light(s: str) -> str:
    """末尾カンマなど、軽い JSON 崩れを直す。"""
    s = s.strip()
    s = re.sub(r",(\s*])", r"\1", s)
    s = re.sub(r",(\s*})", r"\1", s)
    return s


def call_deepseek_messages(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float,
    timeout_sec: float = 240.0,
) -> str:
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Deepseek API HTTPエラー: {e.code} {err}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Deepseek API接続エラー: {e}") from e

    obj = json.loads(body)
    choices = obj.get("choices") or []
    if not choices:
        raise RuntimeError(f"Deepseek API応答が不正です: {body}")
    content = choices[0].get("message", {}).get("content", "")
    return content.strip()


def validate_line_count(src_n: int, raw_output: str) -> tuple[bool, str, list[str]]:
    cleaned = strip_wrapping(raw_output)
    if not cleaned.strip():
        return False, "空の翻訳結果が返されました。", []
    out_lines = nonempty_lines(cleaned)
    if len(out_lines) != src_n:
        return False, f"行数不一致: source={src_n} translated={len(out_lines)}", out_lines
    return True, "", out_lines


def extract_json_object(raw: str) -> dict | None:
    """応答から translations を含む JSON オブジェクトを取り出す（フェンス・前置きに寛容）。"""
    t0 = raw.replace("\ufeff", "").strip()
    candidates: list[str] = []
    for c in (
        strip_markdown_code_fence(t0),
        strip_wrapping(t0),
        t0,
    ):
        c = c.strip()
        if c and c not in candidates:
            candidates.append(c)

    dec = json.JSONDecoder()
    for t in candidates:
        for variant in (t, _repair_json_light(t)):
            for i, ch in enumerate(variant):
                if ch != "{":
                    continue
                try:
                    obj, _end = dec.raw_decode(variant[i:])
                    if isinstance(obj, dict) and "translations" in obj:
                        return obj
                except json.JSONDecodeError:
                    continue
    return None


def validate_json_translations(src_n: int, raw_output: str) -> tuple[bool, str, list[str]]:
    obj = extract_json_object(raw_output)
    if not obj:
        return False, "JSON を解釈できませんでした。", []
    arr = obj.get("translations")
    if not isinstance(arr, list):
        return False, 'JSON に "translations" 配列がありません。', []
    if len(arr) != src_n:
        return False, f"JSON 要素数不一致: source={src_n} translated={len(arr)}", []
    out: list[str] = []
    for i, item in enumerate(arr):
        if item is None:
            return False, f"translations[{i}] が null です。", []
        s = str(item).replace("\r", " ").replace("\n", " ").strip()
        if not s:
            return False, f"translations[{i}] が空です。", []
        out.append(s)
    return True, "", out


def translate_chunk(
    *,
    chunk_name: str,
    api_key: str,
    model: str,
    system_prompt: str,
    src_lines: list[str],
    user_initial: str,
    numbered_src: str,
    temperature: float,
    max_retries: int,
    retry_base_sec: float,
    line_fix_retries: int,
    fix_temperature: float,
    timeout_sec: float,
    output_json: bool,
) -> tuple[bool, str, str]:
    """
    戻り値: (成功, 正規化済み本文（行ごと改行）, 最後のエラー文)
    """
    n = len(src_lines)
    last_err = ""
    last_raw = ""
    temp = temperature
    validate = validate_json_translations if output_json else validate_line_count

    for attempt in range(1, max_retries + 1):
        try:
            last_raw = call_deepseek_messages(
                api_key,
                model,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_initial},
                ],
                temp,
                timeout_sec=timeout_sec,
            )
            ok, err, out_lines = validate(n, last_raw)
            if ok:
                return True, "\n".join(out_lines) + "\n", ""
            last_err = err
            temp = min(temp, 0.12)
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        if attempt < max_retries:
            wait_sec = retry_base_sec * (2 ** (attempt - 1))
            print(
                f"retry: {chunk_name} attempt={attempt}/{max_retries} "
                f"wait={wait_sec:.1f}s err={last_err}"
            )
            time.sleep(wait_sec)

    # JSON の要素数不一致はマルチターン修正でも直りにくい。短めのチャンクは line-fix を省き、
    # 呼び出し側の 1 行ずつ翻訳フォールバックへ早く回す。
    if (
        output_json
        and n <= 32
        and last_err
        and (
            "要素数不一致" in last_err
            or "JSON を解釈できませんでした" in last_err
        )
    ):
        print(f"skip line-fix → line-by-line へ: {chunk_name} ({n} 行)")
        return False, "", last_err

    bad_assistant = (last_raw or "").strip()
    if len(bad_assistant) > 14000:
        bad_assistant = bad_assistant[:14000] + "\n...(truncated)"

    for fix_i in range(1, line_fix_retries + 1):
        if output_json:
            obj = extract_json_object(bad_assistant)
            ta = obj.get("translations") if obj else None
            prev_n = len(ta) if isinstance(ta, list) else 0
            fix_user = (
                "【JSON 修正】翻訳プロンプトの規則はそのまま。応答は **有効な JSON オブジェクト 1 つだけ**。"
                ' 形: {"translations":["和訳1","和訳2",...]} 。'
                f'"translations" は長さちょうど {n} の文字列配列。'
                f"いまの出力は要素数 {prev_n} でした。要素数を {n} に直す。"
                "各文字列に改行を含めない。JSON の外に説明文を書かない。\n\n"
                f"入力（再掲）:\n{numbered_src}"
            )
        else:
            prev_n = len(nonempty_lines(strip_wrapping(bad_assistant))) if bad_assistant else 0
            fix_user = (
                "【行数修正】翻訳プロンプトの規則はそのまま適用してください。\n"
                "人名の列挙・巻次見出し・譜系の短い行も、必ず1入力行につき1和訳行。複数行を1和訳にまとめない。\n"
                f"入力は合計 {n} 行です。直前のあなたの和訳は {prev_n} 行でした。\n"
                f"出力は【{n} 行ちょうど】にしてください。入力行と出力行は 1 対 1。"
                "行の結合・分割・空行の挿入は禁止です。行番号は出力に含めないでください。\n\n"
                f"入力（再掲）:\n{numbered_src}"
            )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_initial},
            {"role": "assistant", "content": bad_assistant or "（空）"},
            {"role": "user", "content": fix_user},
        ]
        try:
            last_raw = call_deepseek_messages(
                api_key,
                model,
                messages,
                fix_temperature,
                timeout_sec=timeout_sec,
            )
            ok, err, out_lines = validate(n, last_raw)
            if ok:
                return True, "\n".join(out_lines) + "\n", ""
            last_err = err
            bad_assistant = last_raw.strip()
            if len(bad_assistant) > 14000:
                bad_assistant = bad_assistant[:14000] + "\n...(truncated)"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        if fix_i < line_fix_retries:
            wait_sec = retry_base_sec * (2 ** (fix_i - 1))
            print(
                f"line-fix: {chunk_name} fix={fix_i}/{line_fix_retries} "
                f"wait={wait_sec:.1f}s err={last_err}"
            )
            time.sleep(wait_sec)

    return False, "", last_err


def translate_chunk_line_by_line(
    *,
    chunk_name: str,
    api_key: str,
    model: str,
    system_prompt: str,
    src_lines: list[str],
    fix_temperature: float,
    timeout_sec: float,
    sleep_sec: float,
    per_line_retries: int = 4,
    retry_base_sec: float = 1.2,
) -> tuple[bool, str, str]:
    """
    チャンク全体が行数不一致で通らないときの最終手段：1入力行につき API 1回（JSON 要素1つ）。
    """
    total = len(src_lines)
    if total == 0:
        return False, "", "入力行がありません。"
    out: list[str] = []
    for idx, line in enumerate(src_lines):
        numbered = f"001|{line}"
        user_text = (
            f"【チャンク内 {idx + 1}/{total} 行目・この1行のみ】"
            "翻訳プロンプトの規則に従い、上記の漢文1行だけを和訳する。"
            ' 応答は有効な JSON オブジェクト 1 つのみ: {"translations":["和訳1つ"]}。'
            ' "translations" は長さちょうど 1 の文字列配列。和訳に改行を含めない。\n\n'
            f"{numbered}"
        )
        ok_line = False
        last_err = ""
        for attempt in range(1, per_line_retries + 1):
            try:
                raw = call_deepseek_messages(
                    api_key,
                    model,
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text},
                    ],
                    fix_temperature,
                    timeout_sec=timeout_sec,
                )
                vo, err, rows = validate_json_translations(1, raw)
                if vo and rows:
                    out.append(rows[0])
                    ok_line = True
                    break
                last_err = err
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
            if attempt < per_line_retries:
                time.sleep(retry_base_sec * (2 ** (attempt - 1)))
        if not ok_line:
            return False, "", f"line-by-line 失敗 {chunk_name} 行{idx + 1}/{total}: {last_err}"
        print(f"  line-by-line: {chunk_name} {idx + 1}/{total} OK")
        time.sleep(sleep_sec)
    return True, "\n".join(out) + "\n", ""


def main():
    parser = argparse.ArgumentParser(description="Deepseek APIで金史チャンク翻訳")
    parser.add_argument("vol", help="巻番号（例: 1, 135, 43上, 巻1）")
    parser.add_argument("--base-dir", default=r"E:\マイドライブ\史書\金史", help="プロジェクトルート")
    parser.add_argument("--chunk-root", default="temp_chunks_deepseek", help="チャンク親フォルダ")
    parser.add_argument("--model", default="deepseek-chat", help="Deepseekモデル名")
    parser.add_argument("--temperature", type=float, default=0.2, help="生成温度")
    parser.add_argument("--sleep-sec", type=float, default=0.6, help="API呼び出し間隔")
    parser.add_argument("--max-retries", type=int, default=5, help="通常翻訳の最大リトライ回数")
    parser.add_argument("--retry-base-sec", type=float, default=1.5, help="リトライ待機の基準秒")
    parser.add_argument(
        "--line-fix-retries",
        type=int,
        default=5,
        help="行数不一致時のマルチターン修正の試行回数",
    )
    parser.add_argument(
        "--fix-temperature",
        type=float,
        default=0.05,
        help="行数修正フェーズの生成温度（低め推奨）",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=240.0,
        help="API 1 回あたりのタイムアウト秒",
    )
    parser.add_argument("--overwrite", action="store_true", help="既存翻訳チャンクを上書き")
    parser.add_argument(
        "--prompt-file",
        default=r"E:\マイドライブ\史書\金史\翻訳プロンプト2.txt",
        help="翻訳指示ファイル",
    )
    parser.add_argument(
        "--no-wayaku-save",
        action="store_true",
        help="和訳/巻<vol>.txt への保存を無効化（通常は指定不要）",
    )
    parser.add_argument(
        "--output-format",
        choices=("json", "lines"),
        default="json",
        help="json: {\"translations\":[...]} で返させる（短い見出し行の結合ミス対策）。lines: 改行区切り。",
    )
    parser.add_argument(
        "--no-line-fallback",
        action="store_true",
        help="チャンク全体が失敗したとき、1行ずつAPIで直さない（既定はフォールバックする）",
    )
    parser.add_argument(
        "--line-first",
        action="store_true",
        help="バッチを使わず、すべてのチャンクを初めから1行ずつ翻訳（API回数は増えるが確実）",
    )
    args = parser.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("環境変数 DEEPSEEK_API_KEY が未設定です。")

    vol_suffix = normalize_vol(args.vol)
    vol_dir = os.path.join(args.base_dir, args.chunk_root, vol_suffix)
    trans_dir = os.path.join(vol_dir, "translated")
    if not os.path.isdir(vol_dir):
        raise FileNotFoundError(f"チャンクフォルダが見つかりません: {vol_dir}")
    os.makedirs(trans_dir, exist_ok=True)
    progress_path = build_progress_path(vol_dir)

    system_prompt = read_text(args.prompt_file)
    chunks = list_chunk_files(vol_dir)
    if not chunks:
        raise FileNotFoundError(f"chunk_*.txt が見つかりません: {vol_dir}")

    progress = load_progress(progress_path)
    progress["status"] = "running"
    progress["total_chunks"] = len(chunks)
    normalize_done_from_existing(progress, trans_dir)
    save_progress(progress_path, progress)

    done = 0
    skip = 0
    wayaku_path = build_wayaku_path(args.base_dir, vol_suffix)
    for name in chunks:
        src_path = os.path.join(vol_dir, name)
        out_path = os.path.join(trans_dir, name)
        if os.path.exists(out_path) and not args.overwrite:
            skip += 1
            continue

        src_text = read_text(src_path)
        src_lines = nonempty_lines(src_text)
        numbered_src = to_numbered_text(src_lines)
        listing_note = (
            "【列挙・見出し行】人名を全角空白で並べただけの行、金史/巻次/本紀・志・表・列傳の見出し、"
            "『從子:』『曾孫:』のような譜系の短い行も、いずれも1入力行につき必ず1和訳要素。"
            "複数入力行を1つの和訳にまとめない。1入力行を複数要素に割かない。"
            "1行の列挙は『○○、△△、□□（人名。初出にルビ）』のように1要素に収める。"
            "隣接する入力行が同じ語句（例：臣、瑨）で始まっても、譜系の名簿行と本文の続きは別行なので"
            "必ず translations の別要素に分け、1つに統合しない。\n\n"
        )
        nlines = len(src_lines)
        if args.output_format == "json":
            json_instr = (
                "\n\n【出力形式・必須】応答は **有効な JSON オブジェクト 1 つだけ**（前後に説明文・前置き・「以下に…」や ``` を付けない。先頭文字は `{`）。"
                ' キーは "translations" のみ。値は長さちょうど '
                f"{nlines} の文字列の配列。"
                " translations[i] は入力行 (i+1)（001 なら i=0）の和訳。"
                " 各文字列に改行を入れない。"
                " 表題・巻次・短い見出しも、入力行ごとに配列の別要素に分ける。"
                " 先頭が似た行が続いても要素数は減らさない。\n"
                ' 例: {"translations":["第一行の和訳","第二行の和訳"]}'
            )
            user_text = (
                listing_note
                + "以下は漢文の分割チャンク（行番号付き）。翻訳プロンプトの規則に従い各入力行を和訳してください。\n\n"
                + numbered_src
                + json_instr
            )
        else:
            user_text = (
                listing_note
                + "以下は漢文の分割チャンクです（行番号付き）。"
                "必ず翻訳プロンプトの規則を守り、1行につき1行で対応させてください。"
                "行の欠落・統合・分割は禁止です。"
                "出力には行番号を含めないでください。"
                f"出力行数は必ず {nlines} 行にしてください（この数より多くても少なくても不可）。\n\n"
                + numbered_src
            )
        if args.line_first and args.output_format == "json":
            print(f"line-first: {name} ({len(src_lines)} API calls)")
            ok, translated, last_err = translate_chunk_line_by_line(
                chunk_name=name,
                api_key=api_key,
                model=args.model,
                system_prompt=system_prompt,
                src_lines=src_lines,
                fix_temperature=args.fix_temperature,
                timeout_sec=args.timeout_sec,
                sleep_sec=args.sleep_sec,
            )
        else:
            ok, translated, last_err = translate_chunk(
                chunk_name=name,
                api_key=api_key,
                model=args.model,
                system_prompt=system_prompt,
                src_lines=src_lines,
                user_initial=user_text,
                numbered_src=numbered_src,
                temperature=args.temperature,
                max_retries=args.max_retries,
                retry_base_sec=args.retry_base_sec,
                line_fix_retries=args.line_fix_retries,
                fix_temperature=args.fix_temperature,
                timeout_sec=args.timeout_sec,
                output_json=args.output_format == "json",
            )

            if (
                not ok
                and args.output_format == "json"
                and not args.no_line_fallback
                and len(src_lines) > 0
            ):
                print(f"line-by-line fallback: {name} ({len(src_lines)} API calls)")
                ok, translated, last_err = translate_chunk_line_by_line(
                    chunk_name=name,
                    api_key=api_key,
                    model=args.model,
                    system_prompt=system_prompt,
                    src_lines=src_lines,
                    fix_temperature=args.fix_temperature,
                    timeout_sec=args.timeout_sec,
                    sleep_sec=args.sleep_sec,
                )

        if not ok:
            mark_failed(progress, name)
            progress["last_error"] = f"{name}: {last_err}"
            progress["status"] = "running"
            save_progress(progress_path, progress)
            append_failed_chunk_log(vol_dir, name, last_err)
            print(f"failed: {name} error={last_err}")
            continue

        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(translated)
        done += 1
        unmark_failed(progress, name)
        done_set = set(progress.get("done_chunks", []))
        done_set.add(name)
        progress["done_chunks"] = sorted(done_set)
        progress["last_success_chunk"] = name
        progress["last_error"] = ""
        progress["status"] = "running"
        save_progress(progress_path, progress)

        if not args.no_wayaku_save:
            merged = merge_translated_chunks(trans_dir, wayaku_path)
            print(f"wayaku updated: {merged} chunks -> {wayaku_path}")
        print(f"translated: {name}")
        time.sleep(args.sleep_sec)

    print(f"完了: translated={done}, skipped={skip}")
    print(f"保存先: {trans_dir}")
    if not args.no_wayaku_save:
        merged = merge_translated_chunks(trans_dir, wayaku_path)
        print(f"和訳保存完了: {wayaku_path} (chunks={merged})")
    progress = load_progress(progress_path)
    progress["status"] = "completed" if not progress.get("failed_chunks") else "completed_with_errors"
    save_progress(progress_path, progress)


if __name__ == "__main__":
    main()
