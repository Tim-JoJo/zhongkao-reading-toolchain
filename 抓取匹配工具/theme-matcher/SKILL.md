---
name: theme-matcher
description: Use when the user wants to find articles on an external question bank website (组卷网/学科网 etc.) whose themes match a given source reading article at a specified similarity threshold. Extracts the baseline theme, maps it to knowledge-point nodes, crawls candidate list pages, judges similarity (dimension-aware), writes matches to JSON, and opens pages for manual add-to-basket. Triggers on: 找相似文章, 匹配文章, 相似度, 试题篮, 组卷网, zujuan, 找同主题, 主题匹配.
---

# 主题匹配器 — 题库网站找相似文章

## 核心原则

把一篇基准文章（通常是 Part1 生成的中考阅读）作为"主题基线"，在题库网站（如组卷网 zujuan.xkw.com）按**主题维度**（而非表面关键词）寻找相似度 ≥ 阈值的文章。匹配维度由 Claude 语义判断，工具提供抓取/提取支撑。

本 Skill 负责"找文章 + 记录 + 打开页面"。加试题篮等需登录操作由用户手动完成。

## 外部依赖

- `browser-mcp`（CDP 通用抓取）—— 见 `../browser-mcp/README.md`（本分发包内同级的 `browser-mcp` 目录）
- 本地抓取脚本（若 browser-mcp 未注册 MCP 时退化用）：`../browser-mcp/_cdp_batch.py`、`../browser-mcp/_cdp_fetch.py`

## 输入

- 基准文章：本地 docx / 文本 / 或已经解析的内容
- 目标网站：默认组卷网 zujuan.xkw.com（可换成任意网站，抓取工具兼容）
- 相似度阈值：默认 70%
- 题型限定：如"任务型阅读/短文填空/选词填空"（可选）

## 工作流

### 1. 建立主题基线

用 `mineru-open-mcp__parse_documents`（或直接读 docx）解析基准文章，提取：

- **主题范畴**：文章讲什么（说明文/记叙文/议论文）
- **核心脉络**：主线逻辑（时间线/因果/对比/问题解决）
- **匹配维度**：从哪个"维度"判断相似——文化传播 / 消费心理 / 动物演化 / 环保 等

> 关键：相似度不是看表面关键词，而是看**维度**。例如"辣椒酱走向全球"和"奶茶出海美国"共享"文化传播"维度。维度判断要跟用户确认，用户常有更好的直觉。

### 2. 定位知识库目录

目标网站有主题树（如组卷网的 zsdXXXX 知识点树）时：

1. 抓知识树根页，解析出节点层级（level / id / title / href）
2. 从大类（如 人与自我/人与社会/人与自然）往下找最贴合的节点
3. **优先找"维度"对应的节点**，不是表面主题对应的节点
4. 向用户报告已查过的节点和结果，用户可能指出更贴切的目录

### 3. 抓列表页

目标节点的列表页 URL 模式：`<base>/czyy/zsd<id>/qt<type>/`（zujuan 常见题型：
`qt1216o2`=任务型阅读、`qt1213o2`=短文填空、`qt1210o2`=选词填空）。

用 `browser-mcp` 的 `batch_fetch` 抓取候选列表页，或退化用 `../browser-mcp/_cdp_batch.py`：

```bash
printf "%s\t%s\n" "URL1" "out1.html" "URL2" "out2.html" > tasks.txt
python ../browser-mcp/_cdp_batch.py < tasks.txt
```

### 4. 提取候选文章概要

从列表页 HTML 提取每篇的 overview（文章大意），写入文件供阅读筛选：

```bash
python -c "
import re
html = open('page.html', encoding='utf-8').read()
ids = re.findall(r'3q(\d{8})\.html', html)
blocks = re.findall(r'class=\"art-overview\"[^>]*>(.*?)</', html, re.S)
# 清洗、按序配对 id 和 overview，写入 txt
"
```

> 终端显示中文可能乱码（Windows），**把提取结果写文件再用 Read 读**，文件是 UTF-8 正确的。

### 5. 判定相似度

对照主题基线的**匹配维度**，逐篇评估：

- ≥ 阈值：纳入候选
- 略低于阈值（如 60-65%）：列出，说明差异，让用户决定是否放宽
- 明显不相关：跳过

**诚实评估**：宁缺毋滥。维度错位（如"动物科普" vs "动物演化研究"）即使表面都是动物也达不到 70%。查遍最可能的目录后若仍无 ≥ 阈值文章，如实报告"该主题在题库中冷门"，把最接近的列给用户决定。

### 6. 用户确认后写入 JSON

把选中的文章写入匹配数据文件（如 `zujuan_fetched_data.json` 的 `matches[]`）：

```python
match = {
    "id": "题目ID",
    "url": "https://zujuan.xkw.com/3q<ID>.html",
    "question_type": "任务型阅读/短文填空/选词填空",
    "knowledge_point": "节点名 (zsdXXXX)",
    "overview": "文章大意",
    "match_reason": "维度匹配的理由（为什么算匹配）",
    "similarity": 0.7,  # 0~1
}
d["matches"] = [m for m in d.get("matches", []) if m["id"] != "<ID>"]
d["matches"].append(match)
```

### 7. 打开页面供手动操作

加试题篮需要登录，用 `browser-mcp__open_in_browser`（或直接调 Chrome）打开页面，让用户手动加。

## 失败模式与 Fallback 表

| # | 触发信号 | 第一选择 | 备用 |
|---|---------|---------|------|
| 1 | `browser-mcp` 未注册 / CDP 连接失败 | 退化为本地脚本 `../browser-mcp/_cdp_batch.py` / `_cdp_fetch.py` | 手动用 Chrome 打开列表页另存 HTML，再用 Read 读 |
| 2 | Aliyun WAF「已阻断」拦截（requests / 无头 Chrome） | 改用真实 Chrome + `--remote-allow-origins=*` + websocket 抓取 | 换一个目标节点/URL 重试；仍失败则把候选页 URL 交给用户手动打开 |
| 3 | 目标网站没有主题树（非组卷网） | 跳过知识树定位，直接用站点搜索词抓列表页 | 问用户要该站的分类/标签 URL |
| 4 | 该节点下候选文章过少，或全部 < 阈值 | 检查相邻（上下级）节点，换更贴近「匹配维度」的节点 | 列出 60-65% 的接近项让用户决定是否放宽阈值 |
| 5 | 抓取结果中文乱码 | 中文分析结果一律写文件再用 Read 读（UTF-8 正确） | 用 python 显式 `encoding='utf-8'` 重新解码后写文件 |
| 6 | 批量抓取脚本报错（tasks.txt 格式错 / 超时） | 检查 `printf "%s\t%s"` 的 tab 分隔与 URL 有效性，单页重试 | 拆成小批次逐页抓，逐页确认输出非空 |
| 7 | 维度判断与用户分歧 | 先听用户直觉改维度（用户常更准） | 把两种维度的候选差异列出来让用户选 |
| 8 | 匹配结果写入 JSON 后需要撤回 | 按 id 移除旧记录再 append（见步骤 6 的幂等写法） | 手动编辑 JSON，确认 id 无重复 |

## 反例与黑名单（不要这样做）

| # | 不要做 | 后果 | 应该 |
|---|--------|------|------|
| 1 | 用表面关键词重合度判断相似 | 关键词同但维度错位（动物科普 vs 动物演化）仍远低于阈值，污染候选 | 按匹配维度判断，维度先跟用户确认（见步骤 1/5） |
| 2 | 用 requests / 无头 Chrome 抓组卷网 | Aliyun WAF 直接「已阻断」，白费时间 | 真实 Chrome + `--remote-allow-origins=*` + websocket（见失败模式表 2） |
| 3 | 依赖终端打印中文分析结果 | Windows 终端乱码，读到的不是真数据 | 写文件再 Read，UTF-8 正确（见步骤 4） |
| 4 | 找不到 ≥ 阈值文章就硬凑「差不多」的 | 维度错位匹配会误导选题，宁缺毋滥 | 如实报告「题库冷门」，列 60-65% 近似项让用户决定（见步骤 5） |
| 5 | 擅自放宽相似度阈值或改口径 | 用户按 70% 阈值决策，静默放宽等于篡改筛选标准 | 明确告知差距，由用户拍板（见失败模式表 4） |
| 6 | 未经确认就写 JSON / 直接覆盖 matches 旧记录 | 覆盖或重复 id 会丢数据 | 按 id 移除旧记录再 append 的幂等写法（见步骤 6） |
| 7 | 同一节点反复重抓同一列表页 | 重复抓取耗时且易触发限流 | 沿知识树换相邻节点；单页失败拆小批次（见失败模式表 6） |
| 8 | 用户指出更贴切目录/维度时仍坚持原方案 | 用户直觉常更准（维度优先原则），坚持会偏离目标 | 先听用户直觉改维度，列出两案差异让用户选（见失败模式表 7） |

## 已固化的经验

- **CDP 才是唯一绕过 Aliyun WAF 的方法**：requests 和无头 Chrome 都被"已阻断"拦截，真实 Chrome + `--remote-allow-origins=*` + websocket 才行
- **Windows 终端中文乱码**：所有中文分析结果写文件再 Read，不要依赖终端输出
- **知识点树驱动探索**：zujuan 有完整知识树，沿 `zsdXXXX` 节点逐层抓取即可获得（见步骤 2），按树找节点比盲搜高效
- **维度优先于关键词**：用户会提示更准的维度（如"盲盒和锚定偏见都是 mental 维度"），匹配思路要跟着用户的直觉走
- **相似度判断要透明**：给出"为什么算/不算"的理由，让用户能复核
