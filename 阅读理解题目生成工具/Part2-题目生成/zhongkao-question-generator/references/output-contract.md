# 固定输出合同 — 题目生成

除非用户明确要求简版，按下列顺序交付。

## 1. 任务配置

- 档位：`standard | extended`
- 题数与选项数
- 文章标题

## 2. 题目蓝图

在正式题目之前输出：

| 题号 | 考查类型 | 对应能力 | 证据段落 | 证据跨度 | 证据句 | 预计难度 |
|---|---|---|---|---|---|---|

## 3. 选择题

按用户要求生成 3 或 4 个平行选项。题干语言不应比正文更难。

- **题干不带数字标号**：`stem` 字段只写题干本身（如 `How does the writer begin the article?`），不带 `1.` / `2.` 前缀；导出器自动编号，避免出现 `1. 1.` 重复标号。
- **排序题必须含事件**：`ordering` 题（Q4）的 `stem` 必须先用 ①/②/③/④ 列出各事件（每事件一行），再给选项序列（如 `A. ②③①④`）。事件列表用换行分隔（导出器自动渲染为题干续行、不加粗；标号 ①~④ 用苹方-简字体，换行渲染为 Word 换行，一行一个事件）。
- **题干多行写法**：排序题事件用 `\n` 连接在同一 `stem` 字符串中，例如：

  ```
  "Put the following events about Saturn's rings in the correct order.\n①. Small planets crashed into Saturn's moons.\n②. The pieces were pulled inward while their orbits tried to throw them away.\n③. The ice and rock pieces began to travel around the planet.\n④. The pieces settled into wide rings around Saturn."
  ```

## 4. 答案与解析

解析正文按**真题对齐的「导语 + 逐题详解」结构**撰写（详见 `explanation-writing.md`）。一组题目导出时：

- **导语**（每组一条）：一句话压缩全文——体裁判定 + 内容概括。
- **逐题详解**（每题一条）：`定位短语 + 逐字引原文 + 一句话下结论`（引证两段式）。

每题详解必须包含（导出正文）：

- 正确答案（作为详解结论句）
- 原文证据（定位短语 + 逐字引原文）
- 推理步骤（结论动词层级：说明/可知/因此/推知/最可能出自）
- 每个干扰项的错误点（"少而准"：多数只讲正确项即间接排除；易混题显式点出可验证否定）

难度等级为内部元数据，不进入导出正文（同 question-design.md「解析合同」）。

**解析文本不带数字标号**：`explanations` 第 1 条为**导语**（全文总结，如 `本文是一篇说明文，……`），**不加编号**；导出器自动将其渲染为独立段落并后接空行。`explanations` 其余条目为**逐题详解**，只写解析内容本身（如 `第X段"…"，可知…`），不带 `1.` / `2.` 前缀；导出器从 `1.` 开始编号。与题干同一条约定，避免出现 `1. 1.` 重复标号。

## 5. 质量检查

- 格式检查：选项数量、字母前缀、答案唯一性
- 题型覆盖：vocabulary_or_detail / inference / main_idea 必覆盖，外加 writing_technique 或 detail（Q1 按 30%/70% 二选一）、ordering 或 inference（Q4 按 80%/20% 二选一）
- 选项平衡：长度均衡、无绝对词泄露
- 题干规范：无过度宽泛的定位、否定词标注正确
- 答案分布：无连续 3 次同一选项
- 前后暗示：无题目间信息泄露

最终状态只能是：

- `可交付`
- `需人工复核`，并列出具体问题
