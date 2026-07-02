# 🤖 我做了一个「任意方向论文速递」机器人——每天早上9点准时推送，只改一个文件就能适配你的领域

> **适用平台**：知乎 / 掘金 / V2EX / 小红书 / 即刻 / X（Twitter）
> 标注了 ✂️ 的地方可按需拆分截取

---

## ✂️ 开头：先看看每天收到的效果

每天早上 9:00，飞书准时弹出一条消息：

> 📄 **具身智能与机器人学习 日报 [1/5]**
>
> **FurnitureVLA：基于视觉-语言-动作模型学习长时双居家居装配**
> *FurnitureVLA: Learning Long-Horizon Bimanual Furniture Assembly with VLA*
>
> 📂 VLA与端到端策略　📊 相关性 **9/10**
> 🔗 [arXiv 原文](https://arxiv.org/abs/...) | 🌐 [中科院镜像](https://xxx.itp.ac.cn/abs/...) | [arxiv.org.cn镜像](https://arxiv.org.cn/abs/...)
>
> ━━━━━━━━━━━━━━
> 📝 **中文摘要（完整翻译）**
> （完整的中文论文摘要翻译）
>
> ━━━━━━━━━━━━━━
> 🔍 **深度解读**
> 【背景知识】这篇论文的核心是视觉-语言-动作模型（VLA），可以类比为机器人的"大脑"……
> 【核心问题】传统机器人家具装配研究局限于仿真或单臂操作，真实尺度的长时任务需要双……
> 【方法】提出 FurnitureVLA 系统，创新在于：1）可扩展的数据收集管线…… 2）进度增强……
> 【实验结果】在7种宜家家具上测试，最长1550步操作序列，成功率……
> 【局限性】1）目前仅测试了结构相似的家具…… 2）VR数据采集成本较高……
> 【个人视角点评】这是一篇**范式突破**性质的工作，首次将VLA成功应用于真实尺度双……
> 【代码/数据开源情况】已开源：github.com/xxx

同时邮箱收到一封排版精美的 HTML 邮件——紫色渐变头部、分区清晰、手机端观感良好。

**不是我在盯 arXiv**，是一个跑在 GitHub 上、完全免费、零服务器成本的 Agent 在帮我盯。关机也不影响，每天早上准时到。

---

## ✂️ 为什么做这个

如果你也是学生/研究者，大概率经历这些：

- 关注的领域每天几十篇新论文，标题划一眼就过了，什么都没记住
- 想"保持前沿敏感度"，但没有系统性方法，全靠刷社交媒体里别人分享的截图
- 想读综述打基础，又不知道现在这个领域到底哪个子方向在升温
- 试过订阅 arXiv 官方邮件/各种日报工具，结果是：**要么纯关键词堆砌被热点方向淹没，要么默认你是专家没有背景知识铺垫，要么没法在国内直接打开原文链接**

市面上不是没有类似工具——调研了 GitHub 上十几个类似项目。但发现共同问题：纯得分排序导致热门方向霸屏、没有子方向多样性概念、默认读者是内行、中文是附加功能、只能改代码不能改配置。所以自己动手做了一个。

---

## ✂️ 这个项目做了什么（核心卖点）

**一句话**：一个基于 arXiv + LLM + GitHub Actions 的全自动论文速递机器人。

| 能力 | 具体实现 |
|---|---|
| 每天 0-5 篇 | 宁缺毋滥，DeepSeek 打分 ≥7 才推送 |
| 中文完整翻译 | 标题+摘要逐句翻译，不缩水不概括 |
| 深度结构化解读 | 背景知识 → 核心问题 → 方法 → 实验 → 局限 → 个人点评 |
| 子方向多样性覆盖 | 8 个子方向各取 1 篇最高分，不被热点方向淹没 |
| 版本不依赖原文 | 国内可访问的 arXiv 镜像链接，不翻墙也能看 |
| 三通道推送 | 飞书 + 邮件 + GitHub Pages（可浏览历史的永久归档） |
| 每周全领域趋势地图 | 各子方向热度统计 + 跨论文趋势总结 |

### 和同类项目比

| | 常见 arXiv 日报 | 本项目 |
|---|---|---|
| 过滤逻辑 | 关键词命中数排序 | LLM 打分 + 子方向多样性覆盖 |
| 中文支持 | 附加功能，机翻味浓 | **中文优先设计**，Prompt 本身就是中文语境 |
| 新手友好 | 默认你懂 | 每篇带**背景知识层**，术语中英对照解释 |
| 国内访问 | 仅原始 arXiv 链接 | 自动附带**镜像站链接** |
| 换方向 | 要改代码 | **只改一个 yaml 文件** |
| 推送渠道 | 通常单一 | 飞书+邮件+Pages+Issues 多选 |

---

## ✂️ 部署教程：你只需要改3样东西

### 前置准备（3 个都有就完美，最少 1 个也能跑）

| 东西 | 怎么拿 | 要钱吗 |
|---|---|---|
| GitHub 账号 | [github.com](https://github.com) 注册 | 免费 |
| DeepSeek API Key | [platform.deepseek.com](https://platform.deepseek.com) 注册 → API Keys | 几块钱够跑很久 |
| 飞书群机器人 | 飞书群 → 设置 → 群机器人 → 添加 → 复制 webhook URL | 免费 |
| 163/QQ 邮箱授权码 | 邮箱设置 → 开启 SMTP → 生成授权码 | 免费 |

> 💡 **零密钥尝鲜**：如果暂时不想申请任何密钥，可以只用 GitHub Issues 作为推送渠道——fork/template 完直接能在 Issues 里看到效果。

---

### 为什么说"要改3样东西"

这是我开源时的核心设计——把**属于你个人的**和**通用功能**彻底拆开：

| 你要改的 | 为什么 | 对应文件 |
|---|---|---|
| **① API 密钥** | 飞书 webhook 是我的群，邮箱是我的邮箱，DeepSeek 是花的我的钱。你必须填自己的，不然就推我这里了 | GitHub Secrets（3 个环境变量） |
| **② 研究方向** | 我关注的是具身智能/机器人，你关注的可能是 NLP / CV / 多模态 / RL / 生物信息——系统需要知道你要什么 | `domains/你的领域.yaml`（1 个文件） |
| **③ 激活配置** | 告诉系统加载你刚才写的领域文件 | `config/settings.yaml` 里改 1 行 |

其他所有代码**你一行都不用看、不用改**。

---

### 正式部署：3 步搞定

#### 第一步：用模板创建仓库（30 秒）

打开 [github.com/LR0625/paper-digest-agent](https://github.com/LR0625/paper-digest-agent)，点击绿色按钮 **"Use this template"** → "Create a new repository"。

> ⚠️ 别点 Fork，点 **Use this template**——这样你的仓库和我的完全独立，后续你的改动不会被认为是要给我提 PR。同时记得勾选 Template repository，这样别人也可以用你的仓库作为模板。

#### 第二步：定义你的研究方向（3 分钟）

复制模板，填你的内容：

```bash
cp domains/_template.yaml domains/my_field.yaml
```

打开 `domains/my_field.yaml`，填入你的领域信息。举个例子，如果你是做多模态大模型的：

```yaml
domain_name: "多模态大模型"
categories: ["cs.CL", "cs.CV", "cs.LG"]

subfields:
  vlm_pretrain:
    label: "视觉语言预训练"
    keywords: ["vision-language pretraining", "multimodal foundation model", "VLM training"]
  multimodal_reasoning:
    label: "多模态推理"
    keywords: ["multimodal reasoning", "visual question answering", "chain-of-thought multimodal"]
  video_understanding:
    label: "视频理解"
    keywords: ["video understanding", "temporal grounding", "video question answering"]
  # …再加 3-5 个子方向，建议 6-10 个
  # 太少起不到多样性覆盖效果，太多每个方向曝光太少

priority_labs:
  - "Google DeepMind"
  - "Meta AI"
  # 你关注的实验室英文名
```

**不知道怎么拆子方向？** 直接把 `_template.yaml` 丢给 ChatGPT / Claude Code，说：

> "我想关注 [多模态大模型] 方向，帮我拆成 8 个左右的子方向，每个给 3-5 个英文关键词，按这个 yaml 模板格式输出。"

全程不用自己动脑。

然后在 `config/settings.yaml` 里改一行：

```yaml
active_domain: "my_field"   # 你的文件名（不含 .yaml）
```

如果暂时不想配飞书和邮箱，也可以把推送渠道改为仅 Issues：

```yaml
push_channels: ["issues"]
```

#### 第三步：填密钥，跑一次验证（2 分钟）

进你自己的仓库 → Settings → Secrets and variables → Actions → New repository secret，填入：

| Secret 名 | 值 | 是否必需 |
|---|---|---|
| `DEEPSEEK_API_KEY` | `sk-xxxx` | ✅ 必需 |
| `FEISHU_WEBHOOK` | `https://open.feishu.cn/...` | 飞书推送时才要 |
| `SMTP_HOST` | `smtp.163.com` | 邮件推送时才要 |
| `SMTP_FROM` | `你的邮箱@163.com` | 邮件推送时才要 |
| `SMTP_TO` | `你的邮箱@163.com` | 邮件推送时才要 |
| `SMTP_PASSWORD` | `你的邮箱授权码` | 邮件推送时才要 |

全部填完后 → Actions 标签 → Daily Digest → Run workflow。

**等 4-5 分钟**（抓取 + LLM 打分 + 翻译 + 摘要生成），然后检查飞书/邮箱/Issues。收到了，就搞定了。

从此之后，**每天早上 9:00 自动推送，每周一 10:00 额外发周报趋势地图**。你什么都不用管，电脑关着也能收到。

---

## ✂️ 背后的技术方案（给想了解原理的人）

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│  arXiv API   │ --> │  LLM 相关性打分 │ --> │  LLM 翻译+摘要   │ --> │  飞书/邮件    │
│ (cs.RO/CV/LG)│     │  + 子方向多样性 │     │  + 深度解读       │     │  /Pages推送   │
└─────────────┘     └──────────────┘     └─────────────────┘     └──────────────┘
      GitHub Actions 定时触发：每天 8:50 启动处理，9:00 准时发送
```

- **arXiv API**（`arxiv` Python 包）按你定义的子方向关键词分别抓取
- **去重**：SQLite 记录已推送论文 ID，同篇不重复推
- **LLM 打分 + 多样性选取**：DeepSeek 给每篇论文打 1-10 分，然后每个子方向各取 1 篇最高分，确保不单一方向霸屏
- **LLM 翻译 + 深度解读**：完整中文翻译 + 背景知识 + 方法拆解 + 个人视角点评
- **多通道推送**：飞书卡片消息 / SMTP 邮件 / GitHub Pages 归档 / GitHub Issues
- **每周汇总**：宽松抓取全领域、统计各子方向热度、LLM 做跨论文趋势总结
- **代码行数**：约 1000 行 Python，其中跟领域相关的部分为 **0 行**

---

## ✂️ 结尾

这套系统跑了一周之后，我对"具身智能"这个领域的认知从"偶尔看到一篇"变成了"能说出 8 个子方向各自在发生什么"。这就是每天 0-5 篇精选 + 每周趋势地图的累积效应——**不是读更多论文，而是有策略地筛选信息入口。**

- ⭐ 觉得有用？欢迎 Star：[github.com/LR0625/paper-digest-agent](https://github.com/LR0625/paper-digest-agent)
- 🔧 想适配自己方向？按照上面的 3 步走，5 分钟搞定
- 💬 改出了自己的领域包？欢迎提 PR 加到 `domains/` 目录，攒一个"领域包市场"，让别人直接用现成的
- 🐛 遇到问题？去 Issues 提

---

*一个人盯论文很累，让 Agent 替你盯，你只负责判断哪些值得深入。*

*—— 每天早上 9:00，飞书见。*
