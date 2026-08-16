# zhongkao-mcp

中考阅读出题工具链 MCP Server — 提供正文指标全检、题目质量校验和 Word 文档导出。

## 定位

**辅助工具层**：写作和出题本身由 Claude 执行（遵循 zhongkao-article-writer SKILL），本 MCP 提供自动化支撑。

## 安装

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 下载 spaCy 英文模型（首次使用前）
python -m spacy download en_core_web_sm

# 3. 确认 vocab-checker 在同级目录
ls ../vocab-checker/mcp_server.py
```

## 在 Claude Code 中配置

将 `.mcp.json` 复制到项目根目录，或手动添加到 `settings.json`：

```json
{
  "mcpServers": {
    "zhongkao-mcp": {
      "command": "python",
      "args": ["zhongkao-mcp/mcp_server.py"],
      "description": "中考阅读出题工具链 — 指标检查、题目校验、Word导出"
    }
  }
}
```

## Tools

### `check_passage` — 正文指标全检

组合 vocab-checker（spaCy 词形还原 + 派生词缀）和结构分析，对照档位阈值逐项判定。

```python
check_passage(
    text="China's economy went up by 4.7 percent...",
    level="standard",      # standard | extended
    grade=9,               # 7 | 8 | 9
    proper_names=["China"] # 保留的专名
)
```

返回：覆盖率、超纲词、句长、词数、专名数和年级合规判定。

### `validate_questions` — 题目质量校验

检查选项格式、答案唯一性、类型覆盖、选项长度平衡、绝对词泄露。

```python
validate_questions(
    questions=[
        {"id": 1, "stem": "How much...?", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "answer": "D", "type": "detail"},
        ...
    ],
    option_count=4  # 3 或 4
)
```

### `export_docx` — Word 导出

将正文和题目导出为可直接使用的 .docx 阅读练习文档。

```python
export_docx(
    title="China Plans to Help Its Economy",
    body="In the first months of 2026...",
    questions=[{"stem": "...", "options": [...]}, ...],
    answer_key=["D", "A", "B", "C"],
    explanations=["1. 解析：...", "2. 解析：...", "3. 解析：...", "4. 解析：..."],  # 可选
    output_path="reading_exercise.docx"
)
```

`explanations`（可选）：每题答案解析，与题目一一对应，渲染在 Answer Key 之后。

## 与 vocab-checker 的关系

`zhongkao-mcp` 直接 import `vocab_checker` 模块作为词汇检查引擎（不通过 MCP 协议桥接）。确保 `vocab-checker/` 在同级目录。

## 目录结构

```
zhongkao-mcp/
├── mcp_server.py       # FastMCP 入口
├── requirements.txt
├── README.md
├── src/
│   ├── __init__.py
│   ├── checker.py      # 指标全检（词汇 + 篇幅 + 句长）
│   ├── validator.py    # 题目质量校验
│   ├── exporter.py     # Word 文档生成
│   └── blueprint.py    # 题目蓝图随机抽取
└── tests/
    └── test_tools.py   # 安装后自测脚本
```
