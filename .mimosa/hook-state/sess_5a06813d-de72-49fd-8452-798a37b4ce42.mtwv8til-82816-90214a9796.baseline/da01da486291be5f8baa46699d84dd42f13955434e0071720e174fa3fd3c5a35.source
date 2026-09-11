"""导出门禁 hook —— 抓"漏做步骤照样导出"、"改完正文还用旧校验放行"和"档位没问就开跑"。

对应踩过的坑：
  1. 未抽蓝图 / 未过 validate / 正文漏了中文注释 → 必须拦截（SKILL 的门禁兜底）
  2. **状态只记 all_pass 的布尔值、不记正文** —— 校验完 A 稿、改成 B 稿照样导出。
     现在状态里存正文内容指纹，导出时比对。
  3. 指纹必须忽略中文注释：SKILL 规定的流程是「无注释正文先过 check_passage，
     导出前最后一步才加注释」，若连注释都算内容变化，合规交付会被拦死。
  4. **档位漏问用户**：CLAUDE.md 第 5 节与两个 SKILL 的 🔴 CHECKPOINT 都要求先问
     standard / extended，但过去 check_passage 的签名自带 default="standard"、
     导出侧没有任何工具读 state["level"]，漏问照样能静默按标准档跑完并交付。
     现在档位只认显式的 workflow_init(level=...)：未登记则指标检查 / 题目导出 /
     报告导出全部拦截；登记档位与实跑档位不一致同样拦截。
"""
from __future__ import annotations

import pytest
from src import workflow
from src.workflow import content_fingerprint, export_gate_errors, level_gate_errors

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


def _complete_state(annotated=True, level: str | None = "standard"):
    """把四道硬性步骤都做完；level=None 表示"档位从未登记"。"""
    if level is None:
        workflow.reset_state()
    else:
        workflow.init_state(level)      # init 会清空旧记录，故必须最先调用
    workflow.record_blueprint({"codes": ["WT-01", "V-02", "I-01", "O-01", "M-01"]})
    workflow.record_validate({"all_pass": True})
    workflow.record_check_passage(OOV_RESULT, ANNOTATED if annotated else BODY, level=level)


# ══════════════════════════════════════════════════
# A. 档位：必须先问用户（CLAUDE.md 第 5 节的机器兜底）
# ══════════════════════════════════════════════════

def test_level_gate_blocks_until_registered(state):
    """档位没登记 → 门禁报"档位未登记"；登记之后放行。"""
    errs = level_gate_errors("standard")
    assert any("档位未登记" in e for e in errs), errs
    workflow.init_state("standard")
    assert level_gate_errors("standard") == []


def test_check_passage_does_not_register_level_implicitly(state):
    """指标检查**不得**顺手把档位记成"用户的选择"。

    否则 check_passage 签名里的 default="standard" 会替 agent 完成"决定"，
    门禁变成永远通过，等于没做这条护栏。
    """
    workflow.record_check_passage(OOV_RESULT, ANNOTATED, level="standard")
    st = workflow.get_state()
    assert st["level"] is None, "check_passage 不该写 state['level']"
    assert st["part1"]["check_passage"]["level"] == "standard", "但应记下本次实跑档位"
    assert any("档位未登记" in e for e in export_gate_errors(ANNOTATED))


def test_export_blocked_when_level_never_registered(state):
    """其余四道步骤都齐、只缺档位登记 → 仍然不许导出。"""
    _complete_state(level=None)
    errs = export_gate_errors(ANNOTATED)
    assert len(errs) == 1 and "档位未登记" in errs[0], errs


def test_export_blocked_when_run_level_differs_from_registered(state):
    """登记 extended、却按 standard 校指标（用错标尺）→ 拦。"""
    _complete_state(level="standard")
    workflow.record_check_passage(OOV_RESULT, ANNOTATED, level="extended")
    errs = export_gate_errors(ANNOTATED)
    assert any("档位不一致" in e for e in errs), errs


def test_status_summary_surfaces_missing_level(state):
    r = workflow.status_summary()
    assert r["level"] is None
    assert any("档位登记" in m for m in r["missing"]), r["missing"]
    workflow.init_state("extended")
    r = workflow.status_summary()
    assert r["level"] == "extended"
    assert any("档位已登记" in d for d in r["completed"]), r["completed"]


def test_check_passage_tool_is_gated(state):
    """MCP 工具层：未登记档位时 check_passage 直接返回错误（不产出指标、不留指纹）。"""
    pytest.importorskip("mcp", reason="加载 zhongkao-mcp 需要 mcp")
    pytest.importorskip("spacy", reason="加载 zhongkao-mcp 需要 spacy")
    import importlib.util
    import sys

    from conftest import MCP

    # 按路径加载 zhongkao-mcp 的 server：sys.path 里还有 vocab-checker/mcp_server.py，
    # 直接 `import mcp_server` 会撞名拿到另一个 server（曾如此踩过）。
    if str(MCP) not in sys.path:
        sys.path.insert(0, str(MCP))
    spec = importlib.util.spec_from_file_location("zk_mcp_server", MCP / "mcp_server.py")
    mcp_server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mcp_server)

    blocked = mcp_server.check_passage(BODY, level="standard")
    assert "error" in blocked and "档位未登记" in blocked["error"], blocked
    assert workflow.get_state()["part1"]["check_passage"] is None, "被拦时不得留下指标记录"

    workflow.init_state("standard")
    ok = mcp_server.check_passage(BODY, level="standard")
    assert "error" not in ok, ok
    assert ok["metrics"]["word_count"]["value"] > 0


def test_report_export_is_gated(state, tmp_path):
    """Part1 的报告 Word 过去完全无门禁 —— 现在与题目导出一致，缺档位即拦。"""
    pytest.importorskip("docx", reason="报告导出需要 python-docx")
    from src.exporter import is_report_ok, run_export_report_docx

    out = tmp_path / "report.docx"
    blocked = run_export_report_docx(
        title="测试报告", content=[{"heading": "一", "paragraphs": ["x"]}], output_path=str(out))
    assert blocked.startswith("❌ 已拦截导出") and "档位未登记" in blocked, blocked
    assert not out.exists(), "被拦时不得写出文件"

    workflow.init_state("standard")
    ok = run_export_report_docx(
        title="测试报告", content=[{"heading": "一", "paragraphs": ["x"]}], output_path=str(out))
    assert is_report_ok(ok), ok
    assert out.exists()


# ══════════════════════════════════════════════════
# B. 漏步 / 改文后仍想放行（原有护栏）
# ══════════════════════════════════════════════════

def test_blocks_without_blueprint(state):
    workflow.init_state("standard")
    errs = export_gate_errors(ANNOTATED)
    assert any("draw_blueprint" in e for e in errs), errs


def test_blocks_without_validate(state):
    workflow.init_state("standard")
    workflow.record_blueprint({"codes": ["WT-01"]})
    errs = export_gate_errors(ANNOTATED)
    assert any("validate_questions" in e for e in errs), errs


def test_blocks_when_oov_present_but_body_not_annotated(state):
    workflow.init_state("standard")
    workflow.record_blueprint({"codes": ["WT-01"]})
    workflow.record_validate({"all_pass": True})
    workflow.record_check_passage(OOV_RESULT, BODY, level="standard")
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
    workflow.init_state("standard")
    workflow.record_blueprint({"codes": ["WT-01"]})
    workflow.record_validate({"all_pass": True})
    st = workflow.get_state()
    st["part1"]["check_passage"] = {"all_pass": True, "word_count": 179, "oov_distinct": 0}
    workflow.save_state(st)
    assert export_gate_errors(ANNOTATED) == []
