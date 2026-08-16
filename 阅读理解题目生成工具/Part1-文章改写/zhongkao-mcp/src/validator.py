"""题目质量校验。

检查项：
- 每题选项数正确，字母连续
- 正确答案唯一且存在于选项中
- 题目类型覆盖（信息整合/逻辑推断/全篇理解/文本特征）
- 题干无 ask/question mark
- 选项长度平衡
- 无 all/never/only 等绝对词泄露
"""

from __future__ import annotations

import re
import statistics
from typing import Any


OPTION_LETTERS = {3: ["A", "B", "C"], 4: ["A", "B", "C", "D"]}

RECOMMENDED_TYPES = {
    "writing_technique",     # Q1 写作手法·开篇引入（30%）或 detail（70%）替代
    "vocabulary_or_detail",  # Q2 词义猜测 or 细节理解
    "inference",             # Q3 逻辑推断
    "ordering",              # Q4 排序·事件顺序
    "main_idea",             # Q5 主旨/标题/目的
}

ABSOLUTE_PATTERNS = [
    r"\ball\b", r"\bnever\b", r"\balways\b", r"\bonly\b",
    r"\bnone\b", r"\bevery\b", r"\bno one\b",
]


def run_validate_questions(
    questions: list[dict],
    option_count: int = 4,
) -> dict[str, Any]:
    if option_count not in OPTION_LETTERS:
        return {"error": f"option_count 须为 3 或 4，收到 {option_count}"}
    letters = OPTION_LETTERS[option_count]

    issues: list[str] = []
    checks: dict[str, str] = {}

    # ── 检查 1: 选项格式 ──
    format_ok = True
    for q in questions:
        qid = q.get("id", "?")
        opts = q.get("options", [])
        if len(opts) != option_count:
            issues.append(f"题{qid}：应有 {option_count} 个选项，实际 {len(opts)} 个")
            format_ok = False
        for i, opt in enumerate(opts):
            expected_prefix = f"{letters[i]}."
            if not opt.strip().startswith(expected_prefix):
                issues.append(f"题{qid} 选项{i+1}：应以 {expected_prefix} 开头，实际 '{opt[:3]}...'")
                format_ok = False
        stem = q.get("stem", "")
        if stem and not stem.strip().endswith("?") and not stem.strip().endswith("?"):
            # 题干应以问号结尾，但有些题型（如完成句子）可能不用问号，故仅提醒
            if "best title" in stem.lower() or "why" in stem.lower() or "how" in stem.lower():
                if not stem.strip().endswith("?"):
                    issues.append(f"题{qid}：题干可能缺少问号")
    checks["option_format"] = "pass" if format_ok else "fail"

    # ── 检查 1b: 题干格式防错（咨询性，不影响 all_pass）──
    # 1) stem 不应自带数字标号（导出器会自动编号，避免 "1. 1." 重复）
    # 2) ordering 题 stem 应先用 a./b./c./d. 列出事件（防"只给选项序列、没写事件"）
    for q in questions:
        qid = q.get("id", "?")
        stem = q.get("stem", "").strip()
        if re.match(r"^\d+\s*[.．、]\s*", stem):
            issues.append(f"题{qid}：stem 以数字标号开头（'{stem[:4]}...'），导出器会自动编号，会变成 '1. 1.' 重复；请去掉数字前缀")
        if q.get("type") == "ordering":
            # 排序题事件用 ①~④ 标号，一行一个事件
            if not (re.search(r"(?m)^\s*①", stem) and re.search(r"(?m)^\s*②", stem)):
                issues.append(f"题{qid}：ordering 题 stem 应先用 ①/②/③/④ 列出各事件（每事件一行），再给选项序列")

    # ── 检查 2: 答案唯一性 ──
    answer_ok = True
    for q in questions:
        qid = q.get("id", "?")
        opts = q.get("options", [])
        answer = q.get("answer", "").strip().upper()
        if answer not in letters:
            issues.append(f"题{qid}：答案 '{answer}' 不在有效字母 {letters} 中")
            answer_ok = False
    checks["unique_answer"] = "pass" if answer_ok else "fail"

    # ── 检查 3: 题目类型覆盖 ──
    types_present = {q.get("type", "") for q in questions}
    # 5 题结构：Q1 写作手法(30%) 或 细节理解(70%) + Q2 词义/细节 + Q3 推理 + Q4 排序(80%) 或 推断(20%) + Q5 主旨
    # writing_technique 非必选：Q1 抽中 detail 时由 detail 替代该位置
    # ordering 非必选：Q4 按 1:4 权重可能抽中推断题（inference），此时题组无排序题属正常
    expected_core = {"vocabulary_or_detail", "inference", "main_idea"}
    # 旧 4 题结构兼容：detail 视为 vocabulary_or_detail 的同类，text_feature 视为（词义/排序）可替代
    legacy_aliases = {
        "detail": "vocabulary_or_detail",
        "integration": "vocabulary_or_detail",
        "text_feature": "ordering",
    }
    normalized = {legacy_aliases.get(t, t) for t in types_present}
    missing = expected_core - normalized
    if missing:
        issues.append(f"题目类型可能缺失：{missing}（当前类型：{types_present}）")
        checks["type_coverage"] = "review_required"
    else:
        checks["type_coverage"] = "pass"

    # ── 检查 4: 选项长度平衡 ──
    balance_ok = True
    for q in questions:
        opts = q.get("options", [])
        lengths = [len(opt.strip()) for opt in opts]
        if lengths and max(lengths) > 2 * min(lengths) and max(lengths) - min(lengths) > 30:
            qid = q.get("id", "?")
            issues.append(f"题{qid}：选项长度差异较大 ({min(lengths)}–{max(lengths)}字符)，可能泄露答案")
            balance_ok = False
    checks["balanced_options"] = "pass" if balance_ok else "review_required"

    # ── 检查 5: 绝对词泄露 ──
    leak_ok = True
    for q in questions:
        qid = q.get("id", "?")
        opts = q.get("options", [])
        answer = q.get("answer", "").strip().upper()
        correct_idx = letters.index(answer) if answer in letters else -1
        for i, opt in enumerate(opts):
            # 只检查干扰项（非正确答案）
            if i == correct_idx:
                continue
            opt_clean = re.sub(r"^[A-D]\.\s*", "", opt.strip())
            for pat in ABSOLUTE_PATTERNS:
                if re.search(pat, opt_clean, re.IGNORECASE):
                    issues.append(f"题{qid} 干扰项 {letters[i]} 含绝对词 '{re.search(pat, opt_clean, re.IGNORECASE).group()}'，可能泄露")
                    leak_ok = False
    checks["absolute_word_leak"] = "pass" if leak_ok else "review_required"

    # ── 汇总 ──
    all_pass = all(v == "pass" for v in checks.values())

    return {
        "question_count": len(questions),
        "option_count": option_count,
        "checks": checks,
        "issues": issues,
        "all_pass": all_pass,
    }
