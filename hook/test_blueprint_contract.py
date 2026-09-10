"""蓝图契约 hook —— 把"文档承诺的题型分布"钉成可回归的数字。

对应踩过的坑：SKILL/文档写着的加权比例（Q1 写作手法 30%、Q2 词义 70%、Q4 推断 20%、
Q3 抽中 I-08 转 M-03、带标题时 Q5 不出 best title、双 I-08 角点约 0.05%）
一旦被改动而文档没同步，出题分布会静默跑偏且无人发现。
"""
from __future__ import annotations

import pytest

pytest.importorskip("spacy", reason="蓝图模块本身不依赖 spacy；装了 spacy 的环境才跑全量种子扫描")
from src.blueprint import BLUEPRINT_POOL, run_draw_blueprint

N = 3000
ALL_CODES = {c for pool in BLUEPRINT_POOL.values() for c in pool} | {"M-03"}


def _scan(n, **kw):
    codes, labels = [], []
    for s in range(n):
        b = run_draw_blueprint(seed=s, **kw)
        codes.append(b["codes"])
        labels.append(b["type_labels"])
    return codes, labels


def test_codes_come_from_pool():
    codes, _ = _scan(300)
    assert {c for row in codes for c in row} <= ALL_CODES


def test_weighted_distribution():
    codes, labels = _scan(N)
    wt = sum(1 for r in labels if r[0] == "writing_technique") / N
    voc = sum(1 for r in codes if r[1].startswith("V")) / N
    inf = sum(1 for r in labels if r[3] == "inference") / N
    assert abs(wt - 0.30) < 0.04, f"Q1 写作手法 {wt:.3f}，文档称 30%"
    assert abs(voc - 0.70) < 0.04, f"Q2 词义 {voc:.3f}，文档称 70%"
    assert abs(inf - 0.20) < 0.04, f"Q4 推断路径 {inf:.3f}，文档称 20%"


def test_q3_i08_converts_to_m03():
    codes, labels = _scan(N)
    conv = sum(1 for r in codes if r[2] == "M-03")
    assert abs(conv / N - 0.05) < 0.02, f"Q3 I-08→M-03 {conv/N:.3f}，文档称约 5%"
    for r, l in zip(codes, labels):
        if r[2] == "M-03":
            assert l[2] == "main_idea", "转成 M-03 时 type 必须同时是 main_idea（否则导出标签错）"


def test_titled_article_never_gets_best_title():
    for s in range(1500):
        b = run_draw_blueprint(seed=s, article_has_title=True)
        assert b["codes"][4] != "M-01", "带标题文章的 Q5 不得抽到最佳标题"
        assert b["codes"][4] != "I-08", "Q5 是全文位，不得用段落主旨 I-08"
        assert b["type_labels"][4] == "inference"


def test_q4_i08_is_not_auto_converted():
    """文档明确：自动转换只在 Q3 生效，Q4 抽中 I-08 需人工转（SKILL 失败模式 2b）。"""
    codes, labels = _scan(4000)
    hits = [(r, l) for r, l in zip(codes, labels) if r[3] == "I-08"]
    assert hits, "4000 次抽样应能抽到 Q4=I-08（约 1%）"
    for c, l in hits:
        assert l[3] == "inference" and c[3] == "I-08", "源码不应替 Q4 自动转换"
    assert len(hits) / 4000 < 0.02


def test_double_i08_corner_is_rare():
    """Q3 与 Q4 同时落在段落主旨 → 推理题消失、type_coverage 会报错，文档称约 0.05%。"""
    both = 0
    for s in range(6000):
        b = run_draw_blueprint(seed=s)
        if b["codes"][2] == "M-03" and b["codes"][3] == "I-08":
            both += 1
    assert both / 6000 < 0.005, f"双 I-08 角点 {both/6000:.4f} 明显高于文档宣称"
