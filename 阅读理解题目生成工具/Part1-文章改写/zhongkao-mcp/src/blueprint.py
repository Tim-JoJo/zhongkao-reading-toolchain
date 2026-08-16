"""随机抽取题目蓝图。

从五个位置的题型池中各随机抽取一个子题型，
返回完整蓝图（编号、名称、模板、约束），供 Claude 出题使用。
"""

from __future__ import annotations

import random
from typing import Any

# ── 五个位置的题型池 ──
# 题位结构（中考作业体 5 题）：
#   Q1 写作手法(30%) or 细节理解(70%)（加权抽取）
#   Q2 词义猜测(70%) or 细节理解(30%)（加权抽取，词义:细节 = 7:3）
#   Q3 推理判断（固定，含段落主旨）
#   Q4 排序·事件顺序 80% / 推断题 20%（加权抽取，推断:排序 = 1:4）
#   Q5 主旨大意（固定）

BLUEPRINT_POOL = {
    # ── Q1 · 写作手法·开篇引入（30% 权重）──
    "writing_technique": {
        "WT-01": {
            "name": "提问引入",
            "template": "How does the writer begin/lead in the topic?",
            "constraint": "首段以问句引题；正确项 By asking questions",
        },
        "WT-02": {
            "name": "场景/画面描述",
            "template": "How does the writer begin the article to attract the readers?",
            "constraint": "首段以 'Imagine...' 等描述画面；正确项 By describing a possible future situation",
        },
        "WT-03": {
            "name": "讲故事引入",
            "template": "How does the writer begin the article?",
            "constraint": "首段讲一个小故事/案例；正确项 By telling a story",
        },
        "WT-04": {
            "name": "举例引入",
            "template": "How does the writer lead in the topic?",
            "constraint": "首段给出具体例子；正确项 By giving an example",
        },
        "WT-05": {
            "name": "列数字引入",
            "template": "How does the writer begin the article?",
            "constraint": "首段列出数据/统计；正确项 By listing numbers",
        },
        "WT-06": {
            "name": "对比引入",
            "template": "How does the writer lead in the topic?",
            "constraint": "首段对照两个事物；正确项 By comparing two different ideas",
        },
    },
    # ── Q2 · 词义猜测 or 细节理解（二选一）──
    "vocabulary_or_detail": {
        "V-01": {
            "name": "词义猜测-定义线索",
            "template": 'The word "X" means...',
            "constraint": "原文 ≤ 2 句内有 means / refers to / that is 或同位语/定语从句解释；取材：长难词(未加中文注释者)70% + 短语 30%",
        },
        "V-02": {
            "name": "词义猜测-对比线索",
            "template": '"X" probably means...',
            "constraint": "原文含 but / however / while / instead of / unlike 标记；取材：长难词(未加中文注释者)70% + 短语 30%",
        },
        "V-03": {
            "name": "词义猜测-因果线索",
            "template": '"X" probably means...',
            "constraint": "原文含 because / so / lead to / result in 因果链；取材：长难词(未加中文注释者)70% + 短语 30%",
        },
        "V-04": {
            "name": "词义猜测-构词法",
            "template": '"X" means...',
            "constraint": "超纲词根 + 课标词缀；取材：长难词(未加中文注释者)70% + 短语 30%",
        },
        "D-01": {
            "name": "细节-时间/地点/人物/数字",
            "template": "（谁）在（何地/何时）（做了什么）？",
            "constraint": "答案在原文 ≤ 1 句范围内精确定位",
        },
        "D-02": {
            "name": "细节-原因/结果",
            "template": "Why...? / What causes...?",
            "constraint": "原文需有 because / so / since / therefore 等显性因果标记，或 ≤ 2 句内可推断",
        },
        "D-03": {
            "name": "细节-方式/手段",
            "template": "How...?",
            "constraint": "原文需有 by / through / with / using 等显性方式标记",
        },
        "D-05": {
            "name": "细节-特征对比/属性",
            "template": "Which of the following is true about...?",
            "constraint": "答案与原文同义替换，核心语义不变",
        },
        "D-06": {
            "name": "细节-信息匹配/排除",
            "template": "Which is (NOT) mentioned?",
            "constraint": "3 项在原文有依据，1 项无依据",
        },
    },
    # ── Q3 · 推理判断（纯推理）──
    "inference": {
        "I-01": {
            "name": "隐含信息",
            "template": "What can we infer / learn from...?",
            "constraint": "正确答案不可为原文直接陈述；一步推理；范围：针对全文 90% + 针对某一段落 10%",
        },
        "I-02": {
            "name": "人物心理/动机",
            "template": "Why did the character...? / How did...feel?",
            "constraint": "原文有行为描述 → 推断心理状态",
        },
        "I-03": {
            "name": "人物关系/身份",
            "template": "Who is probably the writer? / Relationship?",
            "constraint": "原文有称谓、说话方式等身份提示",
        },
        "I-04": {
            "name": "后续发展",
            "template": "What will probably happen next?",
            "constraint": "原文末段有伏笔/暗示",
        },
        "I-06": {
            "name": "隐含因果",
            "template": "What led to...?",
            "constraint": "需综合多处细节推断",
        },
        "I-07": {
            "name": "信息合理性",
            "template": "Which statement is probably true?",
            "constraint": "3 个干扰项含事实/逻辑错误",
        },
        "I-08": {
            "name": "段落主旨",
            "template": "What is paragraph X mainly about?",
            "constraint": "对应主题句或核心事件；参考 Q5 的 M-03 段落大意，用于 Q3 推理位",
        },
    },
    # ── Q4 · 排序·事件顺序 ──
    "ordering": {
        "O-01": {
            "name": "记叙文事件排序",
            "template": "Put the events about X into the correct order.",
            "constraint": "每事件有明确时间标记/序列词；选项为字母序列（通常 3 个）",
        },
        "O-02": {
            "name": "故事发展顺序",
            "template": "Which of the following shows the correct order of what happened in the story?",
            "constraint": "叙事时间线（开头→过程→结果）；选项为字母序列",
        },
        "O-03": {
            "name": "说明文时代顺序",
            "template": "What is the correct time order of the following events?",
            "constraint": "朝代/时代标记（Tang Dynasty→Song Dynasty→nowadays）；选项为字母序列",
        },
    },
    # ── Q5 · 主旨大意 ──
    "main_idea": {
        "M-01": {
            "name": "最佳标题",
            "template": "What is the best title?",
            "constraint": "覆盖全文核心，范围不过宽/过窄",
        },
        "M-02": {
            "name": "全文主旨",
            "template": "The passage is mainly about...",
            "constraint": "概括 ≥ 3 个段落核心信息",
        },
        "M-03": {
            "name": "段落大意",
            "template": "What is paragraph X mainly about?",
            "constraint": "对应主题句或核心事件",
        },
        "M-04": {
            "name": "写作目的",
            "template": "What is the writer's purpose?",
            "constraint": "限于 to inform/describe/persuade/entertain/warn/advise",
        },
        "M-05": {
            "name": "文章来源",
            "template": "Where is it probably from?",
            "constraint": "匹配体裁特征",
        },
    },
}

# ── 位置 → 池 映射 ──
# Q1/Q2/Q4 特殊处理（加权抽取，见对应常量），其余位置直接映射到 BLUEPRINT_POOL
POSITION_POOLS = [
    ("writing_technique",   1, "写作手法"),
    ("vocabulary_or_detail",2, "词义或细节"),
    ("inference",           3, "推理判断"),
    ("ordering",            4, "排序"),
    ("main_idea",           5, "主旨"),
]

# ── Q1 加权抽取：写作手法 30% / 细节理解 70% ──
Q1_WT_WEIGHT = 0.3  # 写作手法占比，剩余 70% 为细节理解

# ── Q2 加权抽取：词义猜测 70% / 细节理解 30%（词义:细节 = 7:3）──
Q2_VOCAB_WEIGHT = 0.7  # 词义猜测占比，剩余 30% 为细节理解

# ── Q4 加权抽取：推断题 20% / 排序 80%（推断:排序 = 1:4）──
Q4_INFERENCE_WEIGHT = 0.2

# ── Q1 · 细节理解池（70% 权重，证据定位首段）──
Q1_DETAIL_POOL = {
    "D-01": {
        "name": "细节-时间/地点/人物/数字",
        "template": "（谁）在（何地/何时）（做了什么）？",
        "constraint": "首段内精确定位，答案 ≤ 1 句",
    },
    "D-02": {
        "name": "细节-原因/结果",
        "template": "Why...? / What causes...?",
        "constraint": "首段内有 because / so / since / therefore 显性因果标记，或 ≤ 2 句内可推断",
    },
    "D-03": {
        "name": "细节-方式/手段",
        "template": "How...?",
        "constraint": "首段内有 by / through / with / using 等显性方式标记",
    },
    "D-05": {
        "name": "细节-特征对比/属性",
        "template": "Which of the following is true about...?",
        "constraint": "首段内同义替换，核心语义不变",
    },
    "D-06": {
        "name": "细节-信息匹配/排除",
        "template": "Which is (NOT) mentioned?",
        "constraint": "3 项在首段有依据，1 项无依据",
    },
}


def run_draw_blueprint(seed: int | None = None) -> dict[str, Any]:
    """从五个位置的题型池中各随机抽取一个子题型。

    Q1 按加权抽取：写作手法 30% / 细节理解 70%。
    Q2 按加权抽取：词义猜测 70% / 细节理解 30%（词义:细节 = 7:3）。
    Q4 按加权抽取：推断题 20% / 排序 80%（推断:排序 = 1:4）。

    Args:
        seed: 可选随机种子，用于复现（调试用）

    Returns:
        dict: {
            "blueprint": [ 各位置抽取结果 ],
            "type_labels": ["writing_technique", "vocabulary_or_detail", "inference", "ordering", "main_idea"],
            "codes": ["WT-02", "V-01", "I-06", "O-01", "M-01"],
        }
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    blueprint = []
    codes = []
    type_labels = []

    for pool_key, position, function in POSITION_POOLS:
        if position == 1:
            # Q1 加权抽取：写作手法 30% / 细节理解 70%
            if rng.random() < Q1_WT_WEIGHT:
                pool = BLUEPRINT_POOL["writing_technique"]
                type_label = "writing_technique"
                function = "写作手法"
            else:
                pool = Q1_DETAIL_POOL
                type_label = "detail"
                function = "细节理解"
        elif position == 2:
            # Q2 加权抽取：词义猜测 70% / 细节理解 30%（词义:细节 = 7:3）
            if rng.random() < Q2_VOCAB_WEIGHT:
                pool = {k: v for k, v in BLUEPRINT_POOL["vocabulary_or_detail"].items() if k.startswith("V")}
                type_label = "vocabulary_or_detail"
                function = "词义猜测"
            else:
                pool = {k: v for k, v in BLUEPRINT_POOL["vocabulary_or_detail"].items() if k.startswith("D")}
                type_label = "detail"
                function = "细节理解"
        elif position == 4:
            # Q4 加权抽取：推断题 20% / 排序 80%（推断:排序 = 1:4）
            if rng.random() < Q4_INFERENCE_WEIGHT:
                pool = BLUEPRINT_POOL["inference"]
                type_label = "inference"
                function = "推理判断"
            else:
                pool = BLUEPRINT_POOL["ordering"]
                type_label = "ordering"
                function = "排序"
        else:
            pool = BLUEPRINT_POOL[pool_key]
            type_label = pool_key

        code = rng.choice(list(pool.keys()))
        info = pool[code]

        blueprint.append({
            "position": position,
            "function": function,
            "type": type_label,
            "code": code,
            "name": info["name"],
            "template": info["template"],
            "constraint": info["constraint"],
        })
        codes.append(code)
        type_labels.append(type_label)

    return {
        "blueprint": blueprint,
        "type_labels": type_labels,
        "codes": codes,
    }
