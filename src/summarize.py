"""
摘要生成模块 —— 调用 DeepSeek V4 对论文做结构化摘要 + 深度解读。

Prompt 模板中的 {{domain_name}} 和 {{subfield_labels}} 运行时从领域包动态注入，
确保代码与领域内容完全解耦。
"""

import argparse
import json
import os
import re
import sys
import time
import yaml
from openai import OpenAI

# ---------- 路径 ----------

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INPUT_FILE = os.path.join(DATA_DIR, "today_papers.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "today_summaries.json")


# ---------- arXiv 镜像站：方便国内用户在不开启加速器的情况下访问 ----------

ARXIV_MIRRORS = {
    "中科院": "https://xxx.itp.ac.cn/abs/{arxiv_id}",
    "arxiv.org.cn": "https://arxiv.org.cn/abs/{arxiv_id}",
}


def make_mirror_urls(arxiv_id: str) -> dict:
    """为论文生成多个国内可访问的镜像链接。"""
    mirrors = {}
    for name, template in ARXIV_MIRRORS.items():
        mirrors[name] = template.format(arxiv_id=arxiv_id)
    return mirrors


# ---------- 文本清洗：去除 AI 输出的 markdown 格式残余 ----------

def clean_summary(text: str) -> str:
    """
    清洗 DeepSeek 输出的结构化摘要，去除 markdown 格式残余，
    保留纯文本 + 我们自己的【】结构化标记，提升终端阅读体验。

    处理项：
    - 删除独立的 ### / ## / # 行
    - 删除行首的 ### / ## / # 标记（保留后续文字）
    - 删除孤立的列表标记（行首的 - 后面无实质内容）
    - 将 markdown 粗体 **text** 转为 ▲text▲（避免与飞书 markdown 冲突）
    - 合并多余空行
    """
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        stripped = line.strip()

        # 跳过纯空白行（先收集，最后统一处理连续空行）
        if not stripped:
            cleaned.append("")
            continue

        # 删除纯 markdown 标题行（如单独一行的 "###"）
        if re.match(r"^#{1,6}\s*$", stripped):
            continue

        # 删除纯分隔线
        if re.match(r"^[-*=_]{3,}\s*$", stripped):
            cleaned.append("")
            continue

        # 处理行首的 # 标记：去除标记保留文字
        # 如 "### 核心贡献" → "核心贡献"
        # 如 "## 方法细节" → "方法细节"
        m = re.match(r"^#{1,6}\s+(.+)", stripped)
        if m:
            stripped = m.group(1)

        # 处理独立的列表标记（后面没有实质文字的 "- " 或 "* "）
        if re.match(r"^[-*]\s*$", stripped):
            continue

        # 行首的 "- " 或 "* " 列表标记 → 替换为更清晰的项目符号
        m = re.match(r"^[-*]\s+(.+)", stripped)
        if m:
            stripped = "• " + m.group(1)

        # 处理数字列表如 "1. " "2. " → 保持原样但确保后面有内容
        # （DeepSeek 有时输出 "1. " 后面换行没有内容）
        m = re.match(r"^\d+\.\s*$", stripped)
        if m:
            continue

        # 将行内 markdown 粗体转为更可读的格式（避免与 lark_md 冲突）
        # **text** → ▲text▲，这样在飞书/邮件中都能正常显示，且有强调效果
        stripped = re.sub(r"\*\*(.+?)\*\*", r"▲\1▲", stripped)

        # 删除多余的行内 # 符号（通常是格式错误）
        stripped = re.sub(r"(?<!\d)\s*###\s*", " ", stripped)

        cleaned.append(stripped)

    # 合并连续空行：最多保留一个空行
    result = []
    prev_empty = False
    for line in cleaned:
        if line == "":
            if not prev_empty:
                result.append(line)
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False

    # 去掉首尾空行
    while result and result[0] == "":
        result.pop(0)
    while result and result[-1] == "":
        result.pop()

    return "\n".join(result)


def clean_translation(text: str) -> str:
    """清洗翻译文本，去除 markdown 残余但保留自然段落。"""
    # 去除行首的 # 标记
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # 去除孤立的 ###
    text = re.sub(r"\s*###\s*", " ", text)
    # 合并多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 去掉首尾空白
    return text.strip()


# ---------- 配置 ----------

def load_config():
    with open(os.path.join(PROJECT_ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_domain(settings: dict) -> dict:
    domain_name = settings["active_domain"]
    path = os.path.join(PROJECT_ROOT, "domains", f"{domain_name}.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ========== SYSTEM PROMPT ==========

SYSTEM_PROMPT_TEMPLATE = """你是一名{{domain_name}}领域的研究助理，读者是一名本科生，目标是通过你的简报建立对{{domain_name}}全领域的认知全景和前沿敏感度，而非某一个子方向的深度研究。因此你的解读要兼顾准确性和可读性，帮读者理解论文在整个领域坐标系里的位置。

请对给定论文（标题+摘要，必要时结合全文）按以下结构输出，全部使用中文：

【子方向标签】
从以下分类中选一个最贴切的：{{subfield_labels}}
（如都不完全贴切，可自拟一个简短标签）

【一句话简介】
用一句话说清楚这篇论文做了什么（40字以内）。既要概括核心贡献，又要让读者立刻知道"这跟自己有什么关系"。

【背景知识】
这篇论文涉及的关键背景/前置概念是什么？如果读者没接触过这个子方向，需要先知道什么才能看懂这篇论文在解决什么问题。请用 4-6 句展开说明，用类比或通俗语言解释核心概念；专业术语第一次出现时必须中英对照并给出简明解释，不能让读者自己再去查。

【核心问题】
这篇论文试图解决什么问题，为什么重要。请具体说明该项研究在整个领域中的意义——它堵上了什么 gap、解决了什么前人没解决的问题（3-5 句，每句有实质信息）。

【方法】
核心技术方案是什么，与常规做法相比它的创新点在哪里。请详细展开，不要只列名字——每个技术要点需要解释原理、为什么有效、以及为什么之前没人这么做。可分点叙述（5-8 句）。

【实验结果】
关键实验设置和结论。用具体数字说话，不要泛泛而谈。说明实验在什么环境/数据集上做的、对比了哪些 baseline、关键指标提升了多少、是否有消融实验验证各部分贡献。至少写出 3 组具体数据。

【局限性】
论文自己承认的或你能看出的局限。每条局限需要解释为什么它是局限（而不只是列标签），以及这个局限对实际应用意味着什么（2-4 点）。

【个人视角点评】
请充分展开，不要一两句话带过：
- 这篇论文在它所属子方向里处于什么位置（渐进改进 / 范式突破 / 填补空白）？为什么这么判断？
- 和领域里其他子方向相比，这类工作的价值和天花板大致在哪个层级？
- 落地价值：距离实际部署/产品化还有多远，卡点在哪？需要什么条件才能落地？
- 如果只记住一件事：这篇论文最值得你记住的 idea 是什么？为什么这个 idea 特别？

【代码/数据开源情况】
是否开源，链接（如有）。如未开源，说明论文承诺是否会在后续公开。

要求：请写得详细充分，每个小节都要有足够的实质内容和细节，不要用概括性语言一笔带过；专业术语首次出现时中英对照并解释；假设读者有该领域基础知识但不是子方向专家。"""


def build_system_prompt(domain: dict) -> str:
    """从领域包动态注入变量，生成 system prompt。"""
    labels = [sf["label"] for sf in domain["subfields"].values()]
    return SYSTEM_PROMPT_TEMPLATE.replace("{{domain_name}}", domain["domain_name"]).replace(
        "{{subfield_labels}}", "、".join(labels)
    )


# ========== 翻译（完整原文标题+摘要，不缩水）==========

def translate_title_abstract(client: OpenAI, model: str, paper: dict) -> dict:
    """将英文论文标题和摘要完整翻译成中文，不截断不缩水。"""
    full_abstract = paper.get("abstract", "")

    prompt = f"""请将以下英文论文的标题和摘要完整翻译成中文。注意：
- 标题翻译要准确、信雅达，必要时在括号内保留英文原术语
- 摘要翻译要完整覆盖原文的每一句话，不要省略、不要概括、不要缩水
- 专业术语首次出现时中英对照
- 保持原文的叙述逻辑和细节密度

标题: {paper['title']}

摘要: {full_abstract}

请按以下格式输出：

【中文标题】
...

【中文摘要】
..."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
        )
        content = response.choices[0].message.content.strip()
        title_cn = ""
        abstract_cn = ""
        if "【中文标题】" in content and "【中文摘要】" in content:
            parts = content.split("【中文摘要】")
            title_cn = parts[0].replace("【中文标题】", "").strip()
            abstract_cn = parts[1].strip()
        else:
            # 兼容非标准输出
            abstract_cn = content
        return {"title_cn": title_cn, "abstract_cn": abstract_cn}
    except Exception as e:
        print(f"[WARN] 翻译失败: {e}")
        return {"title_cn": paper["title"], "abstract_cn": paper["abstract"]}


# ========== 结构化深度摘要 ==========

def summarize_paper(client: OpenAI, model: str, paper: dict, system_prompt: str) -> dict:
    """对单篇论文生成深度结构化摘要（max_tokens=8192 保证不截断）。"""
    user_prompt = f"""标题: {paper['title']}

摘要: {paper['abstract']}

作者: {', '.join(paper.get('authors', [])[:10])}

arXiv ID: {paper['arxiv_id']}
arXiv 链接: {paper['url']}

请按 system prompt 的结构，对以上论文进行详细、深入的分析。每个模块都要充分展开，不能一两句话带过。"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=8192,
        )
        return {"arxiv_id": paper["arxiv_id"], "summary": response.choices[0].message.content.strip()}
    except Exception as e:
        print(f"[WARN] 摘要生成失败 ({paper['arxiv_id']}): {e}")
        return {"arxiv_id": paper["arxiv_id"], "summary": f"【摘要生成失败】{e}", "error": str(e)}


# ========== 主流程 ==========

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

        # 生成国内可访问的镜像链接
        mirror_urls = make_mirror_urls(paper["arxiv_id"])

        # 完整翻译（标题+摘要）
        if not args.no_translate:
            translation = translate_title_abstract(client, model, paper)
        else:
            translation = {"title_cn": "", "abstract_cn": ""}

        # 结构化深度摘要（清洗 markdown 残余）
        summary_result = summarize_paper(client, model, paper, system_prompt)
        raw_summary = summary_result.get("summary", "")
        cleaned_summary = clean_summary(raw_summary)

        # 清洗翻译文本
        cleaned_title_cn = clean_translation(translation.get("title_cn", ""))
        cleaned_abstract_cn = clean_translation(translation.get("abstract_cn", ""))

        results.append({
            **paper,
            "title_cn": cleaned_title_cn,
            "abstract_cn": cleaned_abstract_cn,
            "mirror_urls": mirror_urls,
            "structured_summary": cleaned_summary,
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
