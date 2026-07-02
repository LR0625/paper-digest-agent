# 📄 paper-digest-agent

> 一个**领域无关**的 arXiv 论文每日速递工具。你只需要写一个 YAML 配置文件，它就能自动抓取、打分、摘要、推送。
>
> 默认搭载「**具身智能与机器人学习**」领域包开箱即用，但它**不只限于具身智能**——改成 NLP、CV、强化学习、多模态……都只需要改一个文件。

## ✨ 为什么是它？

GitHub 上 arXiv 论文推送工具已经有不少了，但大多有这些问题：

| 常见问题 | 本项目的做法 |
|---|---|
| 关键词越热门越霸屏，单一方向刷屏 | **子方向多样性覆盖**：8+ 个子方向各推 1 篇，保证你看到的是全领域地图而非单一深井 |
| 纯英文，国内用户友好度低 | **中文优先**：结构化中文摘要 + 原文中英对照翻译 |
| 默认读者是领域内行，堆术语 | **面向学生/新人**：每篇论文带"背景知识"解释，帮读者理解前置概念 |
| 代码和领域关键词写死在一起 | **引擎与领域包完全解耦**：换方向只改一个 YAML，不碰一行 Python |
| 推送就没了，没有历史归档 | **GitHub Pages 免费归档**：每天自动生成可分享链接的网页版历史记录 |
| 部署门槛高（需要各种密钥） | **零配置尝鲜**：支持 GitHub Issues 作为推送渠道，fork 完立刻能看到效果 |

## 🚀 快速开始（3 分钟接入）

> ⚠️ **重要**：使用 Template 创建仓库后，你需要修改 **3 样东西**才能让系统为你工作：
> 1. **API 密钥**——飞书/邮箱是绑定我个人账号的，DeepSeek 花的也是我的钱，你必须换成自己的
> 2. **研究方向**——默认是"具身智能与机器人学习"，你想关注什么方向需要自己定义
> 3. **激活配置**——告诉系统加载你刚才写的领域文件

- [ ] **1. Use this template** — 点击右上角绿色 "Use this template" → "Create a new repository"（⚠️ 不是 Fork，这样你的仓库跟我的完全独立）
- [ ] **2. 定义你的研究方向** — 复制 `domains/_template.yaml` 并按你的领域编辑（详见下方说明）；然后修改 `config/settings.yaml` 中的 `active_domain` 指向它
- [ ] **3. 填入你自己的 API 密钥** — 仓库 Settings → Secrets and variables → Actions，添加：
  - `DEEPSEEK_API_KEY`（**必需**，去 [platform.deepseek.com](https://platform.deepseek.com) 注册充值后获取，花你自己的钱😂）
  - `FEISHU_WEBHOOK`（飞书推送时需要，用**你自己群**的机器人 webhook，别用我的）
  - `SMTP_HOST` / `SMTP_FROM` / `SMTP_TO` / `SMTP_PASSWORD`（邮件推送时需要，用**你自己邮箱**的授权码）
- [ ] **4. 手动触发测试** — 进入 Actions → Daily Digest → "Run workflow"，等 4-5 分钟后检查是否收到推送
- [ ] **5. 完成** — 每天北京时间 9:00 自动推送，周一 10:00 额外发周报趋势地图

> 💡 **零配置尝鲜**：如果你暂时不想配任何密钥，编辑 `config/settings.yaml`，把 `push_channels` 改为 `["issues"]`，然后手动触发一次 workflow。论文日报会自动出现在仓库的 Issues 里——完全不依赖外部服务。

## 📁 项目结构

```
paper-digest-agent/
├── .github/workflows/
│   ├── daily.yml              # 每日定时任务（北京时间 9:00）
│   └── weekly.yml             # 每周汇总（每周一 10:00）
├── domains/                   # 【领域包】你只需要改这一层
│   ├── embodied_ai.yaml       # 默认领域：具身智能/机器人（8个子方向）
│   ├── _template.yaml         # 空白模板，复制后改成你自己的方向
│   └── README.md              # 领域包编写指南
├── config/
│   └── settings.yaml          # 全局设置（与领域无关）
├── src/                       # 【通用引擎】换领域不需要碰
│   ├── fetch_arxiv.py         # 抓取 + 过滤 + 多样性选取
│   ├── dedup.py               # SQLite 去重
│   ├── summarize.py           # DeepSeek 结构化摘要 + 翻译
│   ├── push_feishu.py         # 飞书 Webhook 推送
│   ├── push_email.py          # SMTP 邮件推送
│   ├── push_pages.py          # GitHub Pages 静态归档
│   ├── push_issues.py         # GitHub Issues 推送（零密钥）
│   ├── weekly_digest.py       # 周报：全景地图 + 趋势总结
│   └── conference_watch.py    # 会议放榜专题（半自动）
├── data/
│   └── seen_ids.db            # 已推送论文记录（自动维护）
├── requirements.txt
└── LICENSE                    # MIT
```

## 🔧 自定义你的领域

这是本项目的核心设计——**换方向只需要改一个 YAML 文件，不碰任何 Python 代码**。

### 3 步适配你自己的方向

```bash
# 1. 复制模板
cp domains/_template.yaml domains/my_field.yaml

# 2. 编辑你的领域包（用任何文本编辑器）
#    - domain_name: 你的领域中文名
#    - categories: 要抓取的 arXiv 分类
#    - subfields: 拆分成 6-10 个子方向，每个填英文关键词
#    - priority_labs: 你重点关注的实验室

# 3. 激活
#    编辑 config/settings.yaml，把 active_domain 改成 "my_field"
```

### 快速头脑风暴子方向划分

如果你不确定怎么拆分，可以把 `_template.yaml` 的内容发给 Claude Code 或 ChatGPT：

> "我想关注 [你的领域]，帮我拆分成 8 个左右的子方向，每个子方向给 3-5 个英文关键词，用于在 arXiv 上搜索论文。请按 _template.yaml 的格式输出。"

详细说明见 [`domains/README.md`](domains/README.md)。

## 📊 输出示例

### 每日快讯（飞书卡片 / 邮件）

每条推送包含：

- **子方向标签** + **相关性评分**
- **一句话简介**（20 字以内抓住核心）
- **背景知识**（新人友好的前置概念解释）
- **核心问题 / 方法 / 实验结果 / 局限性**
- **个人视角点评**（在领域坐标系中的位置、落地价值）
- **中文标题+摘要翻译**

### 每周汇总

- 🌍 **全领域热度地图**：本周各子方向论文数量分布
- 🔥 **趋势总结**：跨论文观察、活跃团队、值得关注的方向

## ⚙️ 配置说明

### `config/settings.yaml` 主要配置项

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `active_domain` | 激活的领域包文件名（不含 .yaml） | `embodied_ai` |
| `daily_limit` | 每日推送数量上限 | `5` |
| `relevance_threshold` | DeepSeek 相关性最低分 (1-10) | `7` |
| `diversity_mode` | 是否启用子方向多样性覆盖 | `true` |
| `push_channels` | 推送渠道列表 | `["feishu", "email", "pages"]` |

### 环境变量 / GitHub Secrets

| Secret | 必需？ | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | ✅ 必需 | DeepSeek API 密钥 |
| `FEISHU_WEBHOOK` | 飞书推送时需要 | 飞书群机器人 Webhook URL |
| `SMTP_HOST` | 邮件推送时需要 | SMTP 服务器地址 |
| `SMTP_FROM` | 邮件推送时需要 | 发件邮箱 |
| `SMTP_TO` | 邮件推送时需要 | 收件邮箱 |
| `SMTP_PASSWORD` | 邮件推送时需要 | 邮箱 SMTP 授权码 |

## 🗺️ 默认领域包：具身智能（8 个子方向）

| 子方向 | 说明 |
|---|---|
| VLA 与端到端策略 | 视觉-语言-动作模型、通用机器人策略 |
| 灵巧操作与抓取 | 机械臂操作、双手协同、触觉操作 |
| 导航与场景理解 | 视觉导航、SLAM、语义建图 |
| 运动控制（足式/人形） | 四足/双足机器人全身控制 |
| 仿真到真机 / 强化学习 | Sim-to-Real、RL 训练框架 |
| 世界模型与规划 | 基于模型的机器人学习、任务规划 |
| 多模态感知 | 触觉传感、3D 场景表征 |
| 人机交互与协作 | 人机协作、辅助机器人 |

## 🎯 与同类项目的对比

| | paper-digest-agent | ArxivDigest | ChatDailyPapers | gpt_paper_assistant |
|---|---|---|---|---|
| 领域无关 | ✅ 一个 YAML 切换 | ❌ 需改代码 | ⚠️ 只改仓库名 | ❌ 需改代码 |
| 子方向多样性 | ✅ diversity_mode | ❌ 纯得分排序 | ❌ 无 | ❌ 无 |
| 中文优先 | ✅ | ❌ | ⚠️ 附加功能 | ❌ |
| 新人友好 | ✅ 背景知识层 | ❌ | ❌ | ❌ |
| 零密钥尝鲜 | ✅ GitHub Issues | ❌ | ❌ | ❌ |
| GitHub Pages | ✅ | ❌ | ❌ | ❌ |
| 全景周报 | ✅ 趋势+热度地图 | ❌ | ❌ | ⚠️ 简单汇总 |

## 📅 后续迭代方向

- [ ] Semantic Scholar 引用数辅助排序
- [ ] 周报热度分布可视化（柱状图）
- [ ] 更多会议数据源适配（OpenReview / DBLP / 官网爬虫）
- [ ] "深度模式"：对特定子方向加权跟踪
- [ ] 支持更多 LLM（OpenAI / Claude 等）

## 📄 License

MIT — 自由使用、修改、分发。

---

> **设计理念**：这个工具的目标不是"找到今天最热的那篇论文"，而是**帮你建立对整个领域的认知全景**。每天 0-5 篇，覆盖不同子方向，宁缺毋滥。周报的地图 + 趋势比日报的单篇推送更值得精读。
