"""词表契约 hook —— 文档写的词表规模 vs 解析器实际加载的词形数。

对应踩过的坑：本仓库历史上 2,795 / 3,510 / 3,585 / 3,686 四种说法并存过，对外文档与运行时行为互相打架。
这里把两边都钉住：文档口径必须全仓一致（见 test_doc_consistency）；
解析器实际加载量若变化，本 hook 立刻变红，强制显式确认后再同步文档。
"""
from __future__ import annotations

import re
import pytest

from conftest import KNOWN_DIVERGENCES, PARSED_VOCAB_FORMS, VOCAB_MD

pytest.importorskip("spacy", reason="解析词表需要 spaCy（纯文档 hook 见 test_doc_consistency）")
pytest.importorskip("en_core_web_sm", reason="需要 spaCy 模型 en_core_web_sm")


def _checker():
    from vocab_checker import VocabChecker
    return VocabChecker(str(VOCAB_MD))


def test_doc_header_count_is_stable():
    m = re.search(r"共收录 *(\d+) *个词条", VOCAB_MD.read_text(encoding="utf-8"))
    assert m, "词表 md 头部应写明收录规模"
    assert int(m.group(1)) == 3585, "md 头部口径变了：请同步全仓文档与 conftest 的登记"


def test_parser_loaded_forms_are_pinned():
    parsed = len(_checker().base_vocab)
    assert parsed == PARSED_VOCAB_FORMS, (
        f"解析器加载 {parsed} 个词形（登记值 {PARSED_VOCAB_FORMS}）。变化本身可以接受，"
        "但要同步 conftest.PARSED_VOCAB_FORMS 与全仓文档口径。")


def test_doc_vs_parser_divergence_is_registered():
    declared = int(re.search(r"共收录 *(\d+) *个词条", VOCAB_MD.read_text(encoding="utf-8")).group(1))
    parsed = len(_checker().base_vocab)
    if declared != parsed:
        assert "vocab_md_parsed_count" in KNOWN_DIVERGENCES, (
            f"md 头部称 {declared} 词条、解析器实得 {parsed}，该差异未登记")


def test_lemma_set_is_superset_of_forms():
    c = _checker()
    assert set(c.base_vocab) <= c.vocab_lemmas, "lemma 集合必须覆盖全部原始词形（否则课标词会被误判超纲）"
