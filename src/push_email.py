"""
邮件推送模块 —— 通过 SMTP 发送 HTML 格式邮件。
包含完整中文翻译、镜像链接和深度结构化摘要。
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
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INPUT_FILE = os.path.join(DATA_DIR, "today_summaries.json")


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_html(papers: list[dict], domain: str, date: str) -> str:
    """构建 HTML 邮件正文，包含完整翻译、镜像链接和结构化摘要。"""
    parts = [
        f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, 'Microsoft YaHei', 'PingFang SC', sans-serif; max-width: 750px; margin: 0 auto; padding: 20px; color: #333; }}
.header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 28px; border-radius: 14px; margin-bottom: 24px; }}
.header h1 {{ margin: 0 0 4px 0; font-size: 22px; }}
.header p {{ margin: 0; opacity: 0.85; font-size: 14px; }}
.paper {{ border: 1px solid #e0e0e0; border-radius: 12px; padding: 24px; margin-bottom: 20px; background: #fff; }}
.paper.priority {{ background: #fffdf5; border-color: #ffc107; border-left: 4px solid #ffc107; }}
.paper h2 {{ margin: 0 0 4px 0; font-size: 17px; color: #1a1a2e; }}
.paper .title-en {{ font-size: 13px; color: #999; margin-bottom: 12px; font-style: italic; }}
.meta {{ font-size: 13px; color: #888; margin-bottom: 14px; display: flex; flex-wrap: wrap; gap: 10px; }}
.meta span {{ margin-right: 8px; }}
.meta a {{ color: #667eea; text-decoration: none; }}
.mirror-links {{ font-size: 12px; color: #888; margin-bottom: 14px; }}
.mirror-links a {{ color: #e67e22; margin-right: 10px; }}
.section-title {{ font-size: 15px; font-weight: bold; color: #1a1a2e; margin: 18px 0 8px 0; padding-bottom: 4px; border-bottom: 1.5px solid #667eea; }}
.abstract-cn {{ font-size: 14px; line-height: 1.9; color: #444; padding: 12px; background: #f8f9ff; border-radius: 8px; margin-bottom: 8px; }}
.summary {{ font-size: 14px; line-height: 1.85; color: #333; }}
.summary strong {{ color: #1a1a2e; }}
.footer {{ text-align: center; color: #aaa; font-size: 12px; margin-top: 36px; }}
a {{ color: #667eea; }}
</style></head><body>
<div class="header"><h1>📄 {domain} 论文日报</h1><p>{date}</p></div>"""
    ]

    for p in papers:
        title_cn = p.get("title_cn") or p.get("title", "未知标题")
        title_en = p.get("title", "")
        score = p.get("score", "?")
        subfield = p.get("subfield_label", "")
        priority_class = ' class="priority"' if p.get("priority") else ""
        priority_star = "⭐ " if p.get("priority") else ""
        arxiv_url = p.get("url", "")
        arxiv_id = p.get("arxiv_id", "")
        abstract_cn = p.get("abstract_cn", "")
        summary = p.get("structured_summary", "")
        mirror_urls = p.get("mirror_urls", {})

        # 镜像链接
        mirror_links_html = ""
        for name, url in mirror_urls.items():
            mirror_links_html += f'<a href="{url}">🌐 {name}镜像</a>\n'

        # 结构化摘要格式化
        summary_html = re.sub(r"【(.+?)】", r"<br><strong>【\1】</strong>", summary)
        summary_html = summary_html.replace("\n", "<br>")

        parts.append(f"""<div class="paper"{priority_class}>
<h2>{priority_star}{title_cn}</h2>
<div class="title-en">{title_en}</div>
<div class="meta">
    <span>📂 {subfield}</span>
    <span>📊 相关性: {score}/10</span>
    <span>🔗 <a href="{arxiv_url}">arXiv: {arxiv_id}</a></span>
</div>""")

        if mirror_links_html:
            parts.append(f'<div class="mirror-links">国内可访问：{mirror_links_html}</div>')

        if abstract_cn:
            parts.append(f'<div class="section-title">📝 中文摘要（完整翻译）</div>')
            parts.append(f'<div class="abstract-cn">{abstract_cn}</div>')

        if summary_html:
            parts.append(f'<div class="section-title">🔍 深度解读</div>')
            parts.append(f'<div class="summary">{summary_html}</div>')

        parts.append("</div>")

    parts.append(f"""<div class="footer">
<p>由 paper-digest-agent 自动生成 | {date}</p>
<p>Powered by arXiv + DeepSeek | <a href="https://github.com/LR0625/paper-digest-agent">GitHub</a></p>
</div></body></html>""")

    return "\n".join(parts)


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
