"""
论文抓取与过滤模块 —— 领域无关，运行时从 domains/*.yaml 读取配置。

流程：
1. 读取 config/settings.yaml -> active_domain -> 加载对应领域包
2. 按子方向分别构造 arXiv 查询，抓取候选论文
3. 去重（跳过已处理论文）
4. 调用 DeepSeek 做相关性打分
5. diversity_mode：按子方向多样性选取最终推送列表
6. 保存结果 JSON 供下游模块使用
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import arxiv
import yaml
from openai import OpenAI

from dedup import is_seen, mark_batch_seen

# ---------- 路径工具 ----------

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "today_papers.json")


def load_config():
    """加载全局配置。"""
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_domain(settings: dict) -> dict:
    """加载当前激活的领域包。"""
    domain_name = settings["active_domain"]
    path = os.path.join(PROJECT_ROOT, "domains", f"{domain_name}.yaml")
    if not os.path.exists(path):
        sys.exit(f"领域包不存在: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_queries(domain: dict) -> list[dict]:
    """
    为每个子方向构建一个查询对象。
    返回: [{subfield_id, label, query_string}]
    """
    queries = []
    for sf_id, sf in domain["subfields"].items():
        kw_queries = [f'abs:"{kw}"' for kw in sf["keywords"]]
        q = " OR ".join(kw_queries)
        cat_filter = " OR ".join(f"cat:{c}" for c in domain["categories"])
        full = f"({q}) AND ({cat_filter})"
        queries.append({"subfield_id": sf_id, "label": sf["label"], "query": full})
    return queries


def fetch_candidates(query: str, max_results: int = 15) -> list[dict]:
    """从 arXiv 抓取单条查询的候选论文。"""
    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )
    papers = []
    try:
        for result in client.results(search):
            papers.append({
                "arxiv_id": result.entry_id.split("/")[-1].replace("v", "").split("v")[0],
                "raw_id": result.entry_id,
                "title": result.title,
                "authors": [a.name for a in result.authors],
                "abstract": result.summary,
                "published": result.published.isoformat(),
                "url": result.entry_id,
                "pdf_url": result.pdf_url,
                "categories": list(result.categories),
            })
    except Exception as e:
        print(f"[WARN] arXiv 查询出错: {e}")
    return papers


def check_priority(paper: dict, priority_labs: list[str]) -> bool:
    """检查论文作者/机构是否命中 priority_labs。"""
    text = " ".join(paper.get("authors", [])) + " " + paper.get("abstract", "")
    text_lower = text.lower()
    return any(lab.lower() in text_lower for lab in priority_labs)


def score_with_deepseek(
    client: OpenAI,
    model: str,
    papers: list[dict],
    domain: dict,
    threshold: int,
) -> list[dict]:
    """
    调用 DeepSeek 对候选论文批量打分。
    返回带 score 字段的论文列表（已筛选 >= threshold 的）。
    """
    if not papers:
        return []

    labels = [sf["label"] for sf in domain["subfields"].values()]
    labels_str = "、".join(labels)

    # 批量处理，每次最多 10 篇
    scored = []
    batch_size = 10
    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]
        papers_text = "\n\n---\n\n".join(
            f"[{j}] 标题: {p['title']}\n摘要: {p['abstract'][:800]}"
            for j, p in enumerate(batch)
        )

        prompt = f"""你是一名{domain['domain_name']}领域的研究助理。下面是{len(batch)}篇arXiv论文的标题和摘要。

这些论文所属领域的子方向包括：{labels_str}

请对每篇论文做两件事：
1. 判断它属于哪个子方向（从上面列表选，如都不贴切可写"其他"）
2. 打一个相关性分（1-10），表示这篇论文是否属于{domain['domain_name']}领域内值得了解的重要进展

请严格按以下JSON格式输出（只输出JSON，不要其他内容）：
[{{"index": 0, "subfield": "子方向名", "score": 8, "reason": "一句话理由"}}, ...]

注意：index 对应上面 [数字] 的编号。"""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是严格的论文评审助理。只输出要求的JSON格式。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2000,
            )
            content = response.choices[0].message.content.strip()
            # 清理可能的 markdown 代码块包裹
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            results = json.loads(content)

            for item in results:
                idx = item["index"]
                if 0 <= idx < len(batch):
                    batch[idx]["score"] = item["score"]
                    batch[idx]["subfield_label"] = item.get("subfield", "")
                    batch[idx]["score_reason"] = item.get("reason", "")
                    if item["score"] >= threshold:
                        scored.append(batch[idx])
        except Exception as e:
            print(f"[WARN] DeepSeek 打分出错 (batch {i}): {e}")
            # 降低标准：出错时全部保留
            for p in batch:
                p["score"] = threshold
                p["subfield_label"] = ""
                p["score_reason"] = "API error, kept by default"
            scored.extend(batch)

        if i + batch_size < len(papers):
            time.sleep(1)  # 避免频率限制

    return scored


def diversity_select(papers: list[dict], limit: int) -> list[dict]:
    """
    多样性选取：每个子方向各取1篇最高分，剩余名额按全局分数补齐。
    """
    if not papers:
        return []

    # 按子方向分组
    by_subfield: dict[str, list[dict]] = {}
    for p in papers:
        sf = p.get("subfield_label", "其他")
        by_subfield.setdefault(sf, []).append(p)

    # 每组内按分数降序
    for sf in by_subfield:
        by_subfield[sf].sort(key=lambda x: x.get("score", 0), reverse=True)

    selected = []
    used_ids = set()

    # 第一轮：从有论文的子方向各取1篇最高分
    for sf, sf_papers in by_subfield.items():
        for p in sf_papers:
            if p["arxiv_id"] not in used_ids:
                selected.append(p)
                used_ids.add(p["arxiv_id"])
                break

    # 若超出 limit，按分数截断
    if len(selected) > limit:
        selected.sort(key=lambda x: x.get("score", 0), reverse=True)
        selected = selected[:limit]
        return selected

    # 若不足 limit，从全局按分数补齐
    if len(selected) < limit:
        remaining = [p for p in papers if p["arxiv_id"] not in used_ids]
        remaining.sort(key=lambda x: x.get("score", 0), reverse=True)
        needed = limit - len(selected)
        selected.extend(remaining[:needed])

    return selected


def main():
    parser = argparse.ArgumentParser(description="抓取 arXiv 论文并过滤")
    parser.add_argument("--output", default=OUTPUT_FILE, help="输出 JSON 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="空跑模式：不实际调用 DeepSeek")
    parser.add_argument("--date", help="指定日期 YYYY-MM-DD（默认今天）")
    args = parser.parse_args()

    settings = load_config()
    domain = load_domain(settings)
    print(f"[INFO] 激活领域: {domain['domain_name']}")

    # DeepSeek 客户端
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        sys.exit("[ERROR] 未设置 DEEPSEEK_API_KEY 环境变量")
    client = OpenAI(api_key=api_key, base_url=settings["deepseek"]["api_base"])

    # 构建查询并抓取
    queries = build_queries(domain)
    all_candidates: dict[str, dict] = {}
    for q in queries:
        print(f"[INFO] 抓取子方向: {q['label']} ...")
        papers = fetch_candidates(q["query"], max_results=15)
        for p in papers:
            # 去重 + 以最高分版本为准（同一论文可能匹配多个子方向）
            if not is_seen(p["arxiv_id"]):
                if p["arxiv_id"] not in all_candidates:
                    all_candidates[p["arxiv_id"]] = p
                    p["matched_subfields"] = [q["subfield_id"]]
                else:
                    all_candidates[p["arxiv_id"]]["matched_subfields"].append(q["subfield_id"])
        time.sleep(0.5)

    candidates = list(all_candidates.values())
    print(f"[INFO] 去重后候选论文: {len(candidates)} 篇")

    # 标记 priority lab
    priority_labs = domain.get("priority_labs", [])
    for p in candidates:
        p["priority"] = check_priority(p, priority_labs)

    # 按发布日期筛选（只看最近2天的）
    from datetime import timezone as tz
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=tz.utc)
    else:
        target_date = datetime.now(tz.utc)
    cutoff = target_date - timedelta(days=2)
    recent = [p for p in candidates if datetime.fromisoformat(p["published"]) >= cutoff]
    print(f"[INFO] 最近2天内的论文: {len(recent)} 篇")

    # 相关性打分
    threshold = settings.get("relevance_threshold", 7)
    if not args.dry_run and recent:
        print(f"[INFO] 正在用 DeepSeek 打分 ...")
        scored = score_with_deepseek(
            client,
            settings["deepseek"]["model"],
            recent,
            domain,
            threshold,
        )
    else:
        scored = recent

    print(f"[INFO] 超过阈值({threshold}分)的论文: {len(scored)} 篇")

    # 优先展示 priority 论文
    priority_papers = [p for p in scored if p.get("priority")]
    normal_papers = [p for p in scored if not p.get("priority")]
    print(f"[INFO] 重点团队论文: {len(priority_papers)} 篇")

    # 多样性选取
    daily_limit = settings.get("daily_limit", 5)
    if settings.get("diversity_mode", True):
        selected_normal = diversity_select(normal_papers, daily_limit - len(priority_papers))
    else:
        normal_papers.sort(key=lambda x: x.get("score", 0), reverse=True)
        selected_normal = normal_papers[: daily_limit - len(priority_papers)]

    final_papers = priority_papers + selected_normal
    # 最终按分数排序
    final_papers.sort(key=lambda x: x.get("score", 0), reverse=True)
    final_papers = final_papers[:daily_limit]

    print(f"[INFO] 最终入选: {len(final_papers)} 篇")
    for i, p in enumerate(final_papers):
        tag = "⭐" if p.get("priority") else "  "
        print(f"  {tag} [{p.get('subfield_label', '?')}] {p['title'][:60]}... ({p.get('score', '?')}/10)")

    # 保存结果
    os.makedirs(DATA_DIR, exist_ok=True)
    output = {
        "date": target_date.strftime("%Y-%m-%d"),
        "domain": domain["domain_name"],
        "count": len(final_papers),
        "papers": final_papers,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 结果已保存至: {args.output}")

    # 标记为已处理
    if final_papers and not args.dry_run:
        mark_batch_seen([{"arxiv_id": p["arxiv_id"], "title": p["title"]} for p in final_papers])


if __name__ == "__main__":
    main()
