# 初中英语阅读命题 — 生词检查器 (Vocab Checker)

基于 2022 版义务教育英语课标二级、三级词汇表（2,795 词）的 MCP Server，用于检查英文文本中的超纲词汇。

## 文件清单

```
vocab-checker/
├── mcp_server.py                                # MCP Server 入口
├── vocab_checker.py                             # 核心检查库
├── 二级、三级词汇表（初中毕业要求）.md             # 词表（2,795 词）
├── .mcp.json                                     # MCP 配置示例（供参考）
├── requirements.txt                              # Python 依赖
└── README.md                                     # 本文件
```

## 环境要求

- Python 3.10+
- spaCy 3.x + en_core_web_sm 英文模型
- MCP 包（FastMCP）

## 安装步骤

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 2. 配置 MCP 客户端

将以下配置添加到 Claude Code 的 `.mcp.json`：

```json
{
  "mcpServers": {
    "vocab-checker": {
      "command": "python",
      "args": ["路径/vocab-checker/mcp_server.py"],
      "description": "初中英语阅读命题生词检查器"
    }
  }
}
```

> **注意：** `args` 中的路径需要指向 `mcp_server.py` 的实际位置，可以是绝对路径或相对于项目根目录的路径。

### 3. 验证

重启 Claude Code 后，vocab-checker 自动加载。说"帮我检查这段文本的超纲词"即可。

## 提供的工具

| Tool | 说明 |
|------|------|
| `check_text` | 检查英文文本超纲词，返回覆盖率、超纲词列表、频次 |
| `check_article` | 检查完整文章（标题+正文） |
| `check_grade_level` | 按九年级标准校验是否符合命题规范 |

## 年级标准

本工具只面向**九年级**（覆盖率 95% – 97%，超纲比例 3% – 5%，平均句长 ≤ 26）。不提供其他年级选项。

超纲词比例 = 超纲唯一词元数 / 有效唯一词元数，与覆盖率互补（覆盖率 = 1 − 超纲词比例）。同一生词反复出现只计一次。

## 直接使用（非 MCP 方式）

也可以不通过 MCP，直接在 Python 中调用：

```python
from vocab_checker import VocabChecker

checker = VocabChecker("二级、三级词汇表（初中毕业要求）.md")
result = checker.check("Your English text here.")
print("覆盖率:", result["coverage"])
print("超纲词:", result["unknown_words"])
```

## 词表说明

`二级、三级词汇表（初中毕业要求）.md` 基于三个来源合并去重：

- 2022 版义务教育英语课标三级词汇表
- 新东方《15天背完3500词》
- 2026 年全国各省中考英语真题超纲词汇

原始课标约 1,683 词形，扩充后共 **2,795+ 词形**。词表中 `*` 标记表示二级（小学阶段）词汇。
