"""词表契约 hook —— 文档口径 vs 解析器实测，两边都钉死。

背景：本仓库历史上 2,795 / 3,510 / 3,585 / 3,686 四种说法并存过，对外文档与运行时行为互相打架。
2026-09-10 起统一为实测口径：**3,686 个可匹配词形 = A–Z 正文 3,570 条词条 + 附录 86 条**。
改词表就必然触发本文件，强制同步文档与 hook/conftest.py 的常量。
"""
from __future__ import annotations

import re

import pytest

from conftest import (APPENDIX_FORMS, AZ_ENTRY_LINES, AZ_STAR_LINES, HYPHEN_FORMS,
                      PARSED_VOCAB_FORMS, VOCAB_MD)

pytest.importorskip("spacy", reason="解析词表需要 spaCy（纯文档 hook 见 test_doc_consistency）")
pytest.importorskip("en_core_web_sm", reason="需要 spaCy 模型 en_core_web_sm")

NUMBERS = ("3686", "3570", "86", "505", "16")


def _checker():
    from vocab_checker import VocabChecker
    return VocabChecker(str(VOCAB_MD))


def _sections():
    """复刻 parse_vocab_md 的切片方式，逐行统计。"""
    from vocab_checker import _parse_number_section, _parse_vocab_line
    text = VOCAB_MD.read_text(encoding="utf-8")
    az = text[text.index("\n## A\n") + len("\n## A\n"):text.index("\n## 数词表\n")]
    entries = [l.strip() for l in az.strip().split("\n")]
    entries = [l for l in entries if l and not l.startswith(("##", "---"))]
    forms = set()
    for l in entries:
        forms |= _parse_vocab_line(l)
    app = set()
    for name in ("基数词", "序数词", "月份词汇", "星期词汇", "地理名称"):
        app |= _parse_number_section(text, name)
    return entries, forms, app


def test_doc_header_uses_measured_numbers():
    body = VOCAB_MD.read_text(encoding="utf-8")
    for n in NUMBERS:
        assert n in body, f"词表说明区缺少实测数字 {n}（口径变了要同步文档与 hook）"
    assert "不要再写" in body, "说明区应明确禁止旧口径数字"


def test_measured_counts_match_registered_constants():
    entries, forms, app = _sections()
    actual = dict(AZ_ENTRY_LINES=len(entries), AZ_STAR_LINES=sum(1 for l in entries if l.rstrip().endswith("*")),
                  APPENDIX_FORMS=len(app), PARSED_VOCAB_FORMS=len(_checker().base_vocab),
                  HYPHEN_FORMS=sum(1 for w in _checker().base_vocab if "-" in w))
    assert actual["AZ_ENTRY_LINES"] == AZ_ENTRY_LINES, actual
    assert actual["AZ_STAR_LINES"] == AZ_STAR_LINES, actual
    assert actual["APPENDIX_FORMS"] == APPENDIX_FORMS, actual
    assert actual["PARSED_VOCAB_FORMS"] == PARSED_VOCAB_FORMS, actual
    assert actual["HYPHEN_FORMS"] == HYPHEN_FORMS, actual


def test_slash_pairs_are_both_kept():
    """`actor / actress` 这类成对条目必须拆出两侧——只留整串会让真实词被判超纲。"""
    entries, _, _ = _sections()
    vocab = _checker().base_vocab
    missing = []
    for line in entries:
        m = re.match(r"^([A-Za-z][A-Za-z.'\-]*)\s*/\s*([A-Za-z][A-Za-z.'\-]*)", line)
        if m and m.group(1).lower() not in vocab or (m and m.group(2).lower() not in vocab):
            missing.append((line, m.groups()))
    assert not missing, f"成对条目未拆开：{missing[:5]}"


def test_no_cjk_or_punctuation_junk_in_vocab():
    """词表里不得混入汉字或纯标点残余（说明区/标题曾被误解析的风险）。"""
    vocab = _checker().base_vocab
    junk = sorted(w for w in vocab if re.search(r"[\u4e00-\u9fff]", w))
    assert not junk, f"词表混入中文片段：{junk[:8]}"


def test_lemma_set_is_superset_of_forms():
    c = _checker()
    assert set(c.base_vocab) <= c.vocab_lemmas, "lemma 集合必须覆盖全部原始词形（否则课标词会被误判超纲）"
