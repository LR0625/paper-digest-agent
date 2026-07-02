"""
摘要生成模块 —— 调用 DeepSeek V4 对论文做结构化摘要 + 深度解读。

Prompt 模板中的 {{domain_name}} 和 {{subfield_labels}} 运行时从领域包动态注入，
确保代码与领域内容完全解耦。
"""

import argparse
import json
import os
import sys
import time
import yaml
from openai import OpenAI

# ---------- 路径 ----------

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INPUT_FILE = os.path.join(DATA_DIR, "today_papers.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "today_summaries.json")


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_domain(settings: dict) -> dict:
    domain_name = settings["active_domain"]
    path = os.path.join(PROJECT_ROOT, "domains", f"{domain_name}.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


SYSTEM_PROMPT_TEMPLATE = """你是一名{{domain_name}}领域的研究助理，读者是一名本科生，目标是通过你的简报建立对{{domain_name}}全领域的认知全景和前沿敏感度，而非某一个子方向的深度研究。因此你的解读要兼顾准确性和可读性，帮读者理解论文在整个领域坐标系里的位置。

请对给定论文（标题+摘要，必要时结合全文）按以下结构输出，全部使用中文：

【子方向标签】
从以下分类中选一个最贴切的：{{subfield_labels}}
（如都不完全贴切，可自拟一个简短标签）

【一句话简介】
用一句话说清楚这篇论文做了什么（20字以内）。

【背景知识】
这篇论文涉及的关键背景/前置概念是什么？如果读者没接触过这个子方向，需要先知道什么才能看懂这篇论文在解决什么问题（2-4句，用类比或通俗语言，不堆术语）。

【核心问题】
这篇论文试图解决什么问题，为什么重要（2-3句）。

【方法】
核心技术方案是什么，与常规做法的区别在哪（3-5句，可分点）。

【实验结果】
关键实验设置和结论，用具体数字说话，不要泛泛而谈。

【局限性】
论文自己承认的或你能看出的局限（1-3点）。

【个人视角点评】
- 这篇论文在它所属子方向里处于什么位置（渐进改进 / 范式突破 / 填补空白）？
- 和领域里其他子方向相比，这类工作的价值和天花板大致在哪个层级？
- 落地价值：距离实际部署/产品化还有多远，卡点在哪？
- 如果只记住一件事：这篇论文最值得你记住的idea是什么？

【代码/数据开源情况】
是否开源，链接（如有）。

要求：语言精炼，避免空话套话；不要逐句翻译摘要，要提炼理解后转述；专业术语第一次出现时中英对照并简单解释；假设读者有该领域基础知识但不是子方向专家。"""


def build_system_prompt(domain: dict) -> str:
    """从领域包动态注入变量，生成 system prompt。"""
    labels = [sf["label"] for sf in domain["subfields"].values()]
    return SYSTEM_PROMPT_TEMPLATE.replace("{{domain_name}}", domain["domain_name"]).replace(
        "{{subfield_labels}}", "、".join(labels)
    )


def translate_title_abstract(client: OpenAI, model: str, paper: dict) -> dict:
    """单独翻译标题和摘要。"""
    prompt = f"""请将以下英文论文的标题和摘要翻译成中文。

标题: {paper['title']}

摘要: {paper['abstract'][:1500]}

输出格式：
【中文标题】
...

【中文摘要】
..."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        content = response.choices[0].message.content.strip()
        # 简单解析
        title_cn = ""
        abstract_cn = ""
        if "【中文标题】" in content and "【中文摘要】" in content:
            parts = content.split("【中文摘要】")
            title_cn = parts[0].replace("【中文标题】", "").strip()
            abstract_cn = parts[1].strip()
        else:
            abstract_cn = content
        return {"title_cn": title_cn, "abstract_cn": abstract_cn}
    except Exception as e:
        print(f"[WARN] 翻译失败: {e}")
        return {"title_cn": paper["title"], "abstract_cn": paper["abstract"]}


def summarize_paper(client: OpenAI, model: str, paper: dict, system_prompt: str) -> dict:
    """对单篇论文生成结构化摘要。"""
    user_prompt = f"""标题: {paper['title']}

摘要: {paper['abstract'][:2000]}

作者: {', '.join(paper.get('authors', [])[:10])}

arXiv ID: {paper['arxiv_id']}
URL: {paper['url']}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=4096,
        )
        return {"arxiv_id": paper["arxiv_id"], "summary": response.choices[0].message.content.strip()}
    except Exception as e:
        print(f"[WARN] 摘要生成失败 ({paper['arxiv_id']}): {e}")
        return {"arxiv_id": paper["arxiv_id"], "summary": f"【摘要生成失败】{e}", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="生成论文结构化摘要")
    parser.add_argument("--input", default=INPUT_FILE, help="输入论文 JSON")
    parser.add_argument("--output", default=OUTPUT_FILE, help="输出摘要 JSON")
    parser.add_argument("--no-translate", action="store_true", help="跳过翻译")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"[ERROR] 输入文件不存在: {args.input}")

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    papers = data.get("papers", [])
    if not papers:
        print("[INFO] 没有论文需要摘要，跳过。")
        output = {"date": data.get("date", ""), "domain": data.get("domain", ""), "count": 0, "papers": []}
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        return

    print(f"[INFO] 共 {len(papers)} 篇论文待摘要")

    settings = load_config()
    domain = load_domain(settings)
    system_prompt = build_system_prompt(domain)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        sys.exit("[ERROR] 未设置 DEEPSEEK_API_KEY")
    client = OpenAI(api_key=api_key, base_url=settings["deepseek"]["api_base"])
    model = settings["deepseek"]["model"]

    results = []
    for i, paper in enumerate(papers):
        print(f"[INFO] 摘要生成 {i+1}/{len(papers)}: {paper['title'][:50]}...")

        # 翻译
        if not args.no_translate:
            translation = translate_title_abstract(client, model, paper)
        else:
            translation = {"title_cn": "", "abstract_cn": ""}

        # 结构化摘要
        summary_result = summarize_paper(client, model, paper, system_prompt)

        results.append({
            **paper,
            **translation,
            "structured_summary": summary_result.get("summary", ""),
        })

        if i < len(papers) - 1:
            time.sleep(1)

    output = {
        "date": data.get("date", ""),
        "domain": data.get("domain", ""),
        "count": len(results),
        "papers": results,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 摘要已保存至: {args.output}")


if __name__ == "__main__":
    main()
