"""
飞书机器人推送模块 —— 通过 Webhook 发送卡片消息。
每篇论文以独立消息发送，包含完整翻译、镜像链接和深度摘要。
"""

import argparse
import json
import os
import sys
import yaml
import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INPUT_FILE = os.path.join(DATA_DIR, "today_summaries.json")

# 飞书单条消息长度上限约为 30KB，这里保守控制在 20000 字符以内
MAX_CONTENT_LENGTH = 18000


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_single_paper_card(paper: dict, index: int, total: int, domain: str, date: str) -> dict:
    """为单篇论文构建一张飞书卡片消息。"""
    title_cn = paper.get("title_cn") or paper.get("title", "未知标题")
    title_en = paper.get("title", "")
    score = paper.get("score", "?")
    subfield = paper.get("subfield_label", "")
    priority = "⭐ " if paper.get("priority") else ""
    arxiv_url = paper.get("url", "")
    arxiv_id = paper.get("arxiv_id", "")
    abstract_cn = paper.get("abstract_cn", "")
    summary = paper.get("structured_summary", "")

    # 镜像链接
    mirror_urls = paper.get("mirror_urls", {})
    mirror_lines = []
    for name, url in mirror_urls.items():
        mirror_lines.append(f"[{name}镜像]({url})")
    mirror_text = " | ".join(mirror_lines) if mirror_lines else ""

    # 构建正文内容
    lines = [
        f"{priority}**{title_cn}**",
        f"*{title_en[:200]}{'...' if len(title_en) > 200 else ''}*",
        "",
        f"📂 {subfield} | 📊 相关性: {score}/10",
        f"🔗 [arXiv 原文]({arxiv_url})",
    ]
    if mirror_text:
        lines.append(f"🌐 {mirror_text}")

    # 中文摘要
    if abstract_cn:
        # 截断过长的中文摘要
        ab = abstract_cn
        if len(ab) > 1500:
            ab = ab[:1500] + "...（原文较长，完整版见邮件或 Pages）"
        lines.append("")
        lines.append("📝 **中文摘要**")
        lines.append(ab)

    # 结构化摘要（截断过长的）
    if summary:
        if len(summary) > 8000:
            summary = summary[:8000] + "\n\n...（完整版见邮件或 GitHub Pages）"
        lines.append("")
        lines.append("---")
        lines.append(summary)

    content = "\n".join(lines)
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n\n...（内容过长已截断，完整版见邮件或 GitHub Pages）"

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📄 {domain} ({date}) [{index}/{total}]",
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content},
                }
            ],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="飞书机器人推送")
    parser.add_argument("--input", default=INPUT_FILE, help="摘要 JSON 文件路径")
    args = parser.parse_args()

    webhook_url = os.environ.get("FEISHU_WEBHOOK", "")
    if not webhook_url:
        sys.exit("[ERROR] 未设置 FEISHU_WEBHOOK 环境变量")

    if not os.path.exists(args.input):
        sys.exit(f"[ERROR] 输入文件不存在: {args.input}")

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    papers = data.get("papers", [])
    if not papers:
        print("[INFO] 没有论文需要推送，跳过。")
        return

    settings = load_config()
    domain = settings.get("active_domain", "论文速递")
    date = data.get("date", "")

    total = len(papers)
    success = 0
    for i, paper in enumerate(papers):
        card = build_single_paper_card(paper, i + 1, total, domain, date)
        try:
            resp = requests.post(webhook_url, json=card, timeout=15)
            result = resp.json()
            if result.get("code") == 0:
                print(f"[INFO] 飞书推送成功 [{i+1}/{total}]: {paper.get('title_cn') or paper.get('title','?')[:40]}")
                success += 1
            else:
                print(f"[ERROR] 飞书推送失败 [{i+1}/{total}]: {result}")
        except Exception as e:
            print(f"[ERROR] 飞书推送异常 [{i+1}/{total}]: {e}")

        # 避免飞书限频
        if i < total - 1:
            import time as t
            t.sleep(0.5)

    print(f"[INFO] 飞书推送完成: {success}/{total} 成功")


if __name__ == "__main__":
    main()
