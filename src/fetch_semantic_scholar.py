"""
Semantic Scholar 备用数据源 —— 当 arXiv API 不稳定或返回 0 篇时作为 fallback。

Semantic Scholar (https://api.semanticscholar.org) 特点：
- 免费 API，无需 API Key
- 覆盖 arXiv 以外的会议/期刊论文
- 自带引用量、高影响力引用等含金量指标
- 国内可直接访问，比 arXiv 更稳定

输出格式与 fetch_arxiv.py 完全一致：data/today_papers.json
下游模块（summarize → push_*）无需任何改动。
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests
import yaml
from openai import OpenAI

from dedup import is_seen, mark_batch_seen

# ---------- 路径 ----------

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "today_papers.json")

S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_domain(settings: dict) -> dict:
    domain_name = settings["active_domain"]
    path = os.path.join(PROJECT_ROOT, "domains", f"{domain_name}.yaml")
    if not os.path.exists(path):
        sys.exit(f"领域包不存在: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def search_papers(query: str, limit: int = 15, max_retries: int = 3) -> list[dict]:
    """
    调用 Semantic Scholar 搜索 API，带重试。
    返回格式与 arXiv 抓取结果兼容。
    """
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,abstract,authors,year,externalIds,url,publicationDate,citationCount,influentialCitationCount",
        "sort": "publicationDate:desc",
    }

    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(S2_API, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                papers = []
                for item in data.get("data", []):
                    ext_ids = item.get("externalIds") or {}
                    arxiv_id = ext_ids.get("ArXiv", "")
                    # 如果没有 arXiv ID，用 Semantic Scholar ID 代替
                    s2_id = item.get("paperId", "")
                    if not arxiv_id:
                        arxiv_id = f"s2-{s2_id}"

                    papers.append({
                        "arxiv_id": arxiv_id,
                        "s2_id": s2_id,
                        "title": item.get("title", ""),
                        "authors": [a.get("name", "") for a in (item.get("authors") or [])],
                        "abstract": item.get("abstract") or "",
                        "published": item.get("publicationDate") or f"{item.get('year', '')}-01-01",
                        "url": ext_ids.get("ArXiv")
                            and f"https://arxiv.org/abs/{ext_ids['ArXiv']}"
                            or item.get("url") or f"https://api.semanticscholar.org/CorpusID:{s2_id}",
                        "pdf_url": ext_ids.get("ArXiv")
                            and f"https://arxiv.org/pdf/{ext_ids['ArXiv']}"
                            or "",
                        "categories": [],
                        "venue": item.get("journal") or item.get("venue") or "",
                        "citation_count": item.get("citationCount", 0),
                        "influential_citation_count": item.get("influentialCitationCount", 0),
                        "source": "semantic_scholar",
                    })
                return papers

            elif resp.status_code in (429, 503):
                if attempt < max_retries:
                    wait = 2 ** attempt
                    print(f"[WARN] S2 API {resp.status_code} (尝试 {attempt+1}/{max_retries+1}), {wait}s 后重试...")
                    time.sleep(wait)
                    continue
                else:
                    print(f"[WARN] S2 API {resp.status_code}，重试耗尽")
                    return []

            else:
                print(f"[WARN] S2 API 返回 {resp.status_code}: {resp.text[:200]}")
                return []

        except Exception as e:
            if attempt < max_retries:
                wait = 2 ** attempt
                print(f"[WARN] S2 连接出错 (尝试 {attempt+1}/{max_retries+1}): {e}, {wait}s 后重试...")
                time.sleep(wait)
            else:
                print(f"[WARN] S2 连接出错，重试耗尽: {e}")
                return []

    return []


def build_query_from_subfield(keywords: list[str]) -> str:
    """将子方向关键词拼接为 S2 搜索查询。"""
    return " OR ".join(f'"{kw}"' for kw in keywords)


def score_with_deepseek(
    client: OpenAI,
    model: str,
    papers: list[dict],
    domain: dict,
    threshold: int,
) -> list[dict]:
    """调用 DeepSeek 打分，与 fetch_arxiv.py 中的函数一致。"""
    if not papers:
        return []

    labels = [sf["label"] for sf in domain["subfields"].values()]
    labels_str = "、".join(labels)

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
            for p in batch:
                p["score"] = threshold
                p["subfield_label"] = ""
                p["score_reason"] = "API error, kept by default"
            scored.extend(batch)

        if i + batch_size < len(papers):
            time.sleep(1)

    return scored


def diversity_select(papers: list[dict], limit: int) -> list[dict]:
    """多样性选取：每个子方向各取1篇最高分。与 fetch_arxiv.py 一致。"""
    if not papers:
        return []

    by_subfield: dict[str, list[dict]] = {}
    for p in papers:
        sf = p.get("subfield_label", "其他")
        by_subfield.setdefault(sf, []).append(p)

    for sf in by_subfield:
        by_subfield[sf].sort(key=lambda x: x.get("score", 0), reverse=True)

    selected = []
    used_ids = set()

    for sf, sf_papers in by_subfield.items():
        for p in sf_papers:
            if p["arxiv_id"] not in used_ids:
                selected.append(p)
                used_ids.add(p["arxiv_id"])
                break

    if len(selected) > limit:
        selected.sort(key=lambda x: x.get("score", 0), reverse=True)
        selected = selected[:limit]
        return selected

    if len(selected) < limit:
        remaining = [p for p in papers if p["arxiv_id"] not in used_ids]
        remaining.sort(key=lambda x: x.get("score", 0), reverse=True)
        needed = limit - len(selected)
        selected.extend(remaining[:needed])

    return selected


def main():
    parser = argparse.ArgumentParser(description="Semantic Scholar 备用抓取")
    parser.add_argument("--output", default=OUTPUT_FILE, help="输出 JSON 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="不实际调用 DeepSeek")
    parser.add_argument("--date", help="指定日期 YYYY-MM-DD")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="合并模式：与已有 today_papers.json 合并而非覆盖",
    )
    args = parser.parse_args()

    settings = load_config()
    domain = load_domain(settings)
    print(f"[INFO] Semantic Scholar 备用源启动 | 激活领域: {domain['domain_name']}")

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        sys.exit("[ERROR] 未设置 DEEPSEEK_API_KEY 环境变量")
    client = OpenAI(api_key=api_key, base_url=settings["deepseek"]["api_base"])

    # 为每个子方向构建查询并搜索
    already_seen = set()
    if args.merge and os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            existing = json.load(f)
            for p in existing.get("papers", []):
                already_seen.add(p["arxiv_id"])
        print(f"[INFO] 合并模式：已有 {len(already_seen)} 篇，将追加新结果")

    all_candidates: dict[str, dict] = {}
    subfields = domain["subfields"]

    for sf_id, sf in subfields.items():
        print(f"[INFO] S2 搜索子方向: {sf['label']} ...")
        query = build_query_from_subfield(sf["keywords"])
        papers = search_papers(query, max_results=15)

        for p in papers:
            aid = p["arxiv_id"]
            if aid in already_seen:
                continue
            if is_seen(aid):
                already_seen.add(aid)
                continue
            if aid not in all_candidates:
                all_candidates[aid] = p
                p["matched_subfields"] = [sf_id]
            else:
                all_candidates[aid]["matched_subfields"].append(sf_id)

        time.sleep(0.6)  # S2 免费 API 限速 ~1 req/s

    candidates = list(all_candidates.values())
    print(f"[INFO] S2 去重后候选论文: {len(candidates)} 篇")

    # 按发布日期筛选（最近3天）
    from datetime import timezone as tz
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=tz.utc)
    else:
        target_date = datetime.now(tz.utc)
    cutoff = target_date - timedelta(days=3)
    recent = []
    for p in candidates:
        pub = p.get("published", "")
        if pub:
            try:
                pub_dt = datetime.fromisoformat(pub).replace(tzinfo=tz.utc)
            except Exception:
                # 可能只有年份，默认为最近
                pub_dt = target_date
        else:
            pub_dt = target_date
        if pub_dt >= cutoff:
            recent.append(p)
    print(f"[INFO] 最近3天内的论文: {len(recent)} 篇")

    # 相关性打分
    threshold = settings.get("relevance_threshold", 7)
    if not args.dry_run and recent:
        print(f"[INFO] 正在用 DeepSeek 打分（{len(recent)} 篇）...")
        scored = score_with_deepseek(client, settings["deepseek"]["model"], recent, domain, threshold)
    else:
        scored = recent

    print(f"[INFO] 超过阈值({threshold}分)的论文: {len(scored)} 篇")

    # 自动降阈值
    if len(scored) == 0 and not args.dry_run and recent:
        for fallback_t in [6, 5]:
            if fallback_t >= threshold:
                continue
            print(f"[INFO] 阈值降为 {fallback_t} 分重选...")
            fallback_papers = [p for p in recent if p.get("score", 0) >= fallback_t]
            if fallback_papers:
                scored = fallback_papers
                print(f"[INFO] 阈值 {fallback_t} 分命中 {len(scored)} 篇")
                break
        if len(scored) == 0:
            scored_by_score = sorted(recent, key=lambda x: x.get("score", 0), reverse=True)
            print(f"[INFO] 保底选取最高分 top 3")
            scored = scored_by_score[:3]

    # 多样性选取
    daily_limit = settings.get("daily_limit", 5)
    if settings.get("diversity_mode", True):
        final_papers = diversity_select(scored, daily_limit)
    else:
        scored.sort(key=lambda x: x.get("score", 0), reverse=True)
        final_papers = scored[:daily_limit]

    print(f"[INFO] S2 最终入选: {len(final_papers)} 篇")
    for i, p in enumerate(final_papers):
        cit = p.get("citation_count", 0)
        inf_cit = p.get("influential_citation_count", 0)
        print(f"  [{p.get('subfield_label', '?')}] {p['title'][:60]}... ({p.get('score', '?')}/10, 引用{cit}/{inf_cit})")

    # 保存
    os.makedirs(DATA_DIR, exist_ok=True)
    output_papers = final_papers

    if args.merge and os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            existing = json.load(f)
        existing_papers = existing.get("papers", [])
        existing_ids = {p["arxiv_id"] for p in existing_papers}
        new_only = [p for p in output_papers if p["arxiv_id"] not in existing_ids]
        existing_papers.extend(new_only)
        output_papers = existing_papers[:daily_limit]

    output = {
        "date": target_date.strftime("%Y-%m-%d"),
        "domain": domain["domain_name"],
        "count": len(output_papers),
        "papers": output_papers,
        "source": "semantic_scholar" if not args.merge else "arxiv+semantic_scholar",
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 结果已保存至: {args.output}")

    # 标记为已处理
    if output_papers and not args.dry_run:
        mark_batch_seen([{"arxiv_id": p["arxiv_id"], "title": p["title"]} for p in output_papers])


if __name__ == "__main__":
    main()
