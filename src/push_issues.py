"""
GitHub Issues 推送模块 —— 零密钥配置的展示渠道。

使用 gh CLI 在仓库中创建 Issue，Actions 运行环境自带 GITHUB_TOKEN 权限。
别人 fork/template 之后，只需在 push_channels 中加入 "issues" 即可开箱即用。
"""

import argparse
import json
import os
import subprocess
import sys
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INPUT_FILE = os.path.join(DATA_DIR, "today_summaries.json")


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_issue_body(papers: list[dict], date: str) -> str:
    """构建 Issue 正文（Markdown 格式）。"""
    lines = [f"# 📄 论文日报 ({date})\n"]

    for i, p in enumerate(papers):
        title_cn = p.get("title_cn") or p.get("title", "未知标题")
        title_en = p.get("title", "")
        score = p.get("score", "?")
        subfield = p.get("subfield_label", "")
        priority = "⭐ " if p.get("priority") else ""
        url = p.get("url", "")
        summary = p.get("structured_summary", "")
        abstract_cn = p.get("abstract_cn", "")
        arxiv_id = p.get("arxiv_id", "")

        lines.append(f"## {i+1}. {priority}{title_cn}\n")
        lines.append(f"**{title_en}**\n")
        lines.append(f"- 📂 子方向: {subfield}")
        lines.append(f"- 📊 相关性: {score}/10")
        lines.append(f"- 🔗 [arXiv: {arxiv_id}]({url})\n")

        if abstract_cn:
            lines.append(f"### 中文摘要\n{abstract_cn}\n")

        if summary:
            lines.append(f"### 深度解读\n{summary}\n")

        lines.append("---\n")

    lines.append(f"\n> 由 paper-digest-agent 自动生成 · {date}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="GitHub Issues 推送")
    parser.add_argument("--input", default=INPUT_FILE, help="摘要 JSON 文件路径")
    parser.add_argument("--repo", help="仓库名 (owner/repo)，默认从 GITHUB_REPOSITORY 读取")
    args = parser.parse_args()

    repo = args.repo or os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        sys.exit("[ERROR] 无法确定仓库名，请通过 --repo 或 GITHUB_REPOSITORY 环境变量指定")

    if not os.path.exists(args.input):
        sys.exit(f"[ERROR] 输入文件不存在: {args.input}")

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    papers = data.get("papers", [])
    if not papers:
        print("[INFO] 没有论文需要推送，跳过。")
        return

    date = data.get("date", "")
    domain = data.get("domain", "论文速递")
    title = f"{domain} 日报 ({date})"
    body = build_issue_body(papers, date)

    try:
        result = subprocess.run(
            [
                "gh", "issue", "create",
                "--repo", repo,
                "--title", title,
                "--body", body,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        print(f"[INFO] Issue 创建成功: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Issue 创建失败: {e.stderr}")
        # 不 exit(1)，Issue 失败不应阻断整个 pipeline
    except FileNotFoundError:
        print("[WARN] 未找到 gh CLI，跳过 Issues 推送。")


if __name__ == "__main__":
    main()
