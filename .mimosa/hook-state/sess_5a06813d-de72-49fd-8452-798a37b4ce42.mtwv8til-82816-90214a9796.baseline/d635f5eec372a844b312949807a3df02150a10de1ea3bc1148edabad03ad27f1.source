"""档位 / 年级阈值 —— 两个 MCP server 共用的唯一定义。

放这一层的原因：zhongkao-mcp（指标检查）与 vocab-checker（独立年级校验）都要用同一套数字，
历史上的做法是各存一份，结果互相漂移（tests 里还留着 word_count [220,240] 的旧档）。
现在两侧都只往上探一层 import 本模块；`hook/test_doc_consistency.py::test_threshold_single_source`
会拦住任何重新抄副本的行为。

改数字只改这里。
"""

# 档位阈值（与 SKILL references/approved-standards.md 一致）
# word_count 上限 350 为硬性门槛：超出即 all_pass=False，不得标为可交付。
LEVEL_THRESHOLDS = {
    "standard": {
        "word_count": [0, 350],
        "average_sentence_length": [13, 15],   # 双侧带区：高/低都 review_required
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
    9: {
        "coverage": [0.95, 0.97],   # 双侧带区：太高（词太简单）同样 review_required
        "oov_ratio": [0.03, 0.05],
        # 专名不设数量限制：article-writer SKILL 第 4 步明确「专名默认保留，不做泛化……
        # 保留 5 个、8 个甚至更多专名均可，只要每个都承担信息功能」。此处 999 即"无上限"，
        # 该阈值只用于统计与展示，不构成判定门槛（曾与 vocab-checker 的 max_proper=5 漂移，
        # 5 属早期遗留、与 SKILL 冲突，已随本次统一移除）。
        "max_proper": 999,
        "max_sentence_len": 26,
        # 注：早期 vocab-checker 里还有一个 max_compound_ratio=0.40，全库无任何调用点，已删除。
    },
}
