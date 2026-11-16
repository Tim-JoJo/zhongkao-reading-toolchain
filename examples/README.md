# 示例产物

工具链端到端跑出来的真实交付物，未作修饰——部署前先看效果可以直接打开这几个文件。全部在 `samples/` 目录。

## 文章 + 五道选择题（生成工具产物）

每篇含改写短文（带中文注释）、A–D 五道选择题、Answer Key 与逐题解析；同名 `N.json` 是导出时的指标记录（`all_pass`、词数、覆盖率、超纲词等）。

| 编号 | 标题 | 批次 | 词数 | 覆盖率 | 句均 / P90 | 超纲词 |
|---|---|---|---|---|---|---|
| [#100](samples/100-Machines-That-Catch-the-Wind.docx) | Machines That Catch the Wind | 手动批次 · VOA 素材 | 308 | 95.24% | 14.7 / 22 | 7 |
| [#210](samples/210-Sea-Otters-Small-Hunters-That-Save-the-Shore.docx) | Sea Otters: Small Hunters That Save the Shore | 无人值守批次 · VOA 素材 | 293 | 96.11% | 13.3 / 17 | 7 |
| [#275](samples/275-The-Long-Road-of-the-Little-Zipper.docx) | The Long Road of the Little Zipper | 无人值守批次 · Wikipedia 素材 | 318 | 96.11% | 13.8 / 20 | 7 |

三篇均 `all_pass`（词数 ≤ 350、覆盖率 ≥ 95%、句长达标）。「无人值守批次」指 2026-09-12 夜间批量生成、无人工介入的产物。

## 二卷追加样例（追加工具产物）

[samples/275-The-Long-Road-of-the-Little-Zipper-含二卷追加.docx](samples/275-The-Long-Road-of-the-Little-Zipper-含二卷追加.docx) 在上面 #275 的基础上，用追加工具按 [`spec示例.json`](../阅读理解题目追加工具/spec示例.json) 在文末追加了一道阅读单选（含导语、答案与逐题详解），排版规则自动套用。

## 来源与许可

- 素材改写自 VOA Learning English（公有领域）与 Simple English Wikipedia（CC BY-SA），输出为 AI 辅助生成内容，正式用于命题或发布前须经人工终审。
- 示例文件随仓库采用 [PolyForm Noncommercial 1.0.0](../LICENSE) 协议。
