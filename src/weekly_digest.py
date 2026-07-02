"""
周报汇总模块 —— 全领域全景地图 + 趋势总结。

做三件事：
1. 宽松抓取本周各子方向的论文（不受 daily_limit 限制）
2. 统计"本周各子方向新增论文数量"，生成分布小结（全景地图）
3. 把本周入选的论文丢给 DeepSeek 做跨论文趋势提炼
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta

import arxiv
import yaml
from openai import OpenAI

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "weekly_report.json")


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_domain(settings: dict) -> dict:
    domain_name = settings["active_domain"]
    path = os.path.join(PROJECT_ROOT, "domains", f"{domain_name}.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_week_history() -> list[dict]:
    """加载本周已推送的论文记录（从 history.json）。"""
    history_file = os.path.join(PROJECT_ROOT, "pages_output", "data", "history.json")
    if not os.path.exists(history_file):
        return []

    with open(history_file, encoding="utf-8") as f:
        all_history = json.load(f)

    # 筛选最近7天
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    return [h for h in all_history if h.get("date", "") >= cutoff]


def fetch_week_candidates(domain: dict, relaxed_limit: int) -> list[dict]:
    """
    宽松抓取本周各子方向论文（不受 daily_limit 限制）。
    返回带子方向标签的论文列表。
    """
    all_papers: dict[str, dict] = {}

    for sf_id, sf in domain["subfields"].items():
        kw_queries = [f'abs:"{kw}"' for kw in sf["keywords"]]
        q = " OR ".join(kw_queries)
        cat_filter = " OR ".join(f"cat:{c}" for c in domain["categories"])
        full_query = f"({q}) AND ({cat_filter})"

        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=full_query,
                max_results=relaxed_limit,
                sort_by=arxiv.SortCriterion.SubmittedDate,
            )
            for result in client.results(search):
                aid = result.entry_id.split("/")[-1].replace("v", "").split("v")[0]
                if aid not in all_papers:
                    all_papers[aid] = {
                        "arxiv_id": aid,
                        "title": result.title,
                        "published": result.published.isoformat(),
                        "url": result.entry_id,
                        "subfield": sf["label"],
                    }
        except Exception as e:
            print(f"[WARN] 子方向 '{sf['label']}' 抓取失败: {e}")

        time.sleep(0.5)

    # 只保留本周的
    cutoff = datetime.now() - timedelta(days=7)
    week_papers = [
        p for p in all_papers.values()
        if datetime.fromisoformat(p["published"]) >= cutoff
    ]
    return week_papers


def build_landscape(week_papers: list[dict], domain: dict) -> str:
    """生成本周子方向热度分布（全景地图）。"""
    counter = Counter(p.get("subfield", "其他") for p in week_papers)

    lines = ["## 本周子方向热度分布\n"]
    lines.append(f"本周共抓取到 {len(week_papers)} 篇相关论文，分布如下：\n")
    lines.append("| 子方向 | 论文数 | 热度 |")
    lines.append("|--------|--------|------|")

    # 找最大数用于可视化
    max_count = max(counter.values()) if counter else 1

    # 按数量降序
    for label, count in counter.most_common():
        bar_len = int(count / max_count * 20) if max_count else 0
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lines.append(f"| {label} | {count} | {bar} |")

    # 标注"挂零"的子方向
    all_labels = [sf["label"] for sf in domain["subfields"].values()]
    zero_labels = [l for l in all_labels if l not in counter]
    if zero_labels:
        lines.append(f"\n本周无新论文的子方向：{'、'.join(zero_labels)}")
        lines.append("（可能该方向本周不活跃，或关键词需要调整）")

    return "\n".join(lines)


def generate_trend_summary(client: OpenAI, model: str, pushed: list[dict], week_papers: list[dict], domain: dict) -> str:
    """调用 DeepSeek 生成跨论文趋势总结。"""
    if not pushed:
        return "本周无推送论文，跳过趋势总结。"

    # 收集本周推送论文的信息
    papers_info = []
    for h in pushed:
        for p in h.get("papers", []):
            papers_info.append({
                "title": p.get("title_cn") or p.get("title", ""),
                "subfield": p.get("subfield_label", ""),
                "summary": (p.get("structured_summary", "") or "")[:500],
            })

    papers_text = "\n\n".join(
        f"- [{p['subfield']}] {p['title']}\n  {p['summary'][:200]}"
        for p in papers_info
    )

    prompt = f"""你是一名{domain['domain_name']}领域的研究分析助理。以下是本周推送的论文精选：

{papers_text}

请完成以下分析（使用中文，500字以内）：

1. **本周趋势观察**：本周各子方向有没有出现从A范式转向B范式的迹象？有没有新的技术路线冒头？
2. **活跃团队/机构**：哪些实验室/机构这周动作频繁？有没有值得关注的新团队？
3. **跨论文观察**：本周不同子方向的论文之间有没有共同主题或互补关系？
4. **值得关注的方向**：基于本周动态，下周最值得留意的子方向是什么？"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一名严谨且有洞察力的研究分析助理。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[WARN] 趋势总结生成失败: {e}")
        return f"趋势总结生成失败: {e}"


def main():
    parser = argparse.ArgumentParser(description="周报汇总")
    parser.add_argument("--output", default=OUTPUT_FILE, help="输出 JSON 路径")
    args = parser.parse_args()

    settings = load_config()
    domain = load_domain(settings)
    print(f"[INFO] 生成周报 —— {domain['domain_name']}")

    # 1. 加载本周推送记录
    pushed = load_week_history()
    pushed_papers_count = sum(len(h.get("papers", [])) for h in pushed)
    print(f"[INFO] 本周已推送: {len(pushed)} 天，共 {pushed_papers_count} 篇")

    # 2. 宽松抓取本周全领域论文
    relaxed_limit = settings.get("weekly", {}).get("relaxed_limit", 30)
    print(f"[INFO] 宽松抓取本周全领域论文 (limit={relaxed_limit})...")
    week_papers = fetch_week_candidates(domain, relaxed_limit)
    print(f"[INFO] 本周候选论文: {len(week_papers)} 篇")

    # 3. 全景地图
    landscape = build_landscape(week_papers, domain)
    print(landscape)

    # 4. 趋势总结（需要 DeepSeek）
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if api_key:
        client = OpenAI(api_key=api_key, base_url=settings["deepseek"]["api_base"])
        trend = generate_trend_summary(client, settings["deepseek"]["model"], pushed, week_papers, domain)
    else:
        trend = "（未配置 DEEPSEEK_API_KEY，跳过趋势总结）"

    # 5. 输出
    report = {
        "week_start": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
        "week_end": datetime.now().strftime("%Y-%m-%d"),
        "domain": domain["domain_name"],
        "pushed_count": pushed_papers_count,
        "total_candidates": len(week_papers),
        "landscape": landscape,
        "trend_summary": trend,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 周报已保存至: {args.output}")


if __name__ == "__main__":
    main()
