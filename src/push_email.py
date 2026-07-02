"""
邮件推送模块 —— 通过 SMTP 发送 HTML 格式邮件。
包含完整中文翻译、镜像链接和深度结构化摘要。
排版针对中文阅读体验深度优化。
"""

import argparse
import json
import os
import re
import smtplib
import sys
import yaml
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INPUT_FILE = os.path.join(DATA_DIR, "today_summaries.json")


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def format_summary_for_html(text: str) -> str:
    """
    将清洗后的摘要文本转为排版良好的 HTML：
    - 【小节标题】→ 带样式的标题块
    - ▲text▲ → <strong>text</strong>
    - • 列表项 → 适当的缩进列表
    - 空行 → 段落间距
    """
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

        # 检测【小节标题】
        if stripped.startswith("【") and "】" in stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            # 提取标题文本
            title_match = re.match(r"【(.+?)】(.*)", stripped)
            if title_match:
                section_name = title_match.group(1)
                rest = title_match.group(2).strip()
                html_parts.append(f'<div class="section-title">{section_name}</div>')
                if rest:
                    html_parts.append(f'<p>{rest}</p>')
            else:
                html_parts.append(f'<p><strong class="highlight">{stripped}</strong></p>')
            continue

        # 列表项
        if stripped.startswith("• "):
            if not in_list:
                html_parts.append('<ul>')
                in_list = True
            html_parts.append(f"<li>{stripped[2:]}</li>")
            continue

        # 数字列表
        if re.match(r"^\d+[\.\、\)]\s", stripped):
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

    # 合并连续 spacer
    result = "\n".join(html_parts)
    result = re.sub(r'(<div class="spacer"></div>\s*)+', '<div class="spacer"></div>', result)
    # ▲text▲ → <strong>text</strong>
    result = re.sub(r"▲(.+?)▲", r"<strong>\1</strong>", result)
    return result


def build_html(papers: list[dict], domain: str, date: str) -> str:
    """构建 HTML 邮件正文。"""

    css = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", "PingFang SC",
                     "Hiragino Sans GB", "Noto Sans CJK SC", "WenQuanYi Micro Hei", sans-serif;
        max-width: 720px; margin: 0 auto; padding: 24px 16px;
        color: #2c2c2c; background: #f7f7f8; line-height: 1.75;
    }
    .header {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #a855f7 100%);
        color: #fff; padding: 32px 28px; border-radius: 16px; margin-bottom: 28px;
        box-shadow: 0 4px 16px rgba(79,70,229,0.25);
    }
    .header h1 { font-size: 22px; font-weight: 700; margin-bottom: 6px; letter-spacing: 0.02em; }
    .header .sub { font-size: 13px; opacity: 0.85; font-weight: 400; }

    .paper {
        background: #fff; border-radius: 14px; padding: 28px 26px;
        margin-bottom: 22px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        border: 1px solid #e8e8ed;
    }
    .paper.priority {
        background: #fffef9; border-color: #fbbf24;
        border-left: 4px solid #f59e0b;
    }
    .paper h2 {
        font-size: 17px; font-weight: 700; color: #1a1a2e;
        margin-bottom: 2px; line-height: 1.5;
    }
    .title-en {
        font-size: 12.5px; color: #a0a0b0; font-style: italic;
        margin-bottom: 14px; line-height: 1.5;
    }
    .meta {
        font-size: 13px; color: #888; margin-bottom: 16px;
        display: flex; flex-wrap: wrap; gap: 6px 14px;
    }
    .meta-item { display: inline-flex; align-items: center; gap: 3px; }
    .meta a { color: #4f46e5; text-decoration: none; font-weight: 500; }
    .meta a:hover { text-decoration: underline; }

    .mirror-links {
        font-size: 12px; color: #888; margin-bottom: 18px;
        padding: 8px 12px; background: #f0f9ff; border-radius: 6px;
        border: 1px solid #e0f2fe;
    }
    .mirror-links a { color: #d97706; margin: 0 6px; font-weight: 500; }

    .block-title {
        font-size: 15px; font-weight: 700; color: #4f46e5;
        margin: 22px 0 10px 0; padding-bottom: 6px;
        border-bottom: 2px solid #e8e8ed;
        letter-spacing: 0.03em;
    }
    .abstract-cn {
        font-size: 14.5px; line-height: 1.95; color: #3d3d4d;
        padding: 16px 18px; background: #f5f3ff; border-radius: 10px;
        margin-bottom: 6px;
    }
    .summary {
        font-size: 14.5px; line-height: 1.95; color: #333;
    }
    .summary p { margin-bottom: 10px; }
    .summary ul {
        margin: 6px 0 12px 0; padding-left: 20px;
    }
    .summary li {
        margin-bottom: 6px; list-style-type: disc;
    }
    .summary .spacer { height: 10px; }
    .summary .section-title {
        font-size: 14.5px; font-weight: 700; color: #1a1a2e;
        background: #f1f5f9; padding: 6px 12px; border-radius: 5px;
        margin: 16px 0 8px 0; display: inline-block;
    }
    .summary .num-item {
        padding-left: 8px; margin-bottom: 6px;
    }
    .summary strong { color: #4f46e5; font-weight: 700; }
    .summary .highlight { color: #1a1a2e; }

    .footer {
        text-align: center; color: #bbb; font-size: 11px;
        margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee;
    }
    .footer a { color: #999; }
    """

    papers_html = []
    for p in papers:
        title_cn = p.get("title_cn") or p.get("title", "未知标题")
        title_en = p.get("title", "")
        score = p.get("score", "?")
        subfield = p.get("subfield_label", "")
        pclass = ' class="priority"' if p.get("priority") else ""
        pstar = "⭐ " if p.get("priority") else ""
        arxiv_url = p.get("url", "")
        arxiv_id = p.get("arxiv_id", "")
        abstract_cn = p.get("abstract_cn", "")
        summary = p.get("structured_summary", "")
        mirror_urls = p.get("mirror_urls", {})

        mirror_html = ""
        for name, url in mirror_urls.items():
            mirror_html += f'<a href="{url}">🌐 {name}</a> '

        summary_html = format_summary_for_html(summary) if summary else ""

        papers_html.append(f"""
<div class="paper{pclass}">
<h2>{pstar}{title_cn}</h2>
<div class="title-en">{title_en}</div>
<div class="meta">
<span class="meta-item">📂 {subfield}</span>
<span class="meta-item">📊 相关性 {score}/10</span>
<span class="meta-item">🔗 <a href="{arxiv_url}">arXiv: {arxiv_id}</a></span>
</div>
{('<div class="mirror-links">🔰 国内可访问：' + mirror_html + '</div>') if mirror_html else ''}
{('<div class="block-title">📝 中文摘要（完整翻译）</div><div class="abstract-cn">' + abstract_cn + '</div>') if abstract_cn else ''}
{('<div class="block-title">🔍 深度解读</div><div class="summary">' + summary_html + '</div>') if summary_html else ''}
</div>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>{css}</style></head>
<body>
<div class="header"><h1>📄 {domain} 论文日报</h1><div class="sub">{date}</div></div>
{"".join(papers_html)}
<div class="footer">
<p>由 paper-digest-agent 自动生成 · {date}</p>
<p>Powered by arXiv + DeepSeek · <a href="https://github.com/LR0625/paper-digest-agent">GitHub</a></p>
</div>
</body></html>"""


def main():
    parser = argparse.ArgumentParser(description="邮件推送")
    parser.add_argument("--input", default=INPUT_FILE, help="摘要 JSON 文件路径")
    args = parser.parse_args()

    settings = load_config()
    email_cfg = settings.get("email", {})

    smtp_host = email_cfg.get("smtp_host", "") or os.environ.get("SMTP_HOST", "")
    smtp_port = email_cfg.get("smtp_port", 465)
    from_addr = email_cfg.get("from_addr", "") or os.environ.get("SMTP_FROM", "")
    to_addr = email_cfg.get("to_addr", "") or os.environ.get("SMTP_TO", "")
    password = os.environ.get("SMTP_PASSWORD", "")

    if not all([smtp_host, from_addr, to_addr, password]):
        print("[WARN] 邮件配置不完整，跳过推送。")
        print(f"  host={smtp_host}, from={from_addr}, to={to_addr}, password={'***' if password else 'MISSING'}")
        return

    if not os.path.exists(args.input):
        sys.exit(f"[ERROR] 输入文件不存在: {args.input}")

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    papers = data.get("papers", [])
    if not papers:
        print("[INFO] 没有论文需要推送，跳过。")
        return

    domain = data.get("domain", "论文速递")
    date = data.get("date", "")

    html = build_html(papers, domain, date)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{domain} 论文日报 ({date})"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.starttls()
        server.login(from_addr, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
        print(f"[INFO] 邮件推送成功 ({len(papers)} 篇)")
    except Exception as e:
        print(f"[ERROR] 邮件推送失败: {e}")


if __name__ == "__main__":
    main()
