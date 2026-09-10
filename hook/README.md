# hook —— 「容易遗漏/出错」点的自动校验

这些不是普通单元测试，而是把**已经踩过的坑**钉成回归锁：谁把旧问题改回来，这里必须变红。
每个文件对应一类真实事故，出处见各文件顶部 docstring。

## 怎么跑

```bash
pytest hook -q                 # 全部（装了 spacy 才跑蓝图种子扫描，否则自动跳过）
pytest hook -q -k doc          # 只跑文档一致性（纯文本，0.1s）
```

依赖：`pytest`（必需）、`python-docx`（导出契约用，缺了自动跳过）、`spacy + en_core_web_sm`（蓝图契约用，缺了自动跳过）。
仓库内的 venv：`/tmp/zk-venv/bin/python -m pytest hook -q`。

## 已挂钩的易错点

| hook 文件 | 钉住的事故类型 | 具体案例 |
|---|---|---|
| `test_doc_consistency.py` | 改一处忘另一处 | 词表口径曾在 5 处并存（1601 / 2,795 / 3,585 / 3,686），且废弃口径后来又藏进 `.mcp.json` 与 server instructions（现在 `.md` 与 `.py`/`.json` 双扫描）；荧光图例写"三种色"而表里只有 2 行；"必答 3 问"下实列 5 条；黑名单到 W11 而正文引用只到 W10、reference 只到 W10；弃用工具 `export_article_docx` 又冒回 MCP 工具表；阈值/导出前缀被抄成多份副本 |
| `test_blueprint_contract.py` | 出题分布静默跑偏 | 文档承诺 Q1 写作手法 30% / Q2 词义 70% / Q4 推断 20% / Q3 抽中 I-08 转 M-03 / 带标题时 Q5 不出 best title / 双 I-08 角点约 0.05% —— 全部按种子扫描核对 |
| `test_validator_contract.py` | 校验器误报与虚假兜底 | `shows` 内含 `how` 导致 O-02 模板必刷"缺问号"噪音；排序题事件行必须 ①②③④ 分行；**校验器不检查答案分布**（特征化断言，防止将来实现了却忘记改文档） |
| `test_gate_contract.py` | 漏步导出 / 改文后仍放行 / 档位漏问 | 未抽蓝图、未过 validate、正文漏注释都要拦；新增**正文内容指纹**：改英文内容后必须重跑 check_passage，只增删中文注释不算改（否则会拦死"注释最后一步加"的合规流程）；新增**档位门禁**：档位只认 `workflow_init(level=...)` 显式登记（check_passage 不得顺手用自己的 default 登记），未登记时 check_passage 拒跑、题目导出与报告导出都拦，登记档位与实跑档位不一致也拦 |
| `test_export_contract.py` | 文案改动让调用方静默失效 | 曾用 `startswith("文档已保存")` 判断成功再记工作流状态，改一个字就让门禁形同虚设；现在判定集中在 `exporter.is_export_ok`，并校验苹方-简字体与 eastAsia 中文字体 |

## 已知差异（有意保留，不是 bug）

登记表在 `conftest.py` 的 `KNOWN_DIVERGENCES`。新增差异必须先登记并写理由，否则 hook 失败。

**当前为空** —— 2026-09-10 已解决三处：

| 原差异 | 解决方式 |
|---|---|
| 专名上限 999 vs 5 | 阈值统一到 `Part1-文章改写/thresholds.py`；按 SKILL「专名不设数量限制」取 999，vocab-checker 的 5 属早期遗留、已删 |
| rc 黑名单 W11 只在 SKILL 里 | 已把 W11 回写进 `references/design-logic.md`，并同步小节标题与 SKILL 索引（10→11 条），hook 现在强制三者编号一致 |
| 词表 3,585 vs 解析器 3,686 | 逐项实测后统一为「3,686 个可匹配词形 = 正文 3,570 条词条（含二级 505 条）+ 附录 86 条」；旧数字（1601/2,795/3,585）列入禁止清单由 hook 拦 |


## 2026-09-10 补齐的四项（原"已知缺口"清单）

| 原缺口 | 现在的做法 | 由谁兜底 |
|---|---|---|
| 猜词题目标词下划线未实现 | `exporter.extract_underline_targets()` 从题干引号解析目标词，正文对应位置自动加单下划线（逐字匹配、只划首现、不破坏词距） | `test_export_contract` 逐段比对 + 只允许一处下划线 |
| 题干引用的词被改稿删掉后查不出 | `validate_questions(..., body=正文)` 新增 `stem_quote_in_body` 检查；不传 body 时行为不变（向后兼容） | `test_validator_contract` |
| 指纹状态被同目录其他 agent 覆盖 | 状态里存**已校验指纹清单**（`check_fingerprints`，上限 20）而不是单值；任一 agent 校验过的正文都仍有效 | `test_gate_contract::test_fingerprint_list_survives_multiple_agents` |
| 覆盖率是自证的 | `coverage_range` 同时给出 lenient / strict 两个口径与「靠词缀/词干放宽掉的词」清单（不参与 pass/fail）。实测样例：`actively` 属放宽项 → lenient 0.80 / strict 0.60 | 输出可见；仍不设硬门槛（刻意取舍） |
| mcp 2.x 下 server 起不来 | 两侧加 `try: FastMCP except: MCPServer as FastMCP` 兼容层；requirements 保留 `mcp>=1.0,<2` 作确定性保险 | `test_doc_consistency::test_mcp_version_compat_layer` |

## 还没挂钩的已知缺口（诚实清单）

- **mcp 2.x 的 stdio `run()` 未实测**：2.x 下模块加载、@tool 注册与整套 hook 已实测通过，但实际起 stdio 服务未验证；requirements 已放开为 `mcp>=1.10`（靠兼容层而非钉版本），若 2.x 实测出问题可临时加回 `<2`。
- **覆盖率仍不设硬门槛**：lenient/strict 已可见，但判定仍用 lenient（刻意取舍：宁可漏判也不误判课标词）。
- **门禁的信任边界**：指纹清单解决了同目录互相覆盖，但状态文件本身仍可被手改；它防的是"漏步"与"改文后忘校验"，不是防人。
