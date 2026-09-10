"""hook 套件的公共部分：路径、依赖降级、已知差异登记。

这些 hook 的目的不是"跑通"，而是把**已经踩过的坑**钉住：
以后任何一次编辑若把旧问题改回来，这里必须变红。
"""
from __future__ import annotations

import pathlib
import sys
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
GEN = REPO / "阅读理解题目生成工具"
MCP = GEN / "Part1-文章改写/zhongkao-mcp"
SRC = MCP / "src"
AW = GEN / "Part1-文章改写/zhongkao-article-writer/SKILL.md"
QG = GEN / "Part2-题目生成/zhongkao-question-generator/SKILL.md"
RC = GEN / "Part2-题目生成/rc-question-writing/SKILL.md"
REW = GEN / "reading-explorer-writing/SKILL.md"
VOCAB_MD = GEN / "Part1-文章改写/vocab-checker/二级、三级词汇表（初中毕业要求）.md"
VOCAB_SRV = GEN / "Part1-文章改写/vocab-checker/mcp_server.py"
DESIGN_LOGIC = GEN / "Part2-题目生成/rc-question-writing/references/design-logic.md"

# ── 已知有意差异：新增差异必须先进这里并写清理由，否则 hook 失败 ──
KNOWN_DIVERGENCES = {
    "grade_max_proper":
        "zhongkao-mcp 走 SKILL「专名不设数量限制」→ 999（无上限）；"
        "vocab-checker 的独立年级校验沿用历史口径 max_proper=5（仅供人工快检）。"
        "**待裁决**：若要求两处一致，改 thresholds.py 与 vocab-checker/mcp_server.py 后同步删除本项。",
    "vocab_md_parsed_count":
        "词表 md 头部写「共收录 3585 个词条（去重 3581 条）」，但 vocab_checker.parse_vocab_md() "
        "实测解析出 3686 个词形（差 101，来自同一行多词形/词组的切分口径）。**待裁决**："
        "把 md 头部改成与解析器一致的可核对表述，或收紧解析器切分规则。"
        "在此之前对外一律用「3,585 词条（md 口径）」并注明解析器实际加载 3,686 个词形。",
    "rc_blacklist_w11":
        "rc SKILL.md 反例黑名单有 W1–W11（W11=答案字母与正确项内容错位），"
        "references/design-logic.md 只到 W1–W10；索引写「10 反模式详解」描述的是 design-logic.md，属准确。"
        "待办：把 W11 回写进 design-logic.md 后删除本项。",
}

if str(MCP) not in sys.path:
    sys.path.insert(0, str(MCP))
if str(GEN / "Part1-文章改写/vocab-checker") not in sys.path:
    sys.path.insert(0, str(GEN / "Part1-文章改写/vocab-checker"))

# 解析器实际加载的词形数（运行时实测值；钉住它，任何变化都要显式确认）
PARSED_VOCAB_FORMS = 3686


def has_module(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


@pytest.fixture(scope="session")
def mcp_dir():
    return MCP


@pytest.fixture(scope="session")
def gen_dir():
    return GEN
