"""题目质量校验。

检查项：
- 每题选项数正确，字母连续
- 正确答案唯一且存在于选项中
- 题目类型覆盖（信息整合/逻辑推断/全篇理解/文本特征）
- 题干无 ask/question mark
- 选项长度平衡
- 无 all/never/only 等绝对词泄露
- 证据段落单调性（携带 answer_paragraph 时，Qn > Qn+1 即违规）
- 排序题事件行：stem 须以 ①② 开头逐行列出事件，缺失即 review_required（拦截导出）
"""

from __future__ import annotations

import re
from typing import Any


OPTION_LETTERS = {3: ["A", "B", "C"], 4: ["A", "B", "C", "D"]}

ABSOLUTE_PATTERNS = [
    r"\ball\b", r"\bnever\b", r"\balways\b", r"\bonly\b",
    r"\bnone\b", r"\bevery\b", r"\bno one\b",
]


def run_validate_questions(
    questions: list[dict],
    option_count: int = 4,
    article_has_title: bool = False,
    body: str | None = None,
) -> dict[str, Any]:
    """body 传入时额外校验「题干引号里的词是否还在正文中」。

    这是机器此前查不出的失配：实测 Q 问 "float"，改稿把该词改成 "big soft bag"，
    题干与正文从此对不上，而老的校验器只看选项格式与答案字母，一律放行。
    不传 body 时该检查不参与（保持向后兼容）。

    题目可携带 answer_paragraph（数字段号）参与「证据段落单调性」校验：
    按题序出现 Qn > Qn+1 即 review_required（SKILL 要求 Q1<…<Q5 单调递增）。
    排序/全文题不绑定单段，省略该字段或写「全文」即不参与比较。
    """
    if option_count not in OPTION_LETTERS:
        return {"error": f"option_count 须为 3 或 4，收到 {option_count}"}
    letters = OPTION_LETTERS[option_count]

    issues: list[str] = []
    checks: dict[str, str] = {}

    # ── 检查 1: 选项格式 ──
    format_ok = True
    for q in questions:
        qid = q.get("id", "?")
        opts = q.get("options") or []
        if len(opts) != option_count:
            issues.append(f"题{qid}：应有 {option_count} 个选项，实际 {len(opts)} 个")
            format_ok = False
        for i, opt in enumerate(opts):
            # letters[i] 在「选项数 > option_count」时越界：曾让整次校验抛 IndexError，
            # agent 只看到框架级报错、拿不到「应有 N 个选项」的修法提示。
            expected_prefix = f"{letters[i]}." if i < len(letters) else f"{chr(ord('A') + i)}."
            if not opt.strip().startswith(expected_prefix):
                issues.append(f"题{qid} 选项{i+1}：应以 {expected_prefix} 开头，实际 '{opt[:3]}...'")
                format_ok = False
        stem = q.get("stem", "")
        # 半角/全角问号都算问号结尾（条件原本重复写了两遍半角 "?"，全角 "？" 会被误报缺问号）
        if stem and not stem.strip().endswith(("?", "？")):
            # 题干应以问号结尾，但排序题以 ①~④ 事件清单结尾，故仅提醒。
            # 用词边界匹配：旧写法 "how" in stem.lower() 会被 "shows" 里的 how 命中，
            # 导致 O-02 模板（Which of the following shows the correct order…?）必然误报。
            if re.search(r"\b(?:why|how)\b", stem, re.IGNORECASE) or "best title" in stem.lower():
                issues.append(f"题{qid}：题干可能缺少问号")
    checks["option_format"] = "pass" if format_ok else "fail"

    # ── 检查 1b: 题干格式防错 ──
    # 1) stem 不应自带数字标号（导出器会自动编号，避免 "1. 1." 重复）——咨询性提示
    # 2) ordering 题 stem 应先用 ①②③④ 逐行列出事件（防"只给选项序列、没写事件"）——门禁项
    for q in questions:
        qid = q.get("id", "?")
        stem = (q.get("stem") or "").strip()
        if re.match(r"^\d+\s*[.．、]\s*", stem):
            issues.append(f"题{qid}：stem 以数字标号开头（'{stem[:4]}...'），导出器会自动编号，会变成 '1. 1.' 重复；请去掉数字前缀")
        if q.get("type") == "ordering":
            # 排序题事件用 ①~④ 标号，一行一个事件（CLAUDE.md 第 9 节）
            if not (re.search(r"(?m)^\s*①", stem) and re.search(r"(?m)^\s*②", stem)):
                issues.append(f"题{qid}：ordering 题 stem 应先用 ①/②/③/④ 列出各事件（每事件一行），再给选项序列")
                # 门禁项：缺失曾只进 issues、all_pass 仍为 true，旧式 a./b. 题组会照常导出
                checks["ordering_events"] = "review_required"
            else:
                checks.setdefault("ordering_events", "pass")
        if q.get("type") == "vocabulary_or_detail" and str(q.get("code", "")).startswith("V"):
            # 猜词题题干：真题格式 `What does the underlined word "X" in Paragraph N (probably) mean?`
            # 或兼容旧空线格式 `The word "X" ... means ______?`；须以问号结尾
            zhen_ti = re.match(r'^What do(es)? the underlined (?:word|words).*\bmean\b.*[?？]$', stem, re.IGNORECASE)
            if not (zhen_ti or ("______" in stem and stem.endswith(("?", "？")))):
                issues.append(f"题{qid}：猜词题 stem 应为真题格式 'What does the underlined word \"X\" in Paragraph N (probably) mean?' 或以 '______?' 空线结尾，当前为 '{stem}'")

    # ── 检查 2: 答案唯一性 ──
    answer_ok = True
    for q in questions:
        qid = q.get("id", "?")
        opts = q.get("options", [])
        answer = str(q.get("answer") or "").strip().upper()
        if answer not in letters:
            issues.append(f"题{qid}：答案 '{answer}' 不在有效字母 {letters} 中")
            answer_ok = False
    checks["unique_answer"] = "pass" if answer_ok else "fail"

    # ── 检查 3: 题目类型覆盖 ──
    types_present = {q.get("type", "") for q in questions}
    # 5 题结构：Q1 写作手法(30%) 或 细节理解(70%) + Q2 词义/细节 + Q3 推理 + Q4 排序(80%) 或 推断(20%) + Q5 主旨
    # writing_technique 非必选：Q1 抽中 detail 时由 detail 替代该位置
    # ordering 非必选：Q4 按 1:4 权重可能抽中推断题（inference），此时题组无排序题属正常
    expected_core = {"vocabulary_or_detail", "inference"}
    # 文章已有标题时 Q5 按硬性规则改出推断题（不出 M-01/M-02），main_idea 仅在 Q3
    # 抽中 I-08（自动转 M-03，约 5%）时出现，不作硬性覆盖要求——否则带标题文章
    # 的 type_coverage 必报 review_required 且重抽蓝图无法消除
    if not article_has_title:
        expected_core.add("main_idea")
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
        if article_has_title and "main_idea" not in normalized:
            issues.append("文章已有标题：Q5 已按硬性规则改出推断题，main_idea 不作硬性覆盖（本次题组未含主旨题，属正常）")

    # ── 检查 4: 选项长度平衡 ──
    balance_ok = True
    for q in questions:
        opts = q.get("options") or []
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
        opts = q.get("options") or []
        answer = str(q.get("answer") or "").strip().upper()
        correct_idx = letters.index(answer) if answer in letters else -1
        for i, opt in enumerate(opts):
            # 只检查干扰项（非正确答案）
            if i == correct_idx:
                continue
            opt_clean = re.sub(r"^[A-D]\.\s*", "", opt.strip())
            for pat in ABSOLUTE_PATTERNS:
                m = re.search(pat, opt_clean, re.IGNORECASE)
                if m:
                    # 干扰项下标可能超出 option_count（同检查 1 的越界场景）
                    label = letters[i] if i < len(letters) else chr(ord("A") + i)
                    issues.append(f"题{qid} 干扰项 {label} 含绝对词 '{m.group()}'，可能泄露")
                    leak_ok = False
    checks["absolute_word_leak"] = "pass" if leak_ok else "review_required"

    # ── 检查 6: 题干引用的词是否仍在正文（仅当传入 body）──
    if body is not None:
        quoted = []
        for q in questions:
            stem = q.get("stem", "") or ""
            for m in re.finditer(r'"([^"]+)"', stem):
                t = m.group(1).strip()
                if t and t not in quoted:
                    quoted.append(t)
        low = body.lower()
        missing = [t for t in quoted if t.lower() not in low]
        if missing:
            issues.append(f"题干引用的词在正文中找不到：{missing}（改稿删词后必须回头核对题干与正文）")
            checks["stem_quote_in_body"] = "review_required"
        else:
            checks["stem_quote_in_body"] = "pass"

    # ── 检查 7: 证据段落单调性（仅当题目携带 answer_paragraph 才参与，向后兼容）──
    # SKILL 第 3 步落点规划要求 Q1<Q2<Q3<Q4<Q5 单调递增；此前只靠命题 agent 自律，
    # 批量生产中出现过 Qn>Qn+1 回退（详见 hook/test_validator_contract）。
    # answer_paragraph：数字段号；排序/全文题不绑定单段，省略或写「全文」即不参与比较（可跳段，同段不算回退）。
    anchors = []
    for pos, q in enumerate(questions, 1):
        ap = q.get("answer_paragraph")
        if isinstance(ap, int) and not isinstance(ap, bool):
            anchors.append((pos, ap))
    if len(anchors) >= 2:
        drops = [
            (anchors[i][0], anchors[i][1], anchors[i + 1][0], anchors[i + 1][1])
            for i in range(len(anchors) - 1)
            if anchors[i][1] > anchors[i + 1][1]
        ]
        if drops:
            detail = "、".join(f"第{p1}题(段{a})→第{p2}题(段{b})" for p1, a, p2, b in drops)
            issues.append(f"证据段落回退：{detail}（违反 SKILL「Q1<Q2<Q3<Q4<Q5 单调递增」，请重排题序或重锚证据段）")
            checks["evidence_paragraph_order"] = "review_required"
        else:
            checks["evidence_paragraph_order"] = "pass"

    # ── 汇总 ──
    all_pass = all(v == "pass" for v in checks.values())

    return {
        "question_count": len(questions),
        "option_count": option_count,
        "checks": checks,
        "issues": issues,
        "all_pass": all_pass,
    }
