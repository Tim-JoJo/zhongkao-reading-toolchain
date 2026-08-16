# 中考阅读题目生成工具（可分发版）

把一篇英文文章（新闻/杂志/科普/记叙文等）**改写为九年级中考阅读文章**并**生成配套五道选择题**，输出带排版的 Word 文档（题目 + 答案 + 解析）。

本包为**可分发版本**：不含本机写死的路径，对方拿到后按下方步骤配置即可在自己机器上用 agent 跑通。文档写给 **agent** 看——agent 负责引导最终用户使用。

## 工具构成

```
阅读理解题目生成工具-可分发版/
├── README.md                        ← 本文件：部署 + 使用指南（agent 先读这里）
├── CLAUDE.md                        ← 全局操作约定（agent 必须在任务开始时读取）
├── .mcp.json                        ← MCP 配置模板（把 <工具根目录> 换成实际路径）
├── requirements.txt                 ← 聚合依赖
├── Part1-文章改写/
│   ├── .mcp.json                    ← Part1 内部相对 MCP 配置（备用）
│   ├── zhongkao-article-writer/     ← Skill ①文章写作（SKILL.md + references/）
│   ├── zhongkao-mcp/                ← MCP server：指标检查 + 题目校验 + Word 导出（mcp_server.py + src/）
│   └── vocab-checker/               ← MCP server：生词/覆盖率检查（基于 2022 课标 2,795 词表）
├── Part2-题目生成/
│   ├── zhongkao-question-generator/ ← Skill ②题目生成（SKILL.md + references/）
│   └── rc-question-writing/         ← Skill ③阅读选择题题型参考（SKILL.md + references/）
└── reading-explorer-writing/        ← 内置依赖 Skill：教材体行文逻辑模块库（module-library.md 等）
```

**三个 Skill 的分工与顺序**：① `zhongkao-article-writer`（文章改写）→ ② `zhongkao-question-generator`（出题）。③ `rc-question-writing` 是题型库参考。Skill 不是安装在 `.claude/skills/` 的斜杠命令，而是**由 agent 按路径读取 SKILL.md 作为工作流指令**。

## 对方需要什么

- **Python 3.10+**（跑 MCP server；需要能 `pip install`）
- 一个**支持 MCP 的 agent**（Claude Code 等）
- （可选）**mineru-open-mcp**：用于把 PDF / 网页解析成文本输入；不装也能用，只是少了 PDF 输入通道

## 部署步骤（agent 按序执行）

### 1. 安装依赖

```bash
cd <工具根目录>
pip install -r requirements.txt
python -m spacy download en_core_web_sm     # 生词检查所需的词形还原模型
```

> 无 pip 权限时改用 `python -m pip install --user -r requirements.txt`。

### 2. 配置 .mcp.json

把包根目录 `.mcp.json` 复制到当前 Claude Code 项目的根目录，并把两处 `<工具根目录>` 替换为本工具包的实际绝对路径。路径分隔符正斜杠 `/` 与 Windows 双反斜杠 `\\` 均可（如 `C:\Users\me\阅读理解题目生成工具-可分发版\Part1-文章改写\vocab-checker\mcp_server.py`）。

配置成功后，会话里应出现这些工具：

- `mcp__zhongkao-mcp__check_passage` / `draw_blueprint` / `validate_questions` / `export_docx` / `export_article_docx`
- `mcp__zhongkao-mcp__workflow_init` / `workflow_status` / `workflow_reset`（工作流状态管理：记录各硬性步骤完成情况，`export_docx` 缺步时自动拦截）
- `mcp__vocab-checker__check_text` / `check_grade_level` / `check_article`

### 3. 可选：启用 mineru（PDF/网页解析）

```bash
pip install mineru-open-mcp
```

然后 `.mcp.json` 的 `mineru-open-mcp` server 用 `python -m mineru_open_mcp.cli` 启动（模板已配好）。不装则跳过该 server，不影响文章写作与出题。

### 4. 验证

```bash
# 确认 server 能启动（无报错即正常）
python -c "import sys; sys.path.insert(0, 'Part1-文章改写/zhongkao-mcp'); import mcp_server; print('zhongkao-mcp OK')"
python -c "import sys; sys.path.insert(0, 'Part1-文章改写/vocab-checker'); import mcp_server; print('vocab-checker OK')"
```

配置路径后若 MCP 工具未出现，重启 agent 会话即可。

## 使用方式（agent 引导用户）

工具只面向**九年级**（年级固定 9），两档：`standard`（标准档）/ `extended`（拓展档）。开始前**必须询问用户选档位**，不得静默默认。

### 工作流

1. **读约定**：先读 `CLAUDE.md`（报告结构、静默输出、注释最后一步加入、档位需确认、输出目录需确认、词数 350 硬门槛等全局规则）。
2. **文章写作**：读 `Part1-文章改写/zhongkao-article-writer/SKILL.md`，按其中工作流执行（提取事实 → 匹配行文模块 → 撰写 → 指标检查 `check_passage` → 追溯 → 导出报告 Word）。行文模块库在包内 `reading-explorer-writing/references/`，已内置。
3. **题目生成**：读 `Part2-题目生成/zhongkao-question-generator/SKILL.md`，`draw_blueprint` 抽五题蓝图 → 逐题编写 → `validate_questions` 校验 → `export_docx` 导出（含答案与解析）。
4. 交付时聊天界面只报告 `输出完成。文件名.docx`，细节都在 Word 里。

### 关键硬性要求（摘自 CLAUDE.md）

- `check_passage` 必须 `all_pass: true`，其中**正文词数 ≤ 350 为硬门槛**，超限不得交付。
- `draw_blueprint` 与 `validate_questions` 是出题硬性步骤，不得跳过。
- 报告/题目 Word 的输出目录**必须先问用户**，不得静默默认。
- 正文中文注释在导出前最后一步才加入，指标检查用无注释正文。
- **导出门禁自动兜底**：`export_docx` 在缺前置步骤（未抽蓝图 / 校验未 all_pass / 正文无中文注释）时会拒绝导出并提示缺步，agent 按提示补做后再导出，不要绕过。开新任务先用 `workflow_init` 或 `workflow_reset` 清空状态。

## 常见问题

- **`ModuleNotFoundError: spacy`**：依赖没装全，重跑部署第 1 步。
- **MCP 工具不出现**：`.mcp.json` 路径写错或 Python 路径不对 → 检查 `<工具根目录>` 替换是否正确，然后重启 agent 会话。
- **覆盖率偏低/偏高**：按 `check_passage` 返回的 `unknown_words` 逐词处理，重新运行直到通过。
