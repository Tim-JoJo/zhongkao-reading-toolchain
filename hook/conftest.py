"""hook 套件的公共部分：路径、依赖降级、实测口径常量。

这些 hook 的目的不是"跑通"，而是把**已经踩过的坑**钉住：
以后任何一次编辑若把旧问题改回来，这里必须变红。
"""
from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
GEN = REPO / "阅读理解题目生成工具"
P1 = GEN / "Part1-文章改写"
MCP = P1 / "zhongkao-mcp"
AW = P1 / "zhongkao-article-writer/SKILL.md"
QG = GEN / "Part2-题目生成/zhongkao-question-generator/SKILL.md"
RC = GEN / "Part2-题目生成/rc-question-writing/SKILL.md"
REW = GEN / "reading-explorer-writing/SKILL.md"
VOCAB_MD = P1 / "vocab-checker/二级、三级词汇表（初中毕业要求）.md"
VOCAB_SRV = P1 / "vocab-checker/mcp_server.py"
DESIGN_LOGIC = GEN / "Part2-题目生成/rc-question-writing/references/design-logic.md"
SHARED_THRESHOLDS = P1 / "thresholds.py"

# ── 词表实测口径（改词表后必须同步这里 + 全仓文档）──
PARSED_VOCAB_FORMS = 3686   # parse_vocab_md() 去重词形总数
AZ_ENTRY_LINES = 3570       # A–Z 正文词条行数
AZ_STAR_LINES = 505         # 其中带 * 的二级（小学阶段）词汇行数
APPENDIX_FORMS = 86         # 附录（基数词/序数词/月份/星期/地理名称）词形数
HYPHEN_FORMS = 16           # 含连字符的词形数

# ── 有意差异登记表 ──
# 规则：任何"文档与实现不一致但暂时不改"的差异都必须登记在此并写清理由，
# 否则对应 hook 会失败。当前为空 —— 历史三处（专名上限、W11、词表口径）已于 2026-09-10 全部解决。
KNOWN_DIVERGENCES: dict[str, str] = {}

for _p in (MCP, P1 / "vocab-checker", P1):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
