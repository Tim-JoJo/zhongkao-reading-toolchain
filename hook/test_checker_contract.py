"""指标检查契约 hook —— word_count 口径、350 词硬门槛与句均同源。

对应踩过的坑（2026-09-12 bug 清单 BUG-03 / DOC-03）：
  1. word_count 曾用 token_occurrences，把专名排除在外（vocab_checker 将 PROPN/
     声明专名归入 proper_count）：320 词、含 40 个专名的稿子只报 280 —— 高专名
     浓度的稿子能绕过「全文 ≤350 词」硬门槛（CLAUDE.md 第 8 节）。
  2. grade_check.avg_sentence_length 与 metrics.average_sentence_length 曾是两套
     算法（分母是否剔除零内容句），同一篇稿子对外出现两个句均数字。
"""
from __future__ import annotations

import pytest

pytest.importorskip("spacy", reason="check_passage 需要 spaCy")
pytest.importorskip("en_core_web_sm", reason="需要 spaCy 模型 en_core_web_sm")

from src.checker import run_check_passage          # noqa: E402（路径由 conftest 注入）
from thresholds import GRADE_LIMITS, LEVEL_THRESHOLDS  # noqa: E402

# 8 个实词词元/句，Kowalczyk 是 PROPN（曾不计入 word_count）
SENT = "Kowalczyk visited the town and met the team."


def _check(text: str):
    return run_check_passage(text=text, level="standard", grade=9, proper_names=[],
                             level_thresholds=LEVEL_THRESHOLDS["standard"],
                             grade_limits=GRADE_LIMITS[9])


def test_word_count_counts_proper_nouns():
    """word_count = 全部实词词元出现次数（含专名）：8 词 ×40 = 320，不得再报 280。"""
    res = _check(" ".join([SENT] * 40))
    assert res["metrics"]["word_count"]["value"] == 320, res["metrics"]["word_count"]


def test_proper_noun_heavy_passage_still_hits_hard_limit():
    """360 词（专名 45 个）必须 review_required —— 硬门槛不因专名浓度而漏判。"""
    res = _check(" ".join([SENT] * 45))
    assert res["metrics"]["word_count"]["value"] == 360, res["metrics"]["word_count"]
    assert res["metrics"]["word_count"]["status"] == "review_required"
    assert res["all_pass"] is False


def test_grade_avg_sentence_length_matches_metrics():
    """grade_check 与 metrics 的句均必须同源，不得两套算法各报一个数。"""
    res = _check(" ".join([SENT] * 10))
    gc = res["grade_check"]["details"]["avg_sentence_length"]["value"]
    assert gc == res["metrics"]["average_sentence_length"]["value"], (gc, res["metrics"]["average_sentence_length"])
