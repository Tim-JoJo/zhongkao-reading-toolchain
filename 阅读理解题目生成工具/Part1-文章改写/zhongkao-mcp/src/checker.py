from __future__ import annotations

import re
import statistics
from typing import Any


# ── 内部：引入 vocab_checker ──
import sys
from pathlib import Path

_VOCAB_CHECKER_DIR = None
for _candidate in (
    Path(__file__).resolve().parent.parent.parent / "vocab-checker",
    Path(__file__).resolve().parent.parent.parent.parent / "Part1-文章改写" / "vocab-checker",
):
    if _candidate.exists():
        _VOCAB_CHECKER_DIR = str(_candidate)
        break
if _VOCAB_CHECKER_DIR is None:
    raise FileNotFoundError("找不到 vocab-checker 目录")
if _VOCAB_CHECKER_DIR not in sys.path:
    sys.path.insert(0, _VOCAB_CHECKER_DIR)

from vocab_checker import VocabChecker

# ── 单例 ──
_checker_singleton: VocabChecker | None = None


def _get_checker() -> VocabChecker:
    global _checker_singleton
    if _checker_singleton is None:
        vocab_md = Path(_VOCAB_CHECKER_DIR) / "二级、三级词汇表（初中毕业要求）.md"
        _checker_singleton = VocabChecker(str(vocab_md))
    return _checker_singleton


# ── 文本分析 ──

WORD_RE = re.compile(r"[A-Za-z]+(?:[''][A-Za-z]+)?")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])(?:['\")\\]*)\s+")


def _tokenize(text: str) -> list[str]:
    return WORD_RE.findall(text)


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return []
    parts = [p.strip() for p in SENTENCE_SPLIT_RE.split(cleaned) if p.strip()]
    return parts or [cleaned]


def _word_count(text: str) -> int:
    return len(_tokenize(text))


def _sentence_metrics(doc) -> dict[str, Any]:
    """从 spaCy Doc 对象提取句子长度指标（替代正则分句，确保与 vocab_checker 一致）"""
    sentences = [s for s in doc.sents]
    lengths = [sum(1 for t in s if not t.is_punct and not t.is_space and not t.like_num and not t.is_currency and not t.is_bracket and not t.is_quote) for s in sentences]
    lengths = [l for l in lengths if l > 0]
    if not lengths:
        return {"average": 0.0, "p90": 0, "count": 0, "lengths": []}
    average = round(statistics.mean(lengths), 2)
    ordered = sorted(lengths)
    rank = max(1, int(0.90 * len(ordered)))
    p90 = ordered[rank - 1]
    return {"average": average, "p90": p90, "count": len(lengths), "lengths": lengths}


def _parse_proper_name_groups(raw: list[str]) -> list[list[str]]:
    """将 ["China", "WHO|World Health Organization"] 展开为分组."""
    groups = []
    for entry in raw:
        aliases = [a.strip() for a in entry.split("|") if a.strip()]
        if aliases:
            groups.append(aliases)
    return groups


def _count_present_proper_names(text: str, groups: list[list[str]]) -> int:
    """统计文本中实际出现的专名实体数（同一实体的多个别名合并为 1）。"""
    count = 0
    for group in groups:
        for alias in group:
            if re.search(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", text, re.IGNORECASE):
                count += 1
                break
    return count


# ── 判定逻辑 ──

def _status_band(value: float, lo: float, hi: float) -> str:
    if lo <= value <= hi:
        return "pass"
    return "review_required"


def _status_ge(value: float, threshold: float) -> str:
    return "pass" if value >= threshold else "review_required"


def _status_le(value: int, max_val: int) -> str:
    return "pass" if value <= max_val else "review_required"


PROPER_STATUS_LABELS = {
    "within_band": "pass",
    "allowed_below_band": "pass",
    "review_required": "review_required",
    "pass": "pass",
}


# ── 主入口 ──

def _check_grade_level(vocab_result: dict, grade_limits: dict) -> dict:
    """年级合规检查（复用 vocab_result 中的 spaCy doc，避免重复 NLP）"""
    unknown_tokens = vocab_result.get("unknown_tokens", 0)
    proper_count = len(vocab_result.get("proper_noun_words", []))

    # 从 vocab_result 中复用 spaCy doc（避免重复 nlp(text)）
    doc = vocab_result.get("_doc")
    if doc is None:
        # 兜底：如果调用方没传 doc（如 vocab-checker MCP 直接调用），重新解析
        from vocab_checker import _get_checker
        doc = _get_checker().nlp("")  # 不会走到这里，但保留防御
    sentences = [s for s in doc.sents]
    total_words = sum(1 for t in doc if not t.is_punct and not t.is_space and not t.like_num and not t.is_currency and not t.is_bracket and not t.is_quote)
    avg_sent_len = total_words / len(sentences) if sentences else 0

    cov_lo, cov_hi = grade_limits["coverage"]
    oov_lo, oov_hi = grade_limits["oov_ratio"]
    # oov_ratio 分母与覆盖率口径一致（唯一词元总数）
    unique_words = vocab_result.get("total_tokens", total_words)
    oov_ratio = unknown_tokens / unique_words if unique_words else 0.0

    checks = {
        "coverage": {
            "value": round(vocab_result["coverage"], 4),
            "required": [cov_lo, cov_hi],
            "pass": cov_lo <= vocab_result["coverage"] <= cov_hi,
        },
        "oov_ratio": {
            "value": round(oov_ratio, 4),
            "required": [oov_lo, oov_hi],
            "pass": oov_lo <= oov_ratio <= oov_hi,
        },
        "proper_nouns": {
            "value": proper_count,
            "required_max": grade_limits.get("max_proper", 99),
            "pass": proper_count <= grade_limits.get("max_proper", 99),
        },
        "avg_sentence_length": {
            "value": round(avg_sent_len, 1),
            "required_max": grade_limits["max_sentence_len"],
            "pass": avg_sent_len <= grade_limits["max_sentence_len"],
        },
    }
    return {
        "grade": grade_limits.get("_grade", 9),
        "all_pass": all(v["pass"] for v in checks.values()),
        "checks": checks,
    }


def run_check_passage(
    *,
    text: str,
    level: str,
    grade: int,
    proper_names: list[str],
    level_thresholds: dict,
    grade_limits: dict,
) -> dict[str, Any]:
    # 1. 词汇检查（vocab-checker）——只此一次 spaCy NLP 解析
    checker = _get_checker()
    vocab_result = checker.check(text, proper_names=proper_names)
    doc = vocab_result.get("_doc")

    # 为 grade_limits 注入 grade 值，供 _check_grade_level 使用
    grade_limits = dict(grade_limits)
    grade_limits["_grade"] = grade

    # 年级合规检查（复用 vocab_result 中的 spaCy doc，不重复解析）
    grade_result = _check_grade_level(vocab_result, grade_limits)

    # 2. 结构指标（复用 vocab_result 数据，不用 regex）
    wc = vocab_result.get("token_occurrences", vocab_result["total_tokens"])
    sent = _sentence_metrics(doc) if doc is not None else {"average": 0.0, "p90": 0, "count": 0, "lengths": []}

    # 3. 专名
    pn_groups = _parse_proper_name_groups(proper_names)
    pn_count = _count_present_proper_names(text, pn_groups)
    pn_lo = level_thresholds["proper_name_band"][0]
    pn_hi = level_thresholds["proper_name_band"][1]
    # proper name band: 0-999 means no limit, always pass
    if pn_lo == 0 and pn_hi >= 999:
        pn_status = "pass"
    elif pn_count < pn_lo:
        pn_status = "allowed_below_band"
    elif pn_count <= pn_hi:
        pn_status = "within_band"
    else:
        pn_status = "review_required"

    # 4. 组装指标
    unknown_words = vocab_result.get("unknown_words", [])
    oov_details = _format_oov_details(vocab_result)

    th = level_thresholds
    metrics = {
        "word_count": {
            "value": wc,
            "band": th["word_count"],
            "status": _status_band(wc, th["word_count"][0], th["word_count"][1]),
        },
        "average_sentence_length": {
            "value": sent["average"],
            "band": th["average_sentence_length"],
            "status": _status_band(sent["average"], th["average_sentence_length"][0], th["average_sentence_length"][1]),
        },
        "sentence_length_p90": {
            "value": sent["p90"],
            "band": th["sentence_length_p90"],
            "status": _status_le(sent["p90"], th["sentence_length_p90"][1]),
        },
        "vocabulary_coverage": {
            "value": round(vocab_result["coverage"], 4),
            "threshold": th["vocabulary_coverage"],
            "status": _status_ge(vocab_result["coverage"], th["vocabulary_coverage"]),
        },
        "oov_distinct": {
            "value": unknown_words,
            "max": th["oov_distinct_max"],
            "status": _status_le(len(unknown_words), th["oov_distinct_max"]),
        },
        "proper_name_count": {
            "value": pn_count,
            "band": th["proper_name_band"],
            "status": PROPER_STATUS_LABELS[pn_status],
        },
    }

    # 5. 年级合规
    gc = grade_result.get("checks", {})
    grade_check = {
        "grade": grade_result.get("grade", grade),
        "all_pass": grade_result.get("all_pass", False),
        "details": {
            "coverage": gc.get("coverage", {}),
            "oov_ratio": gc.get("oov_ratio", {}),
            "proper_nouns": gc.get("proper_nouns", {}),
            "avg_sentence_length": gc.get("avg_sentence_length", {}),
        },
    }

    all_pass = (
        all(m["status"] == "pass" for m in metrics.values())
        and grade_check["all_pass"]
    )

    return {
        "level": level,
        "metrics": metrics,
        "grade_check": grade_check,
        "oov_details": oov_details,
        "proper_noun_candidates": vocab_result.get("proper_noun_words", []),
        "sentence_count": sent["count"],
        "sentence_lengths": sent["lengths"],
        "all_pass": all_pass,
    }


def _format_oov_details(vocab_result: dict) -> list[dict]:
    """整理超纲词详情，去重并统计频次。"""
    unknown_details = vocab_result.get("unknown_details", [])
    # 按词聚合
    by_word: dict[str, dict] = {}
    for d in unknown_details:
        w = d["word"]
        if w not in by_word:
            by_word[w] = {
                "word": w,
                "lemma": d["lemma"],
                "pos": d["pos"],
                "frequency": 0,
                "sentences": [],
            }
        by_word[w]["frequency"] += 1
        sent = d.get("sentence", "")
        if sent and sent not in by_word[w]["sentences"]:
            by_word[w]["sentences"].append(sent)
    # 按频次降序
    return sorted(by_word.values(), key=lambda x: -x["frequency"])


def _norm_sentence(s: str) -> str:
    """归一化:去空白、标点、非字母数字,转小写(用于原句比对)。"""
    return re.sub(r"[\s\W_]+", "", s).lower()


def _char_similarity(a: str, b: str) -> float:
    """字符级相似度(difflib SequenceMatcher ratio)。"""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def run_check_original_quotes(text: str, source_text: str, similarity_threshold: float = 0.95) -> dict[str, Any]:
    """检测改编文本是否引用了原文原句(硬性规则:不可引用任何原文原句)。

    逐句比对:改编句与任一原文句归一化后完全一致、或字符相似度 >= similarity_threshold、
    或改编句完整包含原文句(反之亦然),即判定命中。返回 all_pass 与命中详情;任何命中必须改写该句后重新检测。
    """
    text_sents = _split_sentences(text)
    source_sents = _split_sentences(source_text)
    source_pairs = [(s, _norm_sentence(s)) for s in source_sents if _norm_sentence(s)]
    hits: list[dict] = []
    for s in text_sents:
        n = _norm_sentence(s)
        if not n:
            continue
        for src, sn in source_pairs:
            if n == sn:
                hits.append({"sentence": s, "matched_source": src, "similarity": 1.0})
                break
            # 包含关系:改编句完整包含原文句(或反之)——即使追加了成分也算引用
            if sn in n or n in sn:
                sim = _char_similarity(n, sn)
                hits.append({"sentence": s, "matched_source": src, "similarity": round(sim, 3), "containment": True})
                break
            sim = _char_similarity(n, sn)
            if sim >= similarity_threshold:
                hits.append({"sentence": s, "matched_source": src, "similarity": round(sim, 3)})
                break
    return {
        "all_pass": len(hits) == 0,
        "hit_count": len(hits),
        "hits": hits,
        "threshold": similarity_threshold,
    }
