"""导出门禁 hook —— 抓"漏做步骤照样导出"和"改完正文还用旧校验放行"。

对应踩过的坑：
  1. 未抽蓝图 / 未过 validate / 正文漏了中文注释 → 必须拦截（SKILL 的门禁兜底）
  2. **状态只记 all_pass 的布尔值、不记正文** —— 校验完 A 稿、改成 B 稿照样导出。
     现在状态里存正文内容指纹，导出时比对。
  3. 指纹必须忽略中文注释：SKILL 规定的流程是「无注释正文先过 check_passage，
     导出前最后一步才加注释」，若连注释都算内容变化，合规交付会被拦死。
"""
from __future__ import annotations

import pytest
from src import workflow
from src.workflow import content_fingerprint, export_gate_errors

BODY = ("Most people know that sleep helps the body rest. New research suggests it also helps "
        "the brain tidy up. During the night, the brain sorts the things you learned in the day.")
ANNOTATED = BODY.replace("tidy up", "tidy up（整理）")
CHANGED = BODY.replace("sleep helps the body rest", "sleep helps the body grow stronger")

OOV_RESULT = {"all_pass": True,
              "metrics": {"word_count": {"value": 179}, "oov_distinct": {"value": ["tube", "dive"]}}}
CLEAN_RESULT = {"all_pass": True,
                "metrics": {"word_count": {"value": 179}, "oov_distinct": {"value": []}}}


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHONGKAO_WORKFLOW_FILE", str(tmp_path / "wf.json"))
    workflow.reset_state()
    return tmp_path / "wf.json"


def _complete_state(annotated=True):
    workflow.record_blueprint({"codes": ["WT-01", "V-02", "I-01", "O-01", "M-01"]})
    workflow.record_validate({"all_pass": True})
    workflow.record_check_passage(OOV_RESULT, ANNOTATED if annotated else BODY)


def test_blocks_without_blueprint(state):
    errs = export_gate_errors(ANNOTATED)
    assert any("draw_blueprint" in e for e in errs), errs


def test_blocks_without_validate(state):
    workflow.record_blueprint({"codes": ["WT-01"]})
    errs = export_gate_errors(ANNOTATED)
    assert any("validate_questions" in e for e in errs), errs


def test_blocks_when_oov_present_but_body_not_annotated(state):
    workflow.record_blueprint({"codes": ["WT-01"]})
    workflow.record_validate({"all_pass": True})
    workflow.record_check_passage(OOV_RESULT, BODY)
    errs = export_gate_errors(BODY)
    assert any("中文注释" in e for e in errs), errs


def test_allows_when_all_steps_done(state):
    _complete_state()
    assert export_gate_errors(ANNOTATED) == []


def test_blocks_after_content_change(state):
    """核心：校验后改了英文内容 → 必须拦住，要求重跑 check_passage。"""
    _complete_state()
    errs = export_gate_errors(CHANGED)
    assert any("指纹" in e for e in errs), errs


def test_annotation_only_change_is_allowed(state):
    """只增删中文注释不算内容变化（否则 SKILL 的「注释最后一步加」流程会被拦死）。"""
    _complete_state(annotated=False)
    assert export_gate_errors(ANNOTATED) == []
    assert content_fingerprint(ANNOTATED) == content_fingerprint(BODY)


def test_fingerprint_ignores_cjk_punctuation_and_whitespace():
    a = content_fingerprint("The brain tidies up（整理）at night.")
    b = content_fingerprint("the   brain tidies up at night.")
    assert a == b, "指纹应忽略中文注释、全角标点与空白差异"
    assert a != content_fingerprint("The brain rests at night.")
    # 真实形态：注释紧贴单词、后面直接接下一个词（CLAUDE.md 举过的 urgency（紧迫）and）
    assert content_fingerprint("urgency（紧迫）and worry") == content_fingerprint("urgency and worry"), \
        "紧贴式注释不得改变指纹，否则合规流程会被拦死"


def test_fingerprint_list_survives_multiple_agents(state):
    """同一工作目录里多个 agent / 多篇稿并行时，后一次的校验不得顶掉前一次的有效记录。"""
    _complete_state()                       # 文章 A 校验通过（OOV_RESULT + ANNOTATED 指纹）
    workflow.record_check_passage(CLEAN_RESULT, CHANGED)   # 另一个 agent 校验了文章 B
    assert export_gate_errors(ANNOTATED) == [], "文章 A 的记录被文章 B 覆盖了"
    fps = workflow.get_state()["part1"]["check_fingerprints"]
    assert len(fps) == 2, fps
    assert export_gate_errors("A third, never-checked passage."), "从未校验过的正文仍应被拦"


def test_fingerprint_list_is_capped(state):
    for i in range(30):
        workflow.record_check_passage(CLEAN_RESULT, f"Passage number {i}.")
    fps = workflow.get_state()["part1"]["check_fingerprints"]
    assert len(fps) == 20, f"清单应有上限避免无限增长，实际 {len(fps)}"


def test_old_state_without_fingerprint_is_not_blocked(state):
    """向后兼容：旧版本写下的状态没有 fingerprint 字段时，不做内容比对（软降级）。"""
    workflow.record_blueprint({"codes": ["WT-01"]})
    workflow.record_validate({"all_pass": True})
    st = workflow.get_state()
    st["part1"]["check_passage"] = {"all_pass": True, "word_count": 179, "oov_distinct": 0}
    workflow.save_state(st)
    assert export_gate_errors(ANNOTATED) == []
