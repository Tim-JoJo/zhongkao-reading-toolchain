"""
中考阅读文章写作 MCP Server (Part 1)
===================================
提供工具：
  1. check_passage          — 正文指标全检
  2. validate_questions     — 题目质量校验
  3. export_article_docx    — 导出文章 Word 文档
  4. export_docx            — 导出文章 + 题目 Word 文档
  5. draw_blueprint         — 随机抽取题目蓝图

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

    return run_check_passage(
        text=text,
        level=level,
        grade=grade,
        proper_names=proper_names or [],
        level_thresholds=LEVEL_THRESHOLDS[level],
        grade_limits=GRADE_LIMITS[grade],
    )


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
    return run_validate_questions(questions, option_count)


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
    if output_path is None:
        safe_name = re.sub(r'[<>:"/\\|?*]', '-', title)[:80]
        output_path = str(Path(DEFAULT_ARTICLE_DIR) / f"{safe_name}.docx")
    return run_export_docx(
        title=title,
        body=body,
        questions=questions,
        answer_key=answer_key,
        output_path=output_path,
        explanations=explanations,
    )


# ═══════════════════════════════════════════════════
# Tool 4: draw_blueprint — 随机抽取题目蓝图
# ═══════════════════════════════════════════════════

@mcp.tool()
def draw_blueprint(seed: int | None = None) -> dict[str, Any]:
    """随机抽取五题蓝图——从五个位置各随机选一个子题型。

    Q1(写作手法 30% 或 细节理解 70%) 从 WT-01~WT-06 / D-01~D-03·D-05~D-06 池中加权抽取，
    Q2(词义 70% 或 细节 30%) 从 V-01~V-04 / D-01~D-03·D-05~D-06 池中加权抽取，
    Q3(推理判断) 从 I-01~I-08(不含 I-05) 池中抽，
    Q4(排序 80% 或 推断 20%) 从 O-01~O-03 / I-01~I-08(不含 I-05) 池中加权抽取，
    Q5(主旨) 从 M-01~M-05 池中抽。

    Args:
        seed: 可选随机种子（调试用，通常不传）

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
    return run_draw_blueprint(seed=seed)


# ═══════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
