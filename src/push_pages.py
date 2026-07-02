"""
GitHub Pages 静态归档模块 —— 生成可浏览历史的精美网页。

每天运行后将摘要追加到 gh-pages 分支的 JSON 和 HTML 中，
通过 GitHub Actions 自动部署。
"""

import argparse
import json
import os
import re
import sys
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INPUT_FILE = os.path.join(DATA_DIR, "today_summaries.json")
PAGES_DIR = os.path.join(PROJECT_ROOT, "pages_output")


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_pages_dir():
    os.makedirs(PAGES_DIR, exist_ok=True)
    os.makedirs(os.path.join(PAGES_DIR, "data"), exist_ok=True)


def load_history() -> list[dict]:
    history_file = os.path.join(PAGES_DIR, "data", "history.json")
    if os.path.exists(history_file):
        with open(history_file, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history: list[dict]):
    history_file = os.path.join(PAGES_DIR, "data", "history.json")
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def format_summary_for_html(text: str) -> str:
    """将清洗后的摘要文本转为排版良好的 HTML。"""
    if not text:
        return ""

    lines = text.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append('<div class="spacer"></div>')
            continue

        # 【小节标题】
        if stripped.startswith("【") and "】" in stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            title_match = re.match(r"【(.+?)】(.*)", stripped)
            if title_match:
                section_name = title_match.group(1)
                rest = title_match.group(2).strip()
                html_parts.append(f'<div class="section-title">{section_name}</div>')
                if rest:
                    html_parts.append(f"<p>{rest}</p>")
            else:
                html_parts.append(f'<p><strong class="highlight">{stripped}</strong></p>')
            continue

        # 列表项
        if stripped.startswith("• "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{stripped[2:]}</li>")
            continue

        # 数字列表
        if re.match(r"^\d+[.\、)]\s", stripped):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<p class="num-item">{stripped}</p>')
            continue

        # 普通段落
        if in_list:
            html_parts.append("</ul>")
            in_list = False
        html_parts.append(f"<p>{stripped}</p>")

    if in_list:
        html_parts.append("</ul>")

    result = "\n".join(html_parts)
    result = re.sub(r'(<div class="spacer"></div>\s*)+', '<div class="spacer"></div>', result)
    # ▲text▲ → <strong>text</strong>
    result = re.sub(r"▲(.+?)▲", r"<strong>\1</strong>", result)
    return result


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", "PingFang SC",
                 "Hiragino Sans GB", "Noto Sans CJK SC", sans-serif;
    background: #f0f0f3; color: #2c2c2c; line-height: 1.75;
}
.header {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #a855f7 100%);
    color: #fff; padding: 48px 24px; text-align: center;
    box-shadow: 0 2px 12px rgba(79,70,229,0.2);
}
.header h1 { font-size: 26px; font-weight: 700; margin-bottom: 6px; }
.header p { opacity: 0.85; font-size: 14px; font-weight: 400; }
.container { max-width: 780px; margin: 0 auto; padding: 28px 18px; }
.day { margin-bottom: 36px; }
.day > h2 {
    font-size: 19px; font-weight: 700; color: #4f46e5;
    border-bottom: 2.5px solid #e0e0e8; padding-bottom: 8px; margin-bottom: 18px;
}
.count { font-size: 13px; color: #999; font-weight: 400; }

.paper {
    background: #fff; border-radius: 12px; padding: 26px 24px;
    margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    border: 1px solid #e8e8ed;
}
.paper.priority {
    background: #fffef7; border-color: #fbbf24; border-left: 4px solid #f59e0b;
}
.paper > h3 { font-size: 16.5px; font-weight: 700; color: #1a1a2e; margin-bottom: 3px; }
.title-en { font-size: 12px; color: #aaa; font-style: italic; margin-bottom: 12px; }

.meta { font-size: 12.5px; color: #999; margin-bottom: 14px; display: flex; flex-wrap: wrap; gap: 4px 12px; }
.meta span { margin-right: 4px; }
.meta a { color: #4f46e5; text-decoration: none; font-weight: 500; }

.mirror-links {
    font-size: 12px; color: #888; margin-bottom: 16px;
    padding: 7px 12px; background: #f0f9ff; border-radius: 6px;
}
.mirror-links a { color: #d97706; margin: 0 5px; font-weight: 500; }

.block-title {
    font-size: 15px; font-weight: 700; color: #4f46e5;
    margin: 20px 0 8px 0; padding-bottom: 5px;
    border-bottom: 1.5px solid #e8e8ed;
}
.abstract-cn {
    font-size: 14.5px; line-height: 1.95; color: #3d3d4d;
    padding: 16px 18px; background: #f5f3ff; border-radius: 10px;
    margin-bottom: 6px;
}
.summary { font-size: 14.5px; line-height: 1.9; color: #333; }
.summary p { margin-bottom: 10px; }
.summary ul { margin: 6px 0 12px 0; padding-left: 20px; }
.summary li { margin-bottom: 5px; list-style-type: disc; }
.summary .spacer { height: 10px; }
.summary .section-title {
    font-size: 14px; font-weight: 700; color: #1a1a2e;
    background: #f1f5f9; padding: 5px 10px; border-radius: 5px;
    margin: 14px 0 6px 0; display: inline-block;
}
.summary .num-item { padding-left: 6px; margin-bottom: 6px; }
.summary strong { color: #4f46e5; font-weight: 700; }

.footer { text-align: center; color: #bbb; font-size: 11px; padding: 36px 0 20px; }
@media (max-width: 600px) {
    .container { padding: 14px; }
    .paper { padding: 16px; }
    .header { padding: 32px 16px; }
}
"""


def generate_index_html(history: list[dict], domain: str) -> str:
    sorted_history = sorted(history, key=lambda x: x.get("date", ""), reverse=True)

    entries_html = []
    for entry in sorted_history:
        date = entry.get("date", "")
        papers = entry.get("papers", [])
        papers_parts = []

        for p in papers:
            title_cn = p.get("title_cn") or p.get("title", "未知标题")
            title_en = p.get("title", "")
            score = p.get("score", "?")
            subfield = p.get("subfield_label", "")
            priority_star = "⭐ " if p.get("priority") else ""
            priority_class = ' class="priority"' if p.get("priority") else ""
            url = p.get("url", "")
            arxiv_id = p.get("arxiv_id", "")
            abstract_cn = p.get("abstract_cn", "")
            summary = p.get("structured_summary", "")
            mirror_urls = p.get("mirror_urls", {})

            mirror_html = "".join(
                f'<a href="{u}" target="_blank">🌐 {n}</a> ' for n, u in mirror_urls.items()
            )

            summary_html = format_summary_for_html(summary) if summary else ""

            papers_parts.append(f"""
<div class="paper{priority_class}">
<h3>{priority_star}{title_cn}</h3>
<div class="title-en">{title_en}</div>
<div class="meta">
<span>📂 {subfield}</span>
<span>📊 相关性 {score}/10</span>
<a href="{url}" target="_blank">arXiv: {arxiv_id}</a>
{mirror_html}
</div>
{('<div class="mirror-links">🔰 国内可访问：' + mirror_html + '</div>') if mirror_html else ''}
{('<div class="block-title">📝 中文摘要（完整翻译）</div><div class="abstract-cn">' + abstract_cn + '</div>') if abstract_cn else ''}
{('<div class="block-title">🔍 深度解读</div><div class="summary">' + summary_html + '</div>') if summary_html else ''}
</div>""")

        entries_html.append(f"""
<section class="day">
<h2>📅 {date} <span class="count">({len(papers)} 篇)</span></h2>
{"".join(papers_parts)}
</section>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{domain} · 论文速递</title>
<style>{CSS}</style>
</head>
<body>
<div class="header"><h1>📄 {domain} 论文速递</h1><p>每日自动推送 · 由 paper-digest-agent 驱动</p></div>
<div class="container">{"".join(entries_html)}</div>
<div class="footer"><p>由 paper-digest-agent 自动生成 · 数据来源 arXiv · Powered by DeepSeek</p></div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="生成 GitHub Pages 静态页")
    parser.add_argument("--input", default=INPUT_FILE, help="摘要 JSON 文件路径")
    parser.add_argument("--output-dir", default=PAGES_DIR, help="Pages 输出目录")
    args = parser.parse_args()

    ensure_pages_dir()

    settings = load_config()
    domain = settings.get("active_domain", "论文速递")

    if not os.path.exists(args.input):
        print(f"[INFO] 输入文件不存在: {args.input}，跳过 Pages 生成。")
        return

    with open(args.input, encoding="utf-8") as f:
        today_data = json.load(f)

    papers = today_data.get("papers", [])
    if not papers:
        print("[INFO] 今天没有论文，跳过 Pages 更新。")
        return

    history = load_history()
    today_date = today_data.get("date", "")

    existing_idx = next((i for i, h in enumerate(history) if h.get("date") == today_date), None)
    if existing_idx is not None:
        history[existing_idx] = today_data
    else:
        history.append(today_data)

    save_history(history)

    html = generate_index_html(history, domain)
    index_path = os.path.join(args.output_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[INFO] Pages 生成成功: {index_path}")
    print(f"[INFO] 历史共 {len(history)} 天记录")


if __name__ == "__main__":
    main()
