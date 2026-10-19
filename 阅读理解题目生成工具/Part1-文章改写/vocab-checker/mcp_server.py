"""
初中英语阅读命题 — 生词检查 MCP Server
========================================
提供六个 Tool：
  1. check_text          — 检查英文文本超纲词
  2. check_article       — 检查完整文章（标题 + 正文）
  3. check_grade_level   — 按九年级标准校验
  4. mark_known          — 把误判为超纲的熟词登记进白名单（持久化，立即生效）
  5. unmark_known        — 从白名单移除
  6. review_unknown_log  — 列出历史上最常被判超纲、且仍未处理的词，供人工确认
"""

import sys
from pathlib import Path
from typing import Any

try:                                        # mcp <2：FastMCP
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:                 # mcp >=2：同一能力改名为 MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP   # type: ignore

# ── 初始化 MCP 服务器 ──
mcp = FastMCP(
    "vocab-checker",
    instructions="初中英语阅读命题生词检查器 — 基于2022版课标二级、三级词汇表 + Oxford 3000（A1–B1）补充（4,124 个可匹配词形），提供文本超纲词检测、覆盖率统计和年级合规校验。",
)

# ── 延迟加载 checker（避免启动超时） ──
_checker = None
VOCAB_MD = Path(__file__).parent / "二级、三级词汇表（初中毕业要求）.md"


def _get_checker():
    global _checker
    if _checker is None:
        sys.path.insert(0, str(Path(__file__).parent))
        from vocab_checker import VocabChecker
        _checker = VocabChecker(str(VOCAB_MD))
    return _checker


# ═══════════════════════════════════════════════════
# Tool 1: check_text — 检查超纲词
# ═══════════════════════════════════════════════════

@mcp.tool()
def check_text(text: str, proper_names: list[str] | None = None) -> dict[str, Any]:
    """检查英文文本中的超纲词汇和课标词覆盖率。

    依据 2022 版义务教育英语课标二级、三级词汇表 + Oxford 3000（A1–B1）补充（4,124 个可匹配词形），
    利用 spaCy 词形还原 + 派生词缀匹配，输出：
      - 课标词覆盖率
      - 超纲词列表（去重 + 频次排序）
      - 疑似专有名词（不计入超纲）
      - 每个超纲词的详细信息（lemma、位置、所在句子）

    Args:
        text: 待检查的英文文本，可含多段落
        proper_names: 用户指定的专名实体列表，
                      如 ["China", "WHO|World Health Organization"],
                      同一实体的别名用 | 分隔。
                      匹配到的词不计入超纲，也不计入覆盖率分母。

    Returns:
        dict: {
            "total_tokens": 有效词总数,
            "known_tokens": 课标词数,
            "unknown_tokens": 超纲词数,
            "proper_nouns": 疑似专有名词数（不计入超纲）,
            "coverage": 覆盖率 (0~1),
            "unknown_words": [超纲词列表-去重排序],
            "word_frequency": [[词, 频次], ...],  # 按频次降序
            "proper_noun_words": [专有名词列表],
            "unknown_details": [{word, lemma, pos, position, sentence}, ...]
        }
    """
    c = _get_checker()
    if not text.strip():
        return {"error": "文本为空", "coverage": 1.0}
    result = c.check(text, proper_names=proper_names)

    # 补频次统计（与 vocab_checker.check_article 共用同一 helper；须在 _get_checker 延迟导入后进行）
    from vocab_checker import unknown_word_frequency  # noqa: E402
    result["word_frequency"] = unknown_word_frequency(result["unknown_details"])

    # 移除不可序列化的 spaCy 内部对象
    result.pop("_doc", None)

    return result


# ═══════════════════════════════════════════════════
# Tool 2: check_article — 完整文章检查
# ═══════════════════════════════════════════════════

@mcp.tool()
def check_article(title: str, body: str, proper_names: list[str] | None = None) -> dict[str, Any]:
    """检查一篇完整阅读文章（标题 + 正文）的超纲词。

    适合命题审校场景：输入文章标题和正文，返回详细检查报告。

    Args:
        title: 文章标题
        body:  文章正文
        proper_names: 用户指定的专名实体列表

    Returns:
        dict: 同 check_text 返回结构，额外包含 title 字段
    """
    c = _get_checker()
    result = c.check_article(title, body, proper_names=proper_names)
    result["title"] = title
    result.pop("_doc", None)
    return result


# ═══════════════════════════════════════════════════
# Tool 3: check_grade_level — 按年级标准校验
# ═══════════════════════════════════════════════════

# 年级阈值：唯一定义在 ../thresholds.py（与 zhongkao-mcp 共用同一份，别再抄副本）。
# 历史上这里另存了一份 max_proper=5，与 SKILL「专名不设数量限制」冲突且无人复审，已随统一移除。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from thresholds import GRADE_LIMITS  # noqa: E402


@mcp.tool()
def check_grade_level(text: str, grade: int = 9) -> dict[str, Any]:
    """按九年级标准校验文本是否符合命题规范。

    本工具只面向九年级（覆盖率 95%-97%，超纲比例 3%-5%，平均句长 ≤26）。

    Args:
        text: 待检查的英文文本
        grade: 年级 — 本工具只面向九年级，固定 9；传入其他值将返回错误

    Returns:
        dict: 包含检查结果 + 逐项通过/未通过判定
    """
    if grade != 9:
        return {"error": f"年级参数无效: {grade}。本工具只面向九年级，grade 必须为 9"}

    c = _get_checker()
    result = c.check(text)
    limits = GRADE_LIMITS[grade]
    unknown_tokens = result["unknown_tokens"]
    proper_count = len(result.get("proper_noun_words", []))
    oov_ratio = unknown_tokens / result["total_tokens"] if result["total_tokens"] else 0.0
    oov_lo, oov_hi = limits["oov_ratio"]

    # 平均句长：复用 check() 返回的 _doc，避免同一文本跑第二次 NLP；
    # 词元口径与 zhongkao-mcp/src/checker.py 一致（排除标点/空格/数字/货币/括号/引号）
    doc = result.pop("_doc", None) or c.nlp(text)
    sentences = [s for s in doc.sents]
    total_words = sum(1 for t in doc if not t.is_punct and not t.is_space
                      and not t.like_num and not t.is_currency
                      and not t.is_bracket and not t.is_quote)
    avg_sent_len = total_words / len(sentences) if sentences else 0

    checks = {
        "coverage": {
            "value": round(result["coverage"], 4),
            "required": limits["coverage"],  # band [lo, hi]
            "pass": limits["coverage"][0] <= result["coverage"] <= limits["coverage"][1],
        },
        "oov_ratio": {
            "value": round(oov_ratio, 4),
            "required": [oov_lo, oov_hi],  # band [lo, hi]
            "pass": oov_lo <= oov_ratio <= oov_hi,
        },
        "proper_nouns": {
            "value": proper_count,
            "required_max": limits["max_proper"],
            "pass": proper_count <= limits["max_proper"],
        },
        "avg_sentence_length": {
            "value": round(avg_sent_len, 1),
            "required_max": limits["max_sentence_len"],
            "pass": avg_sent_len <= limits["max_sentence_len"],
        },
    }

    all_pass = all(v["pass"] for v in checks.values())

    return {
        "grade": grade,
        "all_pass": all_pass,
        "checks": checks,
        "unknown_words": result["unknown_words"],
        "word_frequency": sorted(
            [(w, sum(1 for d in result["unknown_details"] if d["word"] == w))
             for w in result["unknown_words"]],
            key=lambda x: -x[1],
        ),
    }


# ═══════════════════════════════════════════════════
# Tool 4–6: 反馈闭环 — 熟词白名单 + 超纲词命中统计
# ═══════════════════════════════════════════════════

@mcp.tool()
def mark_known(words: list[str], note: str = "") -> dict[str, Any]:
    """把被误判为超纲的熟词登记进白名单（写入 extra_known_words.txt，当前会话立即生效）。

    适用：check_text / check_passage 把学生明显认识的词（如 wifi、kg、okay）列成了超纲词。
    登记后该词不再计超纲、不再占中文注释配额；词表 md 本身与其口径不变。

    Args:
        words: 要登记的词，一行一个单词（可含连字符/撇号）。多词短语请改用 check_text 的 proper_names。
        note:  可选备注（写进文件行尾注释，如 "口语高频" / "单位缩写"）

    Returns:
        dict: {added: [...], already_known: [...], invalid: [...], total_extra_known: n, file: 路径}
    """
    return _get_checker().mark_known(words, note=note)


@mcp.tool()
def unmark_known(words: list[str]) -> dict[str, Any]:
    """从熟词白名单移除（文件中其余词与注释行原样保留）。

    Args:
        words: 要移除的词

    Returns:
        dict: {removed: [...], not_in_whitelist: [...], total_extra_known: n}
    """
    return _get_checker().unmark_known(words)


@mcp.tool()
def review_unknown_log(top_n: int = 20, min_count: int = 1) -> dict[str, Any]:
    """列出历史上最常被判超纲、且按当前规则仍会被判超纲的词，供人工决定是否 mark_known。

    每次 check_text / check_article / check_grade_level / check_passage 都会把超纲词累计记入
    unknown_word_stats.json（同一次检查内重复出现只记 1 次）。反复上榜的词大概率是熟词。
    已被白名单、合成词拆分或词表更新放行的词会自动从清单里消失。

    Args:
        top_n:     返回前 N 个
        min_count: 至少被判超纲多少次才列出

    Returns:
        dict: {total_tracked: n, pending_review: n, top: [{word, count, last_seen, example}, ...], file: 路径}
    """
    return _get_checker().review_unknown_stats(top_n=top_n, min_count=min_count)


# ═══════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
