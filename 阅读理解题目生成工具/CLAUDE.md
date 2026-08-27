# 阅读理解题目生成工具 — 项目约定

本文件是工具链的操作约定（源自对话中用户明确提出的要求），参与工具链工作时必须遵守。涉及三个 Skill：`zhongkao-article-writer`（Part1 文章写作）、`zhongkao-question-generator`（Part2 题目生成）。

---

## 1. 报告结构（report-with-article / report-structure-exclusions）

文章完成指标审校后，导出**报告 Word**（用 python-docx 生成，可调用 `src/exporter.py` 的 `run_export_report_docx`）：包含任务配置、事实提取清单与中心思想、**生成文章全文（段内标注）**、模块匹配、指标报告、长难句清单（含种类）、生词中文注释、写作说明、质量检查，保存至 `<用户下载目录>\文章报告\`（目录不存在自动创建）。

**不导出纯文章 Word**（不再调用 `mcp__zhongkao-mcp__export_article_docx`）；文章正文由 Part2 的题目 Word（`export_docx`）承载。

报告中的**文章全文必须带标注**，标注手法包括高亮与段尾批注式说明。报告内**必须含"荧光标注图例"一节**，逐条说明各高亮色的含义，放在"生成文章全文"节之前，让读者在阅读正文前先看懂标注。

**荧光标注图例（三种高亮色，含义如下）：**

| 标注类型 | 高亮色（python-docx） | 含义 | 判断标准 |
|---|---|---|---|
| 事实来源 | 黄 `WD_COLOR_INDEX.YELLOW` | 该句承载从原文提取的客观事实 | 句子包含原文中的人物、时间、地点、数字、过程、结果、因果等可核验信息点；不含比喻、修饰或评价性语言 |
| 长难句 | 粉 `WD_COLOR_INDEX.PINK` | 该句为长难句，并说明类型 | 句子含多层从句/非谓语/并列复合等复杂结构；类型在"长难句清单"节逐句说明（定语从句/状语从句/名词性从句/非谓语动词/并列复合句等） |

注：一句可同时属于多个类别（如既是事实来源又是长难句），报告正文允许对同一句叠加使用高亮；图例中按该句最主要的属性着色即可。

**改编正文不得逐字引用原文任何句子**（硬性规则）；导出前须通过 `mcp__zhongkao-mcp__check_original_quotes` 检测（见 Part1 SKILL 第 7 步）。报告内文章全文字体格式与 Part2 题目 Word 中的正文一致（Arial 12pt、首行缩进 0.75cm、1.5 倍行距、中文字体微软雅黑；标题 Arial 20pt 加粗居中）。

报告不单独开"改编正文"一节（文章全文已在报告内带标注展示），不需要"专名与引述处理"一节。质量检查只写结论（严重项/工程带宽/Humanizer/地道性/最终状态）。

## 2. 静默输出（output-silence）

文章/题目导出后，**聊天界面只报告**"输出完成。`文件名.docx`"，不展示文章全文、指标报告、长难句分析、生词注释等详细内容。所有详细信息写入 Word 文档。

## 3. 中文注释最后一步加入（annotation-last-step）

写文章时，正文的中文注释（如 `urgency（紧迫）`）放在**导出 Word 前的最后一步**才加入。`check_passage` 指标检查始终用**无注释正文**。

- 原因：注释里的括号汉字会被 vocab-checker 分词器误判为生词（`urgency（紧迫）and` 会被当一个词元），导致覆盖率不达标。
- 注释只加在**词族首次出现的词**上（`urgent`/`urgency` 同词族只注释一个）。
- 注释数量 = **超纲词总数（唯一词元）的 50%–60%**（动态范围）。

流程顺序：① 写正文 → ② 用无注释正文跑 `check_passage` 迭代至全部通过 → ③ 导出前最后一步加中文注释 → ④ 正文（带注释）供 Part2 题目 Word 导出，并写入报告 Word。

## 4. Part2 答案解析（part2-export-explanations）

Part2 生成题目并导出 Word 时，调用 `mcp__zhongkao-mcp__export_docx`（或 `run_export_docx`）必须传 `explanations` 参数（第 1 条为导语全文总结、不加编号、独立成段，其余逐题详解与题目一一对应），渲染在 Answer Key 之后。explanations 内容：正确答案、原文证据、干扰项错误点（中英文均可）。**解析正文按真题对齐的「导语 + 逐题详解」结构撰写（引证两段式：定位短语 + 逐字引原文 + 一句话下结论），详见 `zhongkao-question-generator/references/explanation-writing.md`；题干按题型套用真题固定句式，见 `question-design.md`「题干模板库与解析方法」；题池分布与类型不变。**

**解析文本不带数字标号**：`explanations` 第 1 条为**导语**（全文总结，不加编号、导出器自动独立成段并后接空行）；其余每条只写逐题详解内容本身，不带 `1.` / `2.` 前缀；导出器从 `1.` 开始编号（同题干 stem 的约定，避免 `1. 1.` 重复）。导出器已做防御：`run_export_docx` 渲染解析时自动剥掉自带编号。

## 5. 档位需用户选择（ask-level-choice）

执行工具链（文章写作/题目生成）时，若会话中用户未指定档位，必须询问用户选择档位（standard / extended），**不能静默默认 standard**。

本工具只面向**九年级**，年级固定为 9，不提供其他年级选项。

## 6. MCP 配置位置（mcp-config-location）

工具链 MCP server 配置在工具包根目录 `.mcp.json`（由工作区根加载）。部署时把 `.mcp.json` 中的 `<工具根目录>` 替换为本工具包的实际绝对路径，并按接收方机器的 python 环境修改 `command`。三个 server：

- `vocab-checker` → `<工具根目录>/Part1-文章改写/vocab-checker/mcp_server.py`
- `zhongkao-mcp` → `<工具根目录>/Part1-文章改写/zhongkao-mcp/mcp_server.py`
- `mineru-open-mcp` → `python -m mineru_open_mcp.cli`（可选，需先 `pip install mineru-open-mcp`；用于解析 PDF / 网页等输入材料，未安装时跳过此 server 不影响其他功能）

若 MCP 工具（`mcp__zhongkao-mcp__*`、`mcp__vocab-checker__*`）在会话中不可用：先检查根 `.mcp.json` 路径是否仍指向真实代码；路径正确后需**重启 Claude Code 会话**才会重新加载。当前会话未加载时可直接用 Python 调用 `Part1-文章改写/zhongkao-mcp/src/` 下的 `checker.py`、`exporter.py` 等模块绕过 MCP。

## 7. 输出目录需用户指定（ask-output-dir）

调用导出工具（报告 Word、题目 Word）时，若用户会话中**未明确指定输出目录**，**必须先询问用户**输出路径，待用户给出后再导出；不得静默默认任何默认目录。

- 报告 Word 与题目 Word 的目录**分别确认**。
- 用户指定路径优先；用户明确表示采用默认时才用默认目录。
- 覆盖前述 SKILL 中写的默认路径说明（如 `<用户下载目录>\文章报告\`、`<改编版>` 目录），这些仅为「用户未指定时的默认建议」，不是静默默认值。

## 8. 全文词数 350 为硬性门槛（word-count-hard-limit）

`check_passage` 的 `word_count` 带宽已设为 `[0, 350]`（标准档与拓展档一致）。**正文词数超过 350 即返回 `review_required`、`all_pass` 为 false，属硬失败，不得交付。**

- 全文词数口径：正文，不计标题、题干、选项和中文注释。
- 写作阶段以此为硬约束：正文起草即控制 ≤350 词，避免交付阶段被迫压缩。
- Part1 未达 all_pass（含 word_count 超标）不得进入导出；Part2 承接超 350 词正文时回 Part1 压缩，不得带超限正文出题导出。
- 覆盖率、平均句长、P90 仍按「需复核」处理；**word_count 例外，不做复核、必须硬性达标**。

## 9. 排序题标号规范（ordering-marks-format）

改编版题目中，排序题（Q4，`type == "ordering"`）的事件标号统一用 **①②③④**（每事件一行），不用 `a. b. c. d.` 字母；选项序列同步为 ①~④ 序列（如 `A. ②③①④`）。符号 ①②③④ 在 Word 中用**苹方-简**字体渲染（系统已装 pingfang-sc-regular.ttf），每行一个事件，换行须渲染为标准 Word 换行。

- 出题端：`stem` 用 `\n` 连接事件行，事件行前缀为 `①.` `②.` `③.` `④.`；`options` 序列项为 `A. ②③①④` 形式。
- 校验端：`validate_questions` 对 ordering 题检查 `stem` 是否含 `①`、`②` 事件行（不再检查 a./b.）。
- 导出端：`run_export_docx` 对 ordering 题续行换行用 `<w:br/>`，事件标号 run 的 ascii/hAnsi/eastAsia/cs 全部设为「苹方-简」（仅设 eastAsia 时 ① 仍按 Arial 渲染）；选项里的序列标号同样按苹方-简拆分。其余文字保持微软雅黑/Arial。
- 参考实现：`Part1-文章改写\zhongkao-mcp\src\exporter.py`（渲染）、`src/validator.py`（校验）。

## 10. 工作流门禁（workflow-gate）

工具链内置一个**跨 agent、跨会话**的工作流状态机（纯 MCP 工具 + 磁盘 JSON 状态文件，不依赖某一家 agent 的专属机制）。`zhongkao-mcp` 的 `check_passage` / `draw_blueprint` / `validate_questions` 会自动把完成情况写入 `<工作目录>/.zhongkao_workflow.json`（或环境变量 `ZHONGKAO_WORKFLOW_FILE` 指定的路径）。`export_docx` 导出前检查状态，缺少硬性步骤时**直接拒绝导出**并返回缺步清单：

- 未调用 `draw_blueprint`（Part2 硬性步骤，未抽蓝图不得导出）
- `validate_questions` 未通过（`all_pass != true`，校验不过不得导出）
- 正文无中文注释，但 `check_passage` 检出超纲词（Part1 交付给 Part2 的应是**带注释版**正文）

被拦截时按提示补做对应步骤，**不要绕过拦截强行导出**。状态管理工具：

- `workflow_init(level)` — 开新任务时初始化（清空旧记录 + 记录档位，level 为 standard / extended）
- `workflow_status()` — 查看已完成 / 待办步骤
- `workflow_reset()` — 清空状态

开新任务前先 `workflow_init` 或 `workflow_reset`，避免上一个任务的记录干扰本次导出门禁。跨会话/跨 agent 使用同一工作目录时共享同一状态文件。
