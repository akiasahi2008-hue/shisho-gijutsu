import os
import re
import glob

# 設定
SOURCE_DIR = r"e:/マイドライブ/史書/金史/和訳"
OUTPUT_DIR = SOURCE_DIR
BOOK_NAME = "金史"

# プリセット辞書 (常用漢字外や歴史用語)
PRESET_DICT = {
    "阿骨打": "あくだ",
    "完顔": "わんやん",
    "靺鞨": "まっかつ",
    "契丹": "きったん",
    "渤海": "ぼっかい",
    "女直": "じょちょく",
    "顙": "ひたい",
    "僨": "たお",
    "輦": "てぐるま",
    "帟": "とばり",
    "犒": "ねぎら",
    "兀惹": "おつじゃ",
}

# 基本デザイン (CSS)
CSS = """
body {
    background-color: #c0a154;
    margin: 0;
    padding: 0;
    font-family: 'Hiragino Mincho ProN', 'MS PMincho', 'MS Mincho', serif;
}
.container {
    max-width: 900px;
    margin: 0 auto;
    padding: 50px;
    background-color: #fdfcf0;
    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    min-height: 100vh;
    font-weight: bold;
    line-height: 1.8;
    color: #222;
}
.breadcrumb {
    margin-bottom: 20px;
    font-weight: normal;
}
.breadcrumb a {
    color: #333;
    text-decoration: none;
}
.breadcrumb a:hover {
    text-decoration: underline;
}
h1 {
    text-align: center;
    color: #2c3e50;
    margin-bottom: 40px;
    border-bottom: 2px solid #c0a154;
    padding-bottom: 10px;
}
.category-title {
    background: #c0a154;
    color: white;
    padding: 5px 15px;
    margin-top: 30px;
    margin-bottom: 15px;
    font-weight: bold;
}
.index-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin-bottom: 30px;
}
.index-item {
    background: #e6d5a7;
    padding: 10px;
    text-align: center;
    border: 1px solid #c0a154;
    border-radius: 4px;
    text-decoration: none;
    color: #333;
    font-weight: bold;
    font-size: 0.9em;
}
.index-item:hover {
    background: #d4bc7d;
}
.index-item.disabled {
    background: #ccc;
    border-color: #999;
    color: #777;
    cursor: not-allowed;
    pointer-events: none;
}
p {
    margin: 0 0 1.2em 0;
}
.note {
    font-weight: bold;
}
ruby rt {
    font-weight: normal !important;
}
.navigation {
    display: flex;
    justify-content: space-between;
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #c0a154;
    font-weight: normal;
}
.navigation a {
    color: #333;
    text-decoration: none;
    padding: 8px 15px;
    background: #e6d5a7;
    border-radius: 4px;
    border: 1px solid #c0a154;
}
.navigation a:hover {
    background: #d4bc7d;
}
footer {
    margin-top: 50px;
    border-top: 1px solid #c0a154;
    padding-top: 20px;
    font-size: 0.9em;
    color: #666;
    text-align: center;
    font-weight: normal !important;
}
@media (max-width: 768px) {
    .container { padding: 20px; }
    .index-grid { grid-template-columns: repeat(2, 1fr); }
}
"""

def extract_rubi_map(text):
    """
    Pass 1: Extract Kanji(hiragana/katakana) and Aozora-style patterns.
    """
    rubi_map = PRESET_DICT.copy()
    
    # Pattern 1: 漢字（ひらがな・カタカナ）
    pattern1 = re.compile(r'([\u4E00-\u9FFF]+)（([\u3040-\u30FF]+)）')
    matches1 = pattern1.findall(text)
    for kanji, reading in matches1:
        rubi_map[kanji] = reading
        
    # Pattern 2: ｜?漢字《ひらがな・カタカナ》
    pattern2 = re.compile(r'[｜\|]?([\u4E00-\u9FFF]+)《([\u3040-\u30FF]+)》')
    matches2 = pattern2.findall(text)
    for kanji, reading in matches2:
        rubi_map[kanji] = reading
        
    return rubi_map

def apply_rubi(text, rubi_map):
    """
    Pass 2: Apply <ruby> to the first occurrence and handle bracketed notes.
    """
    processed_text = text
    
    # 0. 既存ボムや特殊文字のクリーンアップ
    processed_text = processed_text.replace('\ufeff', '')

    # 1. 既存の青空形式（《》）をルビタグに変換（最優先）
    processed_text = re.sub(r'[｜\|]([\u4E00-\u9FFF]+)《([\u3040-\u30FF]+)》', r'<ruby>\1<rt>\2</rt></ruby>', processed_text)
    processed_text = re.sub(r'([\u4E00-\u9FFF]+)《([\u3040-\u30FF]+)》', r'<ruby>\1<rt>\2</rt></ruby>', processed_text)

    # 2. 漢字を含む括弧書き（注釈）を保護
    notes = re.findall(r'（.*?[\u4E00-\u9FFF].*?）', processed_text)
    for i, note in enumerate(notes):
        processed_text = processed_text.replace(note, f'__NOTE_{i}__', 1)
    
    # 3. 漢字（かな） ペアを正規化（（かな）部分を削除）
    for kanji, reading in rubi_map.items():
        processed_text = processed_text.replace(f'{kanji}（{reading}）', kanji)
        
    # 4. 各漢字の「初出」にルビを付与（すでにタグ化されている場合は除く）
    for kanji, reading in rubi_map.items():
        if f'<ruby>{kanji}<rt>' in processed_text:
            continue
        # 境界を考慮せず、単純に最初に見つかった箇所を置換
        processed_text = re.sub(re.escape(kanji), f'<ruby>{kanji}<rt>{reading}</rt></ruby>', processed_text, count=1)

    # 5. プレースホルダーを装飾付き注釈に戻す
    for i, note in enumerate(notes):
        processed_text = processed_text.replace(f'__NOTE_{i}__', f'<b class="note">{note}</b>')
        
    return processed_text

def get_volume_title(lines):
    clean_lines = [l.strip() for l in lines if l.strip()]
    if len(clean_lines) >= 2:
        return clean_lines[1]
    elif len(clean_lines) >= 1:
        return clean_lines[0]
    return "無題"

def convert_file(file_path, prev_info, next_info):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    title = get_volume_title(lines)
    filename = os.path.basename(file_path).replace(".txt", ".html")
    
    content = "".join(lines)
    rubi_map = extract_rubi_map(content)
    processed_content = apply_rubi(content, rubi_map)
    
    html_lines = []
    for line in processed_content.splitlines():
        if line.strip():
            html_lines.append(f"<p>{line.strip()}</p>")
        else:
            html_lines.append("<p>&nbsp;</p>")
            
    html_body = "\n".join(html_lines)
    
    nav_html = '<div class="navigation">'
    if prev_info:
        nav_html += f'<a href="{prev_info["html"]}">&larr; {prev_info["label"]}</a>'
    else:
        nav_html += '<span></span>'
    nav_html += '<a href="index.html">目次</a>'
    if next_info:
        nav_html += f'<a href="{next_info["html"]}">{next_info["label"]} &rarr;</a>'
    else:
        nav_html += '<span></span>'
    nav_html += '</div>'
    
    full_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{BOOK_NAME} {title}</title>
    <style>{CSS}</style>
</head>
<body>
    <div class="container">
        <div class="breadcrumb"><a href="index.html">← 目次へ戻る</a></div>
        <h1>{BOOK_NAME} {title}</h1>
        {html_body}
        {nav_html}
        <footer>
            <p>※ 本資料はAIによる翻訳・要旨を含む試作版です。正確な内容は原文（{BOOK_NAME}）をご参照ください。</p>
        </footer>
    </div>
</body>
</html>"""

    output_path = os.path.join(OUTPUT_DIR, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Converted: {filename}")

def get_sorted_files():
    files = glob.glob(os.path.join(SOURCE_DIR, "巻*.txt"))
    def sort_key(f):
        m = re.search(r'巻(\d+)([上中下]?)', f)
        if m:
            num = int(m.group(1))
            suffix = m.group(2)
            suffix_val = {"上": 1, "中": 2, "下": 3, "": 0}[suffix]
            return (num, suffix_val)
        return (0, 0)
    files.sort(key=sort_key)
    return files

def generate_index():
    files = get_sorted_files()
    categories = [
        ("本紀", range(1, 20)),
        ("志", range(20, 59)),
        ("表", range(59, 63)),
        ("列傳", range(63, 136)),
    ]
    index_body = []
    for cat_name, v_range in categories:
        index_body.append(f'<div class="category-title">{cat_name}</div>')
        index_body.append('<div class="index-grid">')
        for i in v_range:
            found_any = False
            for suffix in ["", "上", "中", "下"]:
                num_str = f"{i}{suffix}"
                txt_name = f"巻{num_str}.txt"
                html_name = f"巻{num_str}.html"
                display_label = f"巻{i}{suffix}" if suffix else f"巻{i}"
                found = False
                for f in files:
                    if os.path.basename(f) == txt_name:
                        found = True
                        break
                if found:
                    index_body.append(f'<a class="index-item" href="{html_name}">{display_label}</a>')
                    found_any = True
            if not found_any:
                index_body.append(f'<span class="index-item disabled">巻{i}</span>')
        index_body.append('</div>')

    full_index = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{BOOK_NAME} 和訳 目次</title>
    <style>{CSS}</style>
</head>
<body>
    <div class="container">
        <h1>{BOOK_NAME} 和訳</h1>
        <p style="text-align:center; font-weight:normal;">AI和訳試作版</p>
        {"".join(index_body)}
        <footer>
            <p>※ 本資料はAIによる翻訳・要旨を含む試作版です。正確な内容は原文（{BOOK_NAME}）をご参照ください。</p>
        </footer>
    </div>
</body>
</html>"""
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(full_index)

if __name__ == "__main__":
    txt_files = get_sorted_files()
    for i, f in enumerate(txt_files):
        prev_info = None
        if i > 0:
            p_file = txt_files[i-1]
            p_label = os.path.basename(p_file).replace(".txt", "")
            prev_info = {"html": os.path.basename(p_file).replace(".txt", ".html"), "label": p_label}
        next_info = None
        if i < len(txt_files) - 1:
            n_file = txt_files[i+1]
            n_label = os.path.basename(n_file).replace(".txt", "")
            next_info = {"html": os.path.basename(n_file).replace(".txt", ".html"), "label": n_label}
        convert_file(f, prev_info, next_info)
    generate_index()
