# 领域包编写指南

这是 `paper-digest-agent` 的领域配置层。你**不需要修改任何 `.py` 代码**，只需在这里定制你的领域即可。

## 快速开始（3 步）

1. **复制模板**
   ```bash
   cp domains/_template.yaml domains/my_field.yaml
   ```

2. **填写内容**：按下方说明修改你刚复制的文件

3. **激活**
   编辑 `config/settings.yaml`，将 `active_domain` 改为你的文件名（不带 `.yaml`）：
   ```yaml
   active_domain: "my_field"
   ```

## 字段说明

### `domain_name`
领域的中文名称，会显示在推送标题和 Pages 页面上。

### `categories`
要抓取的 arXiv 分类。参考 [arXiv 分类表](https://arxiv.org/category_taxonomy)。
常用组合示例：
- NLP/大模型：`["cs.CL", "cs.LG", "cs.AI"]`
- 计算机视觉：`["cs.CV", "cs.AI"]`
- 强化学习：`["cs.LG", "cs.AI", "cs.RO"]`

### `subfields`
你的领域下的子方向划分。每个子方向包含：
- **key**（如 `subfield_id_1`）：程序内部引用用的 ID，建议用英文/拼音
- **`label`**：显示用的中文名称
- **`keywords`**：该子方向的英文关键词列表，用于在 arXiv 摘要中匹配

> **提示**：如果你不确定怎么拆分子方向和写关键词，可以把 _template.yaml 的内容发给 Claude Code / ChatGPT，让它帮你头脑风暴你关注领域的子方向划分。

**子方向数量建议**：6-10 个。
- 太少 → 起不到"多样性覆盖"的效果
- 太多 → 每个方向的曝光过少

### `priority_labs`
你特别关注的实验室或机构的英文名称。命中这些机构的论文会优先展示，不受每日推送数量限制的挤压。

## 完整示例

见同目录下的 `embodied_ai.yaml`（具身智能/机器人领域）。
