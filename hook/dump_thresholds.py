#!/usr/bin/env python3
"""打印阈值的规范镜像块（供文档粘贴使用）。

用法：python hook/dump_thresholds.py
把输出整段粘进任何"阈值速查表"；本脚本的输出由 hook/test_doc_consistency.py::test_threshold_dump_is_stable
锁定，所以它不会自己漂移 —— 改了 Part1-文章改写/thresholds.py，这里跟着变，把新块替换进文档即可。
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "阅读理解题目生成工具/Part1-文章改写"))
from thresholds import GRADE_LIMITS, LEVEL_THRESHOLDS  # noqa: E402


def canonical_block() -> str:
    def row(name: str, d: dict) -> str:
        return (f"{name}: word_count={d['word_count']} avg_sentence={d['average_sentence_length']} "
                f"p90={d['sentence_length_p90']} coverage>={d['vocabulary_coverage']} "
                f"oov_distinct<={d['oov_distinct_max']} proper_band={d['proper_name_band']}")
    g = GRADE_LIMITS[9]
    return "\n".join([
        row("standard", LEVEL_THRESHOLDS["standard"]),
        row("extended", LEVEL_THRESHOLDS["extended"]),
        f"grade9: coverage={g['coverage']} oov_ratio={g['oov_ratio']} "
        f"max_proper={g['max_proper']}（999=不设限制） max_sentence_len={g['max_sentence_len']}",
    ])


if __name__ == "__main__":
    print(canonical_block())
