"""
中考阅读文章写作 MCP Server (Part 1)
===================================
提供工具：
  1. check_passage          — 正文指标全检(自动记录)
  2. validate_questions     — 题目质量校验(自动记录)
  3. export_article_docx    — 导出文章 Word 文档
  4. export_docx            — 导出文章 + 题目 Word 文档(缺前置步骤时拦截)
  5. draw_blueprint         — 随机抽取题目蓝图(自动记录)
  6. workflow_init          — 开新任务时初始化状态
  7. workflow_status        — 查看各步骤完成情况
  8. workflow_reset         — 清空状态

文章写作由 Claude 执行（遵循 SKILL.md），本 MCP 提供自动化支撑。
"""

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# ── 初始化 MCP 服务器 ──
mcp = FastMCP(
    "zhongkao-mcp",
    instructions="中考阅读文章写作工具链 — 提供正文指标全检、题目质量校验和 Word 文档导出。写作和出题由 Claude 执行，本 MCP 提供自动化支撑。",
)

# ── 导入工具模块 ──
import re
import sys
sys.path.insert(0, str(Path(__file__).parent))
from src.checker import run_check_passage
from src.validator import run_validate_questions
from src.exporter import (
    DEFAULT_ARTICLE_DIR,
    DEFAULT_REPORT_DIR,
    run_export_docx,
    run_export_article_docx,
)
from src.blueprint import run_draw_blueprint
from src.workflow import (
    cjk_count,
    export_annotation_warning,
    export_gate_errors,
    init_state,
    record_blueprint,
    record_check_passage,
    record_docx_exported,
    record_validate,
    reset_state,
    status_summary,
)

# ═══════════════════════════════════════════════════
# Tool 1: check_passage — 指标全检
# ═══════════════════════════════════════════════════

# 档位阈值（与 SKILL approved-standards.md 一致）
# 注意：word_count 上限 350 为硬性门槛——超出将返回 review_required 且 all_pass 为 false，
# 不得把超 350 词的文章标为可交付。
LEVEL_THRESHOLDS = {
    "standard": {
        "word_count": [0, 350],
        "average_sentence_length": [13, 15],
        "sentence_length_p90": [0, 24],
        "vocabulary_coverage": 0.90,
        "oov_distinct_max": 999,
        "proper_name_band": [0, 999],
    },
    "extended": {
        "word_count": [0, 350],
        "average_sentence_length": [16, 18],
        "sentence_length_p90": [0, 30],
        "vocabulary_coverage": 0.90,
        "oov_distinct_max": 999,
        "proper_name_band": [0, 999],
    },
}

GRADE_LIMITS = {
    9: {"coverage": [0.95, 0.97], "oov_ratio": [0.03, 0.05], "max_proper": 999, "max_sentence_len": 26},
}


@mcp.tool()
def check_passage(
    text: str,
    level: str = "standard",
    grade: int = 9,
    proper_names: list[str] | None = None,
) -> dict[str, Any]:
    """正文指标全检：词汇覆盖率 + 篇幅 + 句长 + 专名。

    组合 vocab-checker（spaCy 词形还原 + 派生词缀）和结构分析，
    对照档位阈值逐项判定通过/需复核。

    Args:
        text: 英文正文（不含标题）
        level: 档位 — "standard"（标准档）或 "extended"（拓展档）
        grade: 年级 — 本工具只面向九年级，固定 9；传入其他值将返回错误
        proper_names: 保留的专名实体列表，如 ["China", "WHO|World Health Organization"]，
                      同一实体的别名用 | 分隔

    Returns:
        dict: {
            "metrics": { 各指标实际值 + 阈值 + 状态 },
            "grade_check": { 年级合规判定 },
            "oov_details": [ 超纲词详情 ],
            "all_pass": bool
        }
    """
    if level not in LEVEL_THRESHOLDS:
        return {"error": f"未知档位: {level}，可选 standard / extended"}
    if grade != 9:
        return {"error": f"年级参数无效: {grade}。本工具只面向九年级，grade 必须为 9"}

    result = run_check_passage(
        text=text,
        level=level,
        grade=grade,
        proper_names=proper_names or [],
        level_thresholds=LEVEL_THRESHOLDS[level],
        grade_limits=GRADE_LIMITS[grade],
    )
    # 自动记录指标结果到工作流状态（供 export_docx 门禁用）
    if "error" not in result:
        record_check_passage(result)
    return result


# ═══════════════════════════════════════════════════
# Tool 2: validate_questions — 题目校验
# ═══════════════════════════════════════════════════

@mcp.tool()
def validate_questions(
    questions: list[dict],
    option_count: int = 4,
) -> dict[str, Any]:
    """题目质量校验：检查选项格式、答案唯一性、题目类型覆盖等。

    Args:
        questions: 题目列表，每题为 {"id": 1, "stem": "...", "options": ["A. ...", ...], "answer": "D", "type": "detail"}
        option_count: 每题应有选项数（3 或 4）

    Returns:
        dict: {
            "question_count": int,
            "option_count": int,
            "checks": { 各项检查状态 },
            "issues": [ 发现的问题 ],
            "all_pass": bool
        }
    """
    result = run_validate_questions(questions, option_count)
    # 自动记录校验结果到工作流状态（供 export_docx 门禁用）
    if "error" not in result:
        record_validate(result)
    return result


# ═══════════════════════════════════════════════════
# Tool 3: export_article_docx — 仅导出文章（Part 1 用）
# ═══════════════════════════════════════════════════

@mcp.tool()
def export_article_docx(
    title: str,
    body: str,
    output_path: str | None = None,
) -> str:
    """导出英文文章为 .docx 文档（不含题目）。

    Args:
        title: 文章标题
        body: 英文正文（段落用 \\n\\n 分隔）
        output_path: 输出文件路径（含 .docx 扩展名），不传则保存至 Downloads\生成文章

    Returns:
        str: 成功时返回保存路径，失败时返回错误信息
    """
    if output_path is None:
        safe_name = re.sub(r'[<>:"/\\|?*]', '-', title)[:80]
        output_path = str(Path(DEFAULT_ARTICLE_DIR) / f"{safe_name}.docx")
    return run_export_article_docx(
        title=title,
        body=body,
        output_path=output_path,
    )


# ═══════════════════════════════════════════════════
# Tool 4: export_docx — Word 导出（含题目，供 Part 2 用）
# ═══════════════════════════════════════════════════

@mcp.tool()
def export_docx(
    title: str,
    body: str,
    questions: list[dict],
    answer_key: list[str],
    output_path: str | None = None,
    explanations: list[str] | None = None,
) -> str:
    """将正文和选择题导出为 .docx 文档。

    Args:
        title: 文章标题
        body: 英文正文（段落用 \\n\\n 分隔）
        questions: 题目列表，每题 {"stem": "...", "options": ["A. ...", ...]}
        answer_key: 答案列表，如 ["D", "A", "B", "C"]
        output_path: 输出文件路径（含 .docx 扩展名），不传则保存至 Downloads\生成文章
        explanations: 每题答案解析（与题目一一对应），可选；传入则在 Answer Key 后渲染

    Returns:
        str: 成功时返回保存路径，失败时返回错误信息
    """
    # ── 工作流门禁：缺前置硬性步骤则拦截导出 ──
    errors = export_gate_errors(body)
    if errors:
        return "❌ 已拦截导出，缺少前置硬性步骤：\n" + "\n".join(f"  - {e}" for e in errors)
    warning = export_annotation_warning(body)

    if output_path is None:
        safe_name = re.sub(r'[<>:"/\\|?*]', '-', title)[:80]
        output_path = str(Path(DEFAULT_ARTICLE_DIR) / f"{safe_name}.docx")
    result = run_export_docx(
        title=title,
        body=body,
        questions=questions,
        answer_key=answer_key,
        output_path=output_path,
        explanations=explanations,
    )
    # 导出成功后自动记录（annotated_body = 正文是否含中文注释）
    if result.startswith("文档已保存"):
        record_docx_exported(annotated=bool(cjk_count(body) > 0))
    if warning:
        result = f"{result}\n{warning}"
    return result


# ═══════════════════════════════════════════════════
# Tool 4: draw_blueprint — 随机抽取题目蓝图
# ═══════════════════════════════════════════════════

@mcp.tool()
def draw_blueprint(seed: int | None = None, article_has_title: bool = False) -> dict[str, Any]:
    """随机抽取五题蓝图——从五个位置各随机选一个子题型。

    Q1(写作手法 30% 或 细节理解 70%) 从 WT-01~WT-06 / D-01~D-03·D-05~D-06 池中加权抽取，
    Q2(词义 70% 或 细节 30%) 从 V-01~V-04 / D-01~D-03·D-05~D-06 池中加权抽取，
    Q3(推理判断) 从 I-01~I-08(不含 I-05) 池中抽；抽中 I-08 段落主旨时按 main_idea/M-03 标注（标签 MAIN IDEA），
    Q4(排序 80% 或 推断 20%) 从 O-01~O-03 / I-01~I-08(不含 I-05) 池中加权抽取，
    Q5(主旨) 从 M-01~M-05 池中抽；article_has_title=true 时改从 I 类推断池抽（不出 best title）。

    Args:
        seed: 可选随机种子（调试用，通常不传）
        article_has_title: 文章是否已有标题。为 True 时 Q5 不出「最佳标题」(M-01)，改为推断题（I 类）

    Returns:
        dict: {
            "blueprint": [{
                "position": 1, "function": "写作手法",
                "type": "writing_technique", "code": "WT-06",
                "name": "对比引入", "template": "...", "constraint": "..."
            }, ...],
            "type_labels": ["writing_technique", "vocabulary_or_detail", "inference", "ordering", "main_idea"],
            "codes": ["WT-06", "V-02", "I-01", "O-03", "M-03"],
        }
    """
    result = run_draw_blueprint(seed=seed, article_has_title=article_has_title)
    # 自动记录蓝图已抽取（export_docx 门禁的硬性前置步骤）
    if "error" not in result:
        record_blueprint(result)
    return result


# ═══════════════════════════════════════════════════
# 辅助工具:工作流状态机
# （记录各硬性步骤完成情况;export_docx 在缺步时拦截导出。
#   纯 MCP 工具 + JSON 状态文件,兼容任何 MCP agent。）
# ═══════════════════════════════════════════════════

@mcp.tool()
def workflow_init(level: str) -> dict[str, Any]:
    """开新任务时初始化工作流状态(清空旧状态,记录档位)。

    任何 MCP agent 在开始一篇文章的改写/出题前,建议先调用本工具
    reset 状态,避免上一个任务的记录干扰本次导出门禁。

    Args:
        level: 档位 — "standard"(标准档)或 "extended"(拓展档)

    Returns:
        dict: 初始化后的完整状态,失败(档位非法)时返回 {"error": ...}
    """
    state = init_state(level)
    if state is None:
        return {"error": f"未知档位: {level},可选 standard / extended"}
    return {"ok": True, "state": state}


@mcp.tool()
def workflow_status() -> dict[str, Any]:
    """查看当前工作流状态:已完成步骤 / 待办步骤 / 原始状态。

    Returns:
        dict: {"level", "completed": [已完成的步骤], "missing": [待办的步骤], "state": 原始状态}
    """
    return status_summary()


@mcp.tool()
def workflow_reset() -> dict[str, Any]:
    """清空工作流状态(开新任务 / 重新开始一篇时调用)。

    Returns:
        dict: 清空后的默认状态
    """
    return {"ok": True, "state": reset_state()}


# ═══════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
