"""
GitHub Pages 静态归档模块 —— 生成可浏览历史的网页。

每天运行后将摘要追加到 gh-pages 分支的 JSON 和 HTML 中，
通过 GitHub Actions 自动部署，形成可分享链接的网页归档。
"""

import argparse
import json
import os
import shutil
import sys
import yaml
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INPUT_FILE = os.path.join(DATA_DIR, "today_summaries.json")
PAGES_DIR = os.path.join(PROJECT_ROOT, "pages_output")


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_pages_dir():
    os.makedirs(PAGES_DIR, exist_ok=True)
    # 确保有 data 子目录存放历史 JSON
    os.makedirs(os.path.join(PAGES_DIR, "data"), exist_ok=True)


def load_history() -> list[dict]:
    """加载已有的历史数据。"""
    history_file = os.path.join(PAGES_DIR, "data", "history.json")
    if os.path.exists(history_file):
        with open(history_file, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history: list[dict]):
    history_file = os.path.join(PAGES_DIR, "data", "history.json")
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def generate_index_html(history: list[dict], domain: str) -> str:
    """生成首页 index.html —— 列出所有日期的摘要并展开展示。"""
    # 按日期倒序排列
    sorted_history = sorted(history, key=lambda x: x.get("date", ""), reverse=True)

    entries_html = []
    for entry in sorted_history:
        date = entry.get("date", "")
        papers = entry.get("papers", [])
        papers_html = []
        for p in papers:
            title_cn = p.get("title_cn") or p.get("title", "未知标题")
            title_en = p.get("title", "")
            score = p.get("score", "?")
            subfield = p.get("subfield_label", "")
            priority = ("⭐ " if p.get("priority") else "")
            url = p.get("url", "")
            summary = (p.get("structured_summary", "") or "").replace("\n", "<br>").replace("【", "<strong>【").replace("】", "】</strong>")
            abstract_cn = p.get("abstract_cn", "")
            mirror_urls = p.get("mirror_urls", {})
            mirror_html = "".join(f'<a href="{u}" target="_blank">🌐 {n}镜像</a> ' for n, u in mirror_urls.items())

            papers_html.append(f"""
            <div class="paper{(" priority" if p.get("priority") else "")}">
                <h3>{priority}{title_cn}</h3>
                <div class="title-en">{title_en}</div>
                <div class="meta">
                    <span>📂 {subfield}</span>
                    <span>📊 相关性: {score}/10</span>
                    <a href="{url}" target="_blank">arXiv 原文</a>
                    {mirror_html}
                </div>
                {('<div class="abstract-cn"><strong>📝 中文摘要（完整翻译）：</strong><br>' + abstract_cn + '</div>') if abstract_cn else ''}
                <div class="summary">{summary}</div>
            </div>""")

        entries_html.append(f"""
        <section class="day">
            <h2>📅 {date} <span class="count">({len(papers)} 篇)</span></h2>
            {''.join(papers_html)}
        </section>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{domain} · 论文速递</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, 'Microsoft YaHei', 'PingFang SC', sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
.header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 48px 24px; text-align: center; }}
.header h1 {{ font-size: 28px; margin-bottom: 8px; }}
.header p {{ opacity: 0.85; font-size: 15px; }}
.container {{ max-width: 800px; margin: 0 auto; padding: 24px 16px; }}
.day {{ margin-bottom: 32px; }}
.day h2 {{ font-size: 20px; border-bottom: 2px solid #667eea; padding-bottom: 8px; margin-bottom: 16px; }}
.count {{ font-size: 14px; color: #888; font-weight: normal; }}
.paper {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.paper.priority {{ border-left: 4px solid #ffc107; }}
.paper h3 {{ font-size: 16px; margin-bottom: 4px; color: #1a1a2e; }}
.title-en {{ font-size: 12px; color: #999; font-style: italic; margin-bottom: 8px; }}
.meta {{ font-size: 13px; color: #888; margin-bottom: 10px; }}
.meta span {{ margin-right: 12px; }}
.meta a {{ color: #667eea; }}
.abstract-cn {{ font-size: 14px; color: #555; margin-bottom: 10px; line-height: 1.7; }}
.summary {{ font-size: 14px; color: #444; line-height: 1.8; }}
.footer {{ text-align: center; color: #aaa; font-size: 12px; padding: 32px 0; }}
@media (max-width: 600px) {{ .container {{ padding: 12px; }} .paper {{ padding: 14px; }} }}
</style>
</head>
<body>
<div class="header"><h1>📄 {domain} 论文速递</h1><p>每日自动推送 · 由 paper-digest-agent 驱动</p></div>
<div class="container">{''.join(entries_html)}</div>
<div class="footer"><p>由 paper-digest-agent 自动生成 · 数据来源 arXiv</p></div>
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

    # 加载历史并追加今天的数据
    history = load_history()
    today_date = today_data.get("date", "")

    # 如果今天已有记录则替换，否则追加
    existing_idx = next((i for i, h in enumerate(history) if h.get("date") == today_date), None)
    if existing_idx is not None:
        history[existing_idx] = today_data
    else:
        history.append(today_data)

    save_history(history)

    # 生成 index.html
    html = generate_index_html(history, domain)
    index_path = os.path.join(args.output_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[INFO] Pages 生成成功: {index_path}")
    print(f"[INFO] 历史共 {len(history)} 天记录")


if __name__ == "__main__":
    main()
