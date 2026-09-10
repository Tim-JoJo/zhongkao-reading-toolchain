"""档位与年级阈值 —— 唯一来源（single source of truth）。

改阈值只改这里，不要在各个 mcp_server / 测试里再抄一份。
历史教训：mcp_server.py、vocab-checker/mcp_server.py、tests/test_tools.py 各存一份，
结果互相漂移（tests 里还留着 word_count [220,240] 的旧档、oov_distinct ≤10/15）。
hook/test_doc_consistency.py::test_threshold_single_source 会拦新增的副本。
"""

# 档位阈值（与 SKILL references/approved-standards.md 一致）
# word_count 上限 350 为硬性门槛：超出即 all_pass=False，不得标为可交付。
LEVEL_THRESHOLDS = {
    "standard": {
        "word_count": [0, 350],
        "average_sentence_length": [13, 15],   # 双侧带区，高/低都 review_required
        "sentence_length_p90": [0, 24],
        "vocabulary_coverage": 0.90,
        "oov_distinct_max": 999,
        "proper_name_band": [0, 999],          # 专名不设数量限制（见 article-writer SKILL 第 4 步）
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
        "max_proper": 999,          # 同上：专名不设上限；vocab-checker 独立校验另有一套（见 hook 的已登记差异）
        "max_sentence_len": 26,
    },
}
