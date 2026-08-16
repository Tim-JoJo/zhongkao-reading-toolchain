"""工作流状态与导出门禁。

记录工具链各硬性步骤的完成情况到磁盘状态文件，供 export_docx 在导出前做
确定性拦截——即使 agent 遗漏步骤，导出也会被工具本身挡下并提示补做。

状态文件位置（按优先级）：
  1. 环境变量 ZHONGKAO_WORKFLOW_FILE 指定
  2. 当前工作目录 .zhongkao_workflow.json（每个项目独立）

兼容任何 MCP agent（Claude Code / Claude Desktop / Cursor 等）：
纯 MCP 工具 + 一个 JSON 状态文件，不依赖某一家 agent 的专属机制。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

# ── CJK 检测（注释为 `word（翻译）`，正文英文不含汉字）──
def cjk_count(text: str) -> int:
    """统计文本中的汉字数（CJK 统一表意文字）。"""
    return sum(1 for ch in text if "一" <= ch <= "鿿")


def _default_state() -> dict[str, Any]:
    return {
        "level": None,
        "part1": {
            "check_passage": None,   # {all_pass, word_count, oov_distinct, at}
            "report_exported": False,
        },
        "part2": {
            "blueprint_drawn": False,
            "blueprint_codes": [],
            "questions_validated": None,  # {all_pass, at}
            "docx_exported": False,
            "annotated_body": False,
        },
    }


def state_path() -> Path:
    """状态文件路径：环境变量优先，否则当前工作目录。"""
    env = os.environ.get("ZHONGKAO_WORKFLOW_FILE")
    if env:
        return Path(env)
    return Path(os.getcwd()) / ".zhongkao_workflow.json"


def get_state() -> dict[str, Any]:
    """读取当前状态（文件不存在或损坏时返回默认空状态）。"""
    p = state_path()
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            base = _default_state()
            # 浅合并，缺失字段用默认值兜底
            for k in base:
                if k in data and isinstance(base[k], dict) and isinstance(data[k], dict):
                    base[k].update(data[k])
                elif k in data:
                    base[k] = data[k]
            return base
    except (OSError, ValueError):
        pass
    return _default_state()


def save_state(state: dict[str, Any]) -> None:
    """原子写入状态文件。"""
    p = state_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".zhongkao_wf_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, p)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        # 状态写入失败不阻断主流程（门禁降级为软检查）
        pass


def reset_state() -> dict[str, Any]:
    """清空状态（开新任务时调用）。"""
    state = _default_state()
    save_state(state)
    return state


def init_state(level: str) -> dict[str, Any] | None:
    """以指定档位初始化状态；档位非法时返回 None。"""
    if level not in ("standard", "extended"):
        return None
    state = _default_state()
    state["level"] = level
    save_state(state)
    return state


# ── 自动记录（由 MCP 工具调用，无需 agent 自觉）──

def record_check_passage(result: dict[str, Any]) -> None:
    state = get_state()
    metrics = result.get("metrics", {})
    wc = metrics.get("word_count", {}).get("value", 0)
    oov = len(metrics.get("oov_distinct", {}).get("value", []))
    state["part1"]["check_passage"] = {
        "all_pass": bool(result.get("all_pass")),
        "word_count": wc,
        "oov_distinct": oov,
        "at": _now(),
    }
    save_state(state)


def record_blueprint(result: dict[str, Any]) -> None:
    state = get_state()
    state["part2"]["blueprint_drawn"] = True
    state["part2"]["blueprint_codes"] = result.get("codes", []) if result else []
    save_state(state)


def record_validate(result: dict[str, Any]) -> None:
    state = get_state()
    state["part2"]["questions_validated"] = {
        "all_pass": bool(result.get("all_pass")) if result else False,
        "at": _now(),
    }
    save_state(state)


def record_docx_exported(annotated: bool) -> None:
    state = get_state()
    state["part2"]["docx_exported"] = True
    state["part2"]["annotated_body"] = bool(annotated)
    save_state(state)


def _now() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


# ── 导出门禁 ──

def export_gate_errors(body: str) -> list[str]:
    """返回导出前应拦截的原因列表；空列表 = 允许导出。

    拦截原则：宁可拦住让 agent 补做，也不放行明显缺步的交付。
    """
    state = get_state()
    errors: list[str] = []

    # ① 漏抽蓝图（Part2 硬性步骤）
    if not state.get("part2", {}).get("blueprint_drawn"):
        errors.append(
            "未调用 draw_blueprint 抽取题目蓝图。请先调用 mcp__zhongkao-mcp__draw_blueprint "
            "抽取五题蓝图后再导出。"
        )

    # ② validate_questions 未通过（Part2 硬性步骤）
    qv = state.get("part2", {}).get("questions_validated") or {}
    if qv.get("all_pass") is not True:
        errors.append(
            "validate_questions 未通过(all_pass != true)。请修正后重新调用 "
            "mcp__zhongkao-mcp__validate_questions 校验至 all_pass 为 true 再导出。"
        )

    # ③ 正文忘带中文注释（Part1 交付给 Part2 的正文应为带注释版）
    if cjk_count(body) == 0:
        cp = state.get("part1", {}).get("check_passage") or {}
        oov = cp.get("oov_distinct", 0)
        if oov > 0:
            errors.append(
                f"正文未包含中文注释(检测到 0 个汉字)，但 check_passage 检出 {oov} 个超纲词。"
                "请为超纲词添加中文注释(带注释版正文)后再导出；不要导出无注释的检查版正文。"
            )

    return errors


def export_annotation_warning(body: str) -> str | None:
    """无 check_passage 状态时的软提示（不阻断，仅提醒确认）。"""
    state = get_state()
    if cjk_count(body) == 0 and not state.get("part1", {}).get("check_passage"):
        return "⚠️ 提示：正文未包含中文注释。若文章含超纲词，请确认已按规则添加中文注释(带注释版正文)。"
    return None


# ── 状态汇总（workflow_status 用）──

def status_summary() -> dict[str, Any]:
    """返回可读的状态汇总：已完成 / 待办 / 原始状态。"""
    state = get_state()
    done: list[str] = []
    missing: list[str] = []

    cp = state.get("part1", {}).get("check_passage")
    if cp:
        done.append(f"Part1 指标检查(check_passage) {'通过(all_pass)' if cp.get('all_pass') else '未通过'}"
                    f" | 词数 {cp.get('word_count')} | 超纲词 {cp.get('oov_distinct')}")
    else:
        missing.append("Part1 指标检查(check_passage)")

    bp = state.get("part2", {}).get("blueprint_drawn")
    if bp:
        codes = state.get("part2", {}).get("blueprint_codes", [])
        done.append(f"Part2 蓝图已抽取(draw_blueprint) {codes}")
    else:
        missing.append("Part2 蓝图抽取(draw_blueprint)")

    qv = state.get("part2", {}).get("questions_validated")
    if qv:
        done.append(f"Part2 题目校验(validate_questions) {'通过(all_pass)' if qv.get('all_pass') else '未通过'}")
    else:
        missing.append("Part2 题目校验(validate_questions)")

    if state.get("part2", {}).get("docx_exported"):
        done.append("Part2 题目 Word 已导出(export_docx)")

    return {
        "level": state.get("level"),
        "completed": done,
        "missing": missing,
        "state": state,
    }
