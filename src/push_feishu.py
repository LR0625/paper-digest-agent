"""
飞书机器人推送模块 —— 通过 Webhook 发送卡片消息。
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


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_card(papers: list[dict], domain: str, date: str) -> dict:
    """构建飞书卡片消息。"""
    elements = []

    for p in papers:
        title_cn = p.get("title_cn") or p.get("title", "未知标题")
        score = p.get("score", "?")
        subfield = p.get("subfield_label", "")
        priority = "⭐ " if p.get("priority") else ""
        url = p.get("url", "")
        one_liner = ""

        # 尝试提取一句话简介
        summary = p.get("structured_summary", "")
        if "【一句话简介】" in summary:
            try:
                one_liner = summary.split("【一句话简介】")[1].split("【")[0].strip()
            except Exception:
                pass

        tag_line = f"{subfield} | 相关性: {score}/10" if subfield else f"相关性: {score}/10"

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"{priority}**{title_cn}**\n"
                    f"{one_liner}\n"
                    f"{tag_line}\n"
                    f"[原文链接]({url})"
                ),
            },
        })
        # 分隔线
        elements.append({"tag": "hr"})

    # 去掉末尾多余的分隔线
    if elements and elements[-1]["tag"] == "hr":
        elements.pop()

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{domain} 论文日报 ({date})",
                }
            },
            "elements": elements,
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

    card = build_card(papers, domain, data.get("date", ""))
    resp = requests.post(webhook_url, json=card, timeout=15)
    result = resp.json()
    if result.get("code") == 0:
        print(f"[INFO] 飞书推送成功 ({len(papers)} 篇)")
    else:
        print(f"[ERROR] 飞书推送失败: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
