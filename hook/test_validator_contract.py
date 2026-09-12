"""校验器契约 hook —— 把"校验器实际查什么/不查什么"钉住。

对应踩过的坑：
  1. O-02 模板 `Which of the following shows the correct order…?` 曾因
     `"how" in stem.lower()` 子串判断必刷「题干可能缺少问号」噪音提示，诱导 agent 反复重写合规题干
  2. 排序题事件行必须 ①/②③④ 分行（写成 a./b. 或挤在一行会被挡）
  3. **校验器不检查答案分布** —— 该类倾斜没有机器兜底，只能靠 SKILL 的修正步骤；
     本 hook 把这个"没有兜底"的事实钉住，谁将来实现了分布校验，这里会立刻变红提醒改文档
"""
from __future__ import annotations

from src.validator import run_validate_questions

EV = "\n".join(["①. The team sent robots into the sea.", "②. The robots found tube worms.",
                 "③. The team published the maps.", "④. The robots returned to the ship."])
OPTS = ["A. ②①③④", "B. ①②③④", "C. ④③①②", "D. ③④②①"]


def q4(stem, answer="B", options=None, qtype="ordering"):
    return {"id": 4, "stem": stem, "options": options or OPTS, "answer": answer, "type": qtype}


def issues_of(q):
    return " | ".join(run_validate_questions([q], 4)["issues"])


def test_ordering_format_is_accepted():
    """清单前一句问句 + 事件行真实换行 ①②③④ → 不应刷任何排序/问号提示。"""
    got = issues_of(q4("Which of the following shows the correct order of what happened in the story?\n" + EV))
    assert "缺少问号" not in got, got
    assert "ordering 题 stem" not in got, got


def test_shows_substring_false_positive_is_fixed():
    """shows 内含 how —— 曾经必中误报，现已用词边界匹配。"""
    got = issues_of(q4("Which of the following shows the correct order?\n" + EV))
    assert "缺少问号" not in got, f"shows 的子串误报又回来了：{got}"


def test_real_how_without_question_mark_still_flagged():
    """真·缺问号要保留（别把误报修掉时顺手把真阳性也删了）。"""
    assert "缺少问号" in issues_of(q4("How did the events happen in order?\n" + EV))


def test_best_title_without_question_mark_still_flagged():
    assert "缺少问号" in issues_of(q4("Which would be the best title for the text?\n" + EV))


def test_events_not_on_separate_lines_is_flagged():
    got = issues_of(q4("Which is the correct order?\n①. A ②. B ③. C ④. D"))
    assert "ordering 题 stem" in got, got


def test_stem_quote_must_still_exist_in_body():
    """题干引号里的词必须还在正文中——这是改稿删词后长期查不出的失配。"""
    body = "Half of them slept for eight hours; the others stayed awake until midnight."
    qs = [{"id": 2, "stem": 'What do the underlined words "stayed awake" probably mean?',
           "options": ["A. Did not sleep", "B. Slept well", "C. Went home", "D. Read books"],
           "answer": "A", "type": "vocabulary_or_detail"},
          {"id": 3, "stem": 'What does the underlined word "float" mean?',
           "options": ["A. Rest", "B. Sit", "C. Rise", "D. Fall"], "answer": "C", "type": "detail"},
          {"id": 5, "stem": "What is the main idea of the passage?",
           "options": ["A. Sleep wastes time.", "B. Robots map the sea.", "C. Words are hard.",
                       "D. Sleep helps memory."], "answer": "D", "type": "main_idea"}]

    r_match = run_validate_questions(qs[:1] + qs[2:], 4, False, body)
    assert "stem_quote_in_body" not in r_match["checks"] or r_match["checks"]["stem_quote_in_body"] == "pass"

    r_mismatch = run_validate_questions(qs, 4, False, body)
    assert r_mismatch["checks"]["stem_quote_in_body"] == "review_required", r_mismatch
    assert any("float" in i for i in r_mismatch["issues"]), r_mismatch["issues"]
    assert r_mismatch["all_pass"] is False

    r_no_body = run_validate_questions(qs, 4)
    assert "stem_quote_in_body" not in r_no_body["checks"], "不传 body 时不应新增检查（向后兼容）"


def test_validator_does_not_check_answer_distribution():
    """特征化断言：同一字母出现 3 次不会让校验失败 —— 所以 SKILL 必须有修正步骤。"""
    qs = _full5_with_paras()
    r = run_validate_questions(qs, 4)
    assert r["all_pass"] is True, r["issues"]
    assert sum(1 for q in qs if q["answer"] == "A") == 3, "本用例就是 A×3 的倾斜题组"


# ── 证据段落单调性（answer_paragraph，2026-09-11 新增）──

def _full5_with_paras(paras=None):
    """一套能过全部既有检查的合法题组；paras 非 None 时按位置注入 answer_paragraph。"""
    import copy
    qs = [
        {"id": 1, "stem": "How does the writer begin the article?", "options": ["A. By asking questions", "B. By telling a story", "C. By listing numbers", "D. By giving an example"], "answer": "A", "type": "writing_technique"},
        {"id": 2, "stem": 'What does the underlined word "stages" probably mean?', "options": ["A. Places", "B. Steps", "C. Costs", "D. Names"], "answer": "A", "type": "vocabulary_or_detail"},
        {"id": 3, "stem": "What can we infer from the last paragraph?", "options": ["A. A fixed bedtime may help.", "B. Phones are banned at school.", "C. Teenagers sleep more than adults.", "D. Pills work better than habits."], "answer": "A", "type": "inference"},
        {"id": 4, "stem": "Which is the correct order of the events?\n" + EV, "options": OPTS, "answer": "C", "type": "ordering"},
        {"id": 5, "stem": "What is the main idea of the passage?", "options": ["A. Sleep is a waste of time.", "B. Robots map the sea floor.", "C. Students forget new words.", "D. Sleep helps the brain keep facts."], "answer": "D", "type": "main_idea"},
    ]
    qs = copy.deepcopy(qs)
    if paras is not None:
        for q, p in zip(qs, paras):
            q["answer_paragraph"] = p
    return qs


def test_evidence_paragraph_regression_blocks_export():
    """Qn > Qn+1 回退必须 review_required（阻断导出）——批量生产曾靠自律、无门禁。"""
    r = run_validate_questions(_full5_with_paras([1, 2, 4, 2, 5]), 4)
    assert r["checks"]["evidence_paragraph_order"] == "review_required"
    assert r["all_pass"] is False
    assert any("证据段落回退" in i for i in r["issues"]), r["issues"]


def test_evidence_paragraph_allows_skip_and_fulltext():
    """可跳段；排序/全文题不绑定单段（省略或「全文」）不参与比较。"""
    r = run_validate_questions(_full5_with_paras([1, 3, "全文", 4, 5]), 4)
    assert r["checks"]["evidence_paragraph_order"] == "pass", r["issues"]
    r2 = run_validate_questions(_full5_with_paras([1, 2, 3, 5, 5]), 4)
    assert r2["checks"]["evidence_paragraph_order"] == "pass", r2["issues"]


def test_evidence_paragraph_absent_is_backward_compatible():
    """不带 answer_paragraph 的旧题组不新增检查（向后兼容）。"""
    qs = _full5_with_paras()
    r = run_validate_questions(qs, 4)
    assert "evidence_paragraph_order" not in r["checks"]
    assert r["all_pass"] is True
