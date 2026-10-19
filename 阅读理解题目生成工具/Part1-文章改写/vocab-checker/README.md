# 初中英语阅读命题 — 生词检查器 (Vocab Checker)

基于 2022 版义务教育英语课标二级、三级词汇表 + Oxford 3000（CEFR A1–B1）补充（4,124 个可匹配词形）的 MCP Server，用于检查英文文本中的超纲词汇。

## 文件清单

```
vocab-checker/
├── mcp_server.py                                # MCP Server 入口
├── vocab_checker.py                             # 核心检查库
├── 二级、三级词汇表（初中毕业要求）.md             # 词表（正文 4,005 条 + 附录 86 条）
├── extra_known_words.txt                        # 熟词白名单（反馈闭环；人工确认结果，入库）
├── unknown_word_stats.json                      # 超纲词命中统计（运行时自动生成，不入库）
├── .lemma_cache.pkl                             # 词表 lemma 缓存（按词表哈希自动重建，不入库）
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
| `mark_known` | 把误判为超纲的熟词登记进白名单（写入 `extra_known_words.txt`，立即生效） |
| `unmark_known` | 从白名单移除 |
| `review_unknown_log` | 列出历史上最常被判超纲、且仍未处理的词，供人工确认 |

## 判定逻辑

一个词被认为"学生认识"，依次尝试：

1. **直接命中**：原形或 spaCy lemma 在词表中（`runs → run`、`children → child`）
2. **派生词缀还原**：剥离课标可考的前后缀后命中（`development → develop`、`unhappy → happy`）
3. **词干匹配**：激进剥离多层后缀后与词表词同干（`cooperation ≈ cooperate`）
4. **合成词拆分**：拆成两段都是词表词即视为可由构词法推断（课标三级"根据构词法猜测生词"）：`sunglasses → sun+glasses`、`skateboard → skate+board`、`headphones → head+phones`。为防巧合切分放过真生词，要求全词 ≥ 7 字母、两段各 ≥ 3 字母，且右段不能是 `age / ice / ate / ant` 这类本身是单词的派生后缀（`hostage ≠ host+age`）
5. **熟词白名单**：`extra_known_words.txt` 里的词

第 2–4 层统称"宽松放行"。返回值里 `coverage` 是宽松口径，`coverage_strict` 只算第 1、5 层，两者之差就是算法放宽的部分；`relaxed_only_words` 列出全部放宽词，`compound_words` 单列其中按合成词解释的词及拆法（如 `{"sunglasses": "sun+glasses"}`），`extra_known_hits` 列出命中白名单的词——三个字段都是给人复核用的。

## 反馈闭环：让误判越来越少

课标词表是书面正式语体的最低要求清单，天然不收口语高频词、单位缩写和科技生活新词（`okay`、`kg`、`wifi`……），所以熟词被判为"生词"不可能靠一次性补词根治。工具提供两条持续改善的通路：

**① 熟词白名单** `extra_known_words.txt`

审稿时发现明显的熟词被判超纲，直接登记：

```
mark_known(words=["wifi", "kg"], note="单位/科技缩写")
```

登记后立即生效：不再计超纲、不再占中文注释配额；新会话启动时自动加载。文件一行一个词、`#` 后是注释，可以手工编辑。白名单**只并入匹配集合，不改动词表 md**，所以词表口径（hook 钉死的实测数字）和"课标合规"这个指标的语义都不受影响。

**② 超纲词命中统计** `unknown_word_stats.json`

每次检查（含 Part1 `check_passage` 调用的同一份代码）都会把超纲词累计记录——同一次检查内重复出现只记 1 次。定期查看：

```
review_unknown_log(top_n=20)
```

返回按"被判超纲次数"排序的词及其出现例句；反复上榜的几乎必然是熟词，确认后一批 `mark_known` 即可。已被白名单、合成词拆分或词表更新放行的词会自动从清单里消失，所以这份清单只剩"还没处理的"。统计文件是本机审稿数据，不入库。

> 直接用 Python 时对应 `checker.mark_known(...)` / `checker.unmark_known(...)` / `checker.review_unknown_stats(...)`；`VocabChecker(..., feedback_dir=..., record_stats=False)` 可改白名单与统计的目录、或关闭统计记录（测试时用）。

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

`二级、三级词汇表（初中毕业要求）.md` 由两部分组成：课标主体依据《义务教育英语课程标准（2022年版）》二级、三级词汇要求整理（含二级 505 条）；2026-10-19 起在各字母区末尾以 `### Oxford 3000（A1–B1）补充` 子块注入牛津 3000 词表（The Oxford 3000 by CEFR level）A1／A2／B1 三级词条，跨级去重并剔除课标已有词后新增 435 条。实测规模：A–Z 正文 **4,005 条词条** + 附录 86 条，解析器展开为 **4,124 个可匹配词形**；词表中 `*` 标记表示二级（小学阶段）词汇。