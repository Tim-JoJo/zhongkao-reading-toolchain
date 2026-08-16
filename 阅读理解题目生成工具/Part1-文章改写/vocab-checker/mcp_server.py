"""
初中英语阅读命题 — 生词检查 MCP Server
========================================
提供两个 Tool：
  1. check_text      — 检查英文文本超纲词
  2. list_unknown    — 列出/导出超纲词详情
"""

import json
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# ── 初始化 MCP 服务器 ──
mcp = FastMCP(
    "vocab-checker",
    instructions="初中英语阅读命题生词检查器 — 基于2022版课标二级、三级词汇表（2,795词），提供文本超纲词检测、覆盖率统计和年级合规校验。",
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

    依据 2022 版义务教育英语课标二级、三级词汇表（2,795 词），
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

    # 补频次统计
    freq = {}
    for d in result["unknown_details"]:
        freq[d["word"]] = freq.get(d["word"], 0) + 1
    result["word_frequency"] = sorted(freq.items(), key=lambda x: -x[1])

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

GRADE_LIMITS = {
    9: {"coverage": [0.95, 0.97], "oov_ratio": [0.03, 0.05], "max_proper": 5, "max_sentence_len": 26, "max_compound_ratio": 0.40},
}


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
    result.pop("_doc", None)

    limits = GRADE_LIMITS[grade]
    unknown_tokens = result["unknown_tokens"]
    proper_count = len(result.get("proper_noun_words", []))
    total_words = result["total_tokens"]
    oov_ratio = unknown_tokens / total_words if total_words else 0.0
    oov_lo, oov_hi = limits["oov_ratio"]

    # 计算平均句长
    doc = c.nlp(text)
    sentences = [s for s in doc.sents]
    total_words = sum(1 for t in doc if not t.is_punct and not t.is_space)
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
# 启动
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
