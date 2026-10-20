"""词表契约 hook —— 文档口径 vs 解析器实测，两边都钉死。

背景：本仓库历史上 2,795 / 3,510 / 3,585 / 3,686 四种说法并存过，对外文档与运行时行为互相打架。
2026-09-10 起统一为实测口径：**3,686 个可匹配词形 = A–Z 正文 3,570 条词条 + 附录 86 条**。
2026-10-19 注入 Oxford 3000（CEFR A1/A2/B1）补充 435 条、并修复 `(AmE xxx)` 美式拼写丢失后，
口径更新为：**4,124 个可匹配词形 = A–Z 正文 4,005 条词条 + 附录 86 条**（含连字符词 18 条）。
改词表就必然触发本文件，强制同步文档与 hook/conftest.py 的常量。
"""
from __future__ import annotations

import json
import re
import shutil

import pytest

from conftest import (APPENDIX_FORMS, AZ_ENTRY_LINES, AZ_STAR_LINES, HYPHEN_FORMS,
                      PARSED_VOCAB_FORMS, VOCAB_MD, VOCAB_SRV)

pytest.importorskip("spacy", reason="解析词表需要 spaCy（纯文档 hook 见 test_doc_consistency）")
pytest.importorskip("en_core_web_sm", reason="需要 spaCy 模型 en_core_web_sm")

NUMBERS = ("4124", "4005", "86", "505", "18")


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


# ══════════════════════════════════════════════════════════════════════
# 2026-10-20：合成词拆分 / 熟词白名单 / 命中统计 / lemma 缓存 / 专名通道 的回归钉。
# 这些都是启发式或落盘行为，一旦被改回去不会有任何别的测试变红，所以逐条钉死。
# 全部用临时 feedback_dir，不碰仓库里的白名单与统计文件。
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def fb(tmp_path):
    """白名单/统计落在临时目录、显式开启统计记录的检查器。"""
    from vocab_checker import VocabChecker
    return VocabChecker(str(VOCAB_MD), feedback_dir=str(tmp_path), record_stats=True)


def _unknown(c, text, **kw):
    return c.check(text, **kw)["unknown_words"]


def _stats(c):
    return json.loads((c.feedback_dir / "unknown_word_stats.json").read_text(encoding="utf-8"))


def _private_vocab(tmp_path):
    """词表副本：让 lemma 缓存落在临时目录，测试可以随意弄坏它。"""
    md = tmp_path / VOCAB_MD.name
    shutil.copy(VOCAB_MD, md)
    return md


# ── 合成词拆分 ──

def test_compound_split_releases_transparent_compounds(fb):
    r = fb.check("She wore sunglasses, rode a skateboard and put on headphones.")
    assert not {"sunglasses", "skateboard", "headphones"} & set(r["unknown_words"])
    assert {"sunglasses", "skateboard", "headphones"} <= set(r["compound_words"])


def test_compound_split_blocks_coincidental_splits(fb):
    """leg+end / host+age / mass+age 都是巧合切分，必须仍判超纲。"""
    assert {"legend", "hostage", "massage"} <= set(_unknown(fb, "A legend, a hostage and a massage."))


def test_compound_right_root_must_be_word_length(fb):
    """affectation 曾被拆成 affect + ation：ation 剥掉 tion 落到单字母的 a，a 当然在词表里。
    右半剥后缀后的词根也要 ≥3 字母（系统词典扫描：这条规则拦住 864 个此类巧合放行）。"""
    assert "affectation" in _unknown(fb, "His speech was full of affectation.")


# ── 熟词白名单 ──

def test_mark_known_does_not_change_base_vocab_count(fb):
    before = len(fb.base_vocab)
    fb.mark_known(["zorblat"])
    assert len(fb.base_vocab) == before
    assert "zorblat" not in _unknown(fb, "A zorblat appeared.")


def test_whitelist_reloads_when_another_instance_marks(tmp_path):
    """vocab-checker 与 zhongkao-mcp 是两个进程：一边 mark_known，另一边不重启也要认。"""
    from vocab_checker import VocabChecker
    a = VocabChecker(str(VOCAB_MD), feedback_dir=str(tmp_path), record_stats=False)
    b = VocabChecker(str(VOCAB_MD), feedback_dir=str(tmp_path), record_stats=False)
    assert "zorblat" in _unknown(b, "A zorblat appeared.")
    a.mark_known(["zorblat"])
    assert "zorblat" not in _unknown(b, "A zorblat appeared.")


def test_mark_known_sanitizes_note_newlines(fb):
    """note 来自外部输入：含换行会把整行注入"一行一词"文件，被当作词读入。"""
    from vocab_checker import VocabChecker
    fb.mark_known(["zorblat"], note="first line\ninjectedword")
    fresh = VocabChecker(str(VOCAB_MD), feedback_dir=str(fb.feedback_dir), record_stats=False)
    assert fresh.extra_known == {"zorblat"}


def test_mark_known_accepts_words_with_digits(fb):
    assert fb.mark_known(["mp3"])["added"] == ["mp3"]
    assert "mp3" not in _unknown(fb, "I bought an mp3 player.")


def test_whitelist_file_entries_are_normalized_on_load(tmp_path):
    """手工编辑的白名单可能带引号/大写：加载口径要和 check() 剥标点的口径一致。"""
    from vocab_checker import VocabChecker
    (tmp_path / "extra_known_words.txt").write_text("'Zorblat'\n", encoding="utf-8")
    c = VocabChecker(str(VOCAB_MD), feedback_dir=str(tmp_path), record_stats=False)
    assert "zorblat" not in _unknown(c, "A zorblat appeared.")


# ── 超纲词命中统计 ──

def test_unknown_stats_keyed_by_lemma(fb):
    fb.check("Two zorblats and one zorblat.")
    assert set(_stats(fb)) == {"zorblat"}


def test_unknown_stats_count_distinct_texts_not_calls(fb):
    """同一篇稿子反复检查只算 1 篇：count 记不同文本数，hits 记总次数。"""
    text = "A zorblat appeared."
    fb.check(text)
    fb.check(text)
    fb.check("Another zorblat here.")
    e = _stats(fb)["zorblat"]
    assert (e["count"], e["hits"]) == (2, 3)


def test_corrupt_stats_entry_does_not_break_check(fb):
    """统计是辅助信息：文件被改坏也绝不能让 check()（主门禁）崩掉。"""
    (fb.feedback_dir / "unknown_word_stats.json").write_text('{"zorblat": 3}', encoding="utf-8")
    assert "zorblat" in _unknown(fb, "A zorblat appeared.")
    assert isinstance(fb.review_unknown_stats()["top"], list)


def test_legacy_stats_count_is_preserved(fb):
    """旧格式条目只有 count 没有 texts：换口径时不能把历史累计重置成 1，审核队列排序会断崖。"""
    (fb.feedback_dir / "unknown_word_stats.json").write_text(
        json.dumps({"zorblat": {"count": 7, "first_seen": "2026-10-01T00:00:00", "example": "old"}}),
        encoding="utf-8")
    fb.check("A zorblat appeared.")
    assert _stats(fb)["zorblat"]["count"] == 8


def test_record_stats_can_be_disabled_by_env(tmp_path, monkeypatch):
    """测试/CI 跑真实 check 不得往真实统计里写：默认值受 VOCAB_CHECKER_RECORD_STATS 控制。"""
    from vocab_checker import VocabChecker
    monkeypatch.setenv("VOCAB_CHECKER_RECORD_STATS", "0")
    c = VocabChecker(str(VOCAB_MD), feedback_dir=str(tmp_path))
    c.check("A zorblat appeared.")
    assert not (tmp_path / "unknown_word_stats.json").exists()


def test_review_clamps_negative_top_n(fb):
    fb.check("A zorblat and a quxbar and a flimzle.")
    assert fb.review_unknown_stats(top_n=-1)["top"] == []


# ── lemma 缓存 ──

def test_poisoned_cache_falls_back_to_rebuild(tmp_path):
    """缓存只是加速手段：内容坏了必须重建而不是让启动崩掉。"""
    import pickle
    from vocab_checker import VocabChecker
    md = _private_vocab(tmp_path)
    first = VocabChecker(str(md), feedback_dir=str(tmp_path), record_stats=False)
    first._cache_path().write_bytes(
        pickle.dumps({"key": first._cache_key(), "vocab_lemmas": None, "stem_to_vocab": None}))
    again = VocabChecker(str(md), feedback_dir=str(tmp_path), record_stats=False)
    assert again.vocab_lemmas == first.vocab_lemmas
    assert not again._loaded_from_cache


def test_cache_key_tracks_stem_rule_code(tmp_path, monkeypatch):
    """改了 _agg_stem 却忘了给 CACHE_VERSION +1 时，缓存键也必须变。"""
    from vocab_checker import VocabChecker
    md = _private_vocab(tmp_path)
    c = VocabChecker(str(md), feedback_dir=str(tmp_path), record_stats=False)
    before = c._cache_key()
    monkeypatch.setattr(VocabChecker, "_agg_stem", staticmethod(lambda w: w))
    assert c._cache_key() != before


# ── 专名通道 ──

def test_nationality_adjectives_are_not_counted_as_unknown(fb):
    """Irish/Egyptian 的 POS 是 ADJ，PROPN 通道抓不到，但 NER 标 NORP。"""
    r = fb.check("The Irish and Egyptian teams met in Paris.")
    assert not {"irish", "egyptian"} & set(r["unknown_words"])
    assert {"Irish", "Egyptian"} <= set(r["proper_noun_words"])


def test_unrecognized_capitalized_name_mid_sentence_goes_to_proper_bucket(fb):
    """spaCy 把 Ariely 标成 ADV：句中大写、不在词表的词应归疑似专名，而不是超纲。"""
    r = fb.check("Later, Dr. Ariely studied how people choose.")
    assert "ariely" not in r["unknown_words"]
    assert "Ariely" in r["proper_noun_words"]


def test_title_case_heading_words_still_count_as_unknown(fb):
    """标题行满是大写词：句中大写不能被当成人名放过去。"""
    assert "fossils" in _unknown(fb, "Ancient Fossils Reveal Secrets")


def test_title_line_followed_by_body_text_is_still_guarded(fb):
    """标题行无句号、紧跟正文时 spaCy 会把两者并成一句（连空行都隔不开）：
    标题判据必须按物理行，不能看分句末尾有没有句号。"""
    r = fb.check("Ancient Fossils Reveal Secrets\n\nScientists study them every day.")
    assert "fossils" in r["unknown_words"]
    assert "Fossils" not in r["proper_noun_words"]


def test_sentence_initial_capitalized_unknown_word_still_counts(fb):
    assert "fossils" in _unknown(fb, "Fossils are very old.")


# ── MCP 工具层 ──

def test_check_grade_level_accepts_proper_names():
    """check_text 收 proper_names，check_grade_level 也必须收，否则同一篇稿两个工具口径不一。"""
    import importlib.util
    # 两个 server 的入口都叫 mcp_server.py，全套一起跑时 sys.modules["mcp_server"] 可能已是 zhongkao-mcp 的；
    # 按文件路径、独立模块名加载，不受加载顺序影响
    spec = importlib.util.spec_from_file_location("vocab_checker_mcp_server", VOCAB_SRV)
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    r = srv.check_grade_level("The Zorblat Company opened a new shop in town.", proper_names=["Zorblat"])
    assert "zorblat" not in r["unknown_words"]
