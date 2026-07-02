"""
会议放榜专题推送 —— 半自动脚本。

到 CoRL/RSS/ICRA/CVPR 等放榜节点前，手动运行本脚本，
批量拉取录用列表，走同样的摘要+推送流程，作为"专题特刊"。

支持的会议列表在 config/settings.yaml 的 conferences 字段维护。
每个会议需要实现对应的解析函数。
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

import requests
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


# ========== 会议解析器注册表 ==========
# 每个解析器接受 conference 配置字典，返回论文列表


def fetch_openreview(conf: dict) -> list[dict]:
    """
    从 OpenReview API 获取录用论文列表。

    会议配置示例：
      - name: "CoRL 2025"
        source: "openreview"
        venue_id: "robot-learning.org/CoRL/2025/Conference"
    """
    venue_id = conf.get("venue_id", "")
    if not venue_id:
        print(f"[WARN] {conf['name']}: 缺少 venue_id")
        return []

    # OpenReview API v2
    url = "https://api2.openreview.net/notes"
    params = {
        "content.venueid": venue_id,
        "details": "replyCount",
        "limit": 100,
        "offset": 0,
    }

    papers = []
    try:
        # 可能有多页
        while True:
            resp = requests.get(url, params=params, timeout=30)
            data = resp.json()
            notes = data.get("notes", [])
            if not notes:
                break

            for note in notes:
                content = note.get("content", {})
                papers.append({
                    "arxiv_id": f"openreview-{note.get('id', '')}",
                    "title": content.get("title", {}).get("value", "未知标题"),
                    "authors": content.get("authors", {}).get("value", []),
                    "abstract": content.get("abstract", {}).get("value", ""),
                    "venue": conf["name"],
                    "url": f"https://openreview.net/forum?id={note.get('id', '')}",
                    "published": "",
                    "categories": [],
                })

            if len(notes) < params["limit"]:
                break
            params["offset"] += params["limit"]
            time.sleep(0.5)

    except Exception as e:
        print(f"[ERROR] OpenReview 抓取失败 ({conf['name']}): {e}")

    return papers


def fetch_dblp(conf: dict) -> list[dict]:
    """
    从 DBLP 获取会议论文列表（适用于传统 CS 会议如 ICRA, CVPR）。

    会议配置示例：
      - name: "ICRA 2025"
        source: "dblp"
        venue_key: "conf/icra/2025"
    """
    venue_key = conf.get("venue_key", "")
    if not venue_key:
        print(f"[WARN] {conf['name']}: 缺少 venue_key")
        return []

    url = f"https://dblp.org/search/publ/api?q=stream:streams%2F{venue_key}&format=json&h=1000"
    papers = []
    try:
        resp = requests.get(url, timeout=30)
        data = resp.json()
        hits = data.get("result", {}).get("hits", {}).get("hit", [])
        for hit in hits:
            info = hit.get("info", {})
            papers.append({
                "arxiv_id": f"dblp-{hit.get('@id', '')}",
                "title": info.get("title", "未知标题"),
                "authors": [],
                "abstract": "",
                "venue": conf["name"],
                "url": info.get("ee", info.get("url", "")),
                "published": str(info.get("year", "")),
                "categories": [],
            })
    except Exception as e:
        print(f"[ERROR] DBLP 抓取失败 ({conf['name']}): {e}")

    return papers


# 解析器映射
PARSERS = {
    "openreview": fetch_openreview,
    "dblp": fetch_dblp,
}


def run_conference(conf: dict) -> list[dict]:
    """运行单个会议的抓取。"""
    source = conf.get("source", "")
    parser = PARSERS.get(source)
    if not parser:
        print(f"[WARN] 不支持的数据源: {source} ({conf.get('name', '?')})")
        return []

    print(f"[INFO] 抓取会议: {conf.get('name', '?')} (源: {source})")
    papers = parser(conf)
    print(f"  -> 获取到 {len(papers)} 篇论文")
    return papers


def main():
    parser = argparse.ArgumentParser(description="会议放榜专题抓取")
    parser.add_argument("--conference", help="指定会议名称（不指定则抓取全部已配置的会议）")
    parser.add_argument("--output-dir", default=os.path.join(DATA_DIR, "conferences"), help="输出目录")
    args = parser.parse_args()

    settings = load_config()
    conferences = settings.get("conferences", [])

    if not conferences:
        print("[INFO] 未配置任何会议跟踪。在 config/settings.yaml 中添加 conferences 列表即可。")
        print("示例：")
        print("  conferences:")
        print('    - name: "CoRL 2025"')
        print('      source: "openreview"')
        print('      venue_id: "robot-learning.org/CoRL/2025/Conference"')
        return

    if args.conference:
        conferences = [c for c in conferences if c.get("name") == args.conference]
        if not conferences:
            sys.exit(f"未找到会议: {args.conference}")

    os.makedirs(args.output_dir, exist_ok=True)

    all_results = {}
    for conf in conferences:
        papers = run_conference(conf)
        conf_name = conf.get("name", "unknown").replace(" ", "_").lower()
        output = {
            "conference": conf.get("name"),
            "fetched_at": datetime.now().isoformat(),
            "count": len(papers),
            "papers": papers,
        }
        path = os.path.join(args.output_dir, f"{conf_name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[INFO] 已保存: {path}")
        all_results[conf.get("name", "")] = output

    # 汇总
    total = sum(r["count"] for r in all_results.values())
    print(f"\n[INFO] 会议放榜专题完成！共抓取 {len(all_results)} 个会议，{total} 篇论文。")


if __name__ == "__main__":
    main()
