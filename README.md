# 中考英语阅读 AI 工具链

一套面向**九年级(中考)英语阅读**出题与组卷的本地工具链,包含三个可独立使用的工具,
由 AI agent(如 Claude Code / Claude Desktop)配合 MCP server 驱动。

三个工具串起来即一条完整流水线:

```
英文文章 ──► ① 生成改编文章 + 5 道选择题 ──► ② 追加组卷网二卷配套题目 ──► 排版 Word
                    │
                    └──► ③ 去题库网站抓取主题相似文章,补充题源
```

## 工具一览

| 工具 | 目录 | 作用 |
|------|------|------|
| **阅读理解题目生成工具** | [阅读理解题目生成工具/](阅读理解题目生成工具/) | 把一篇英文文章(新闻/科普/记叙文等)改写为九年级中考阅读文章,并生成配套五道选择题,输出带排版与解析的 Word。内含 3 个 Skill + 2 个 MCP server(指标检查 / 生词覆盖率)。 |
| **阅读理解题目追加工具** | [阅读理解题目追加工具/](阅读理解题目追加工具/) | 在改编版 docx 尾部追加组卷网配套题目(选词填空 / 7选5 / 语法填空 / 首字母填空 / 阅读问答 / 阅读单选),自动套排版规则。纯 Python,仅依赖 python-docx。 |
| **抓取匹配工具** | [抓取匹配工具/](抓取匹配工具/) | 通过真实 Chrome + CDP 绕过 Aliyun WAF,在题库网站(组卷网等)抓取与给定阅读文章主题相似的文章。含 `theme-matcher` 工作流 Skill。 |

## 快速开始

各工具目录内均有自己的 README,说明依赖安装、MCP 配置与使用方式:

- 生成工具:先读 [阅读理解题目生成工具/README.md](阅读理解题目生成工具/README.md),
  开始工作前必须再读其 [CLAUDE.md](阅读理解题目生成工具/CLAUDE.md)(操作硬性约定)。
- 追加工具:见 [阅读理解题目追加工具/README.md](阅读理解题目追加工具/README.md)
- 抓取工具:见 [抓取匹配工具/README.md](抓取匹配工具/README.md)

## 前置要求

- **Python 3.10+**(跑 MCP server 与脚本)
- **支持 MCP 的 agent**(Claude Code / Claude Desktop 等)
- 抓取工具另需**已安装的 Google Chrome**(用于 CDP)

## 工作原理简述

- **生成工具**:`zhongkao-article-writer` Skill 按「提取事实 → 匹配教材体行文模块 → 撰写 → 指标检查 → 导出报告」改写文章;
  `zhongkao-question-generator` Skill 按「蓝图 → 逐题编写 → 校验 → 导出」出题。指标检查含
  正文词数 ≤350 硬门槛、基于 2022 课标 2,795 词表的生词覆盖率等。
- **追加工具**:按 spec JSON(或交互式)把组卷网题目追加进 docx 尾部,自动处理首行缩进、空处下划线、答案块底纹等排版。
- **抓取工具**:`browser-mcp` 提供 `fetch_page` / `batch_fetch` / `open_in_browser` / `extract_items` 四个通用抓取工具;
  `theme-matcher` Skill 负责解析基准文章主题 → 定位知识点树节点 → 抓列表页 → 按维度判相似度 → 写匹配 JSON。

## 目录结构

```
zhongkao-reading-toolchain/
├── README.md                          ← 本文件
├── LICENSE                            ← MIT
├── .gitignore
├── 阅读理解题目生成工具/               ← 主工具:文章改写 + 题目生成
├── 阅读理解题目追加工具/               ← 二卷配套题目追加
└── 抓取匹配工具/                      ← 题库网站主题匹配抓取
```

## 许可

MIT License,见 [LICENSE](LICENSE)。
