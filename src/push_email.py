"""
邮件推送模块 —— 通过 SMTP 发送 HTML 格式邮件。
"""

import argparse
import json
import os
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
    """构建 HTML 邮件正文。"""
    parts = [
        f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; max-width: 720px; margin: 0 auto; padding: 20px; color: #333; }}
.header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; border-radius: 12px; margin-bottom: 24px; }}
.header h1 {{ margin: 0 0 4px 0; font-size: 22px; }}
.header p {{ margin: 0; opacity: 0.85; font-size: 14px; }}
.paper {{ border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; margin-bottom: 16px; }}
.paper h2 {{ margin: 0 0 8px 0; font-size: 17px; color: #1a1a2e; }}
.meta {{ font-size: 13px; color: #888; margin-bottom: 12px; }}
.meta span {{ margin-right: 12px; }}
.priority {{ background: #fff3cd; border-color: #ffc107; }}
.summary {{ font-size: 14px; line-height: 1.7; white-space: pre-wrap; }}
.summary strong {{ color: #333; }}
.footer {{ text-align: center; color: #aaa; font-size: 12px; margin-top: 32px; }}
a {{ color: #667eea; }}
</style></head><body>
<div class="header"><h1>📄 {domain} 论文日报</h1><p>{date}</p></div>"""
    ]

    for p in papers:
        title_cn = p.get("title_cn") or p.get("title", "未知标题")
        score = p.get("score", "?")
        subfield = p.get("subfield_label", "")
        priority_class = ' class="priority"' if p.get("priority") else ""
        url = p.get("url", "")
        summary = p.get("structured_summary", "")

        # 把摘要里的【】转为粗体
        import re
        summary_html = re.sub(r"【(.+?)】", r"<br><strong>【\1】</strong>", summary)
        summary_html = summary_html.replace("\n", "<br>")

        parts.append(f"""<div class="paper"{priority_class}>
<h2>{'⭐ ' if p.get('priority') else ''}{title_cn}</h2>
<div class="meta"><span>📂 {subfield}</span><span>📊 相关性: {score}/10</span><span><a href="{url}">原文链接</a></span></div>
<div class="summary">{summary_html}</div>
</div>""")

    parts.append(f"""<div class="footer">
<p>由 paper-digest-agent 自动生成 | {date}</p>
<p><a href="https://github.com">GitHub 仓库</a></p>
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
        # 不 exit(1)，邮件失败不应阻断整个 pipeline


if __name__ == "__main__":
    main()
