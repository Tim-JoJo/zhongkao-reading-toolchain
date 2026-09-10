"""文档一致性 hook —— 抓"改了一处、忘了另一处"的陈旧口径与悬空引用。

对应踩过的坑：
  1. 词表口径在 5 处并存（1601 / 2,795 / 3,585），互相矛盾
  2. 荧光图例写"三种高亮色"但表里只有 2 行，而导出器实际支持 3 色
  3. SKILL 引用的 references 路径不存在 / 跨 skill 相对路径改名未同步
  4. "必答 N 问" 标题下的条目数与 N 不符
  5. 反例黑名单编号范围与正文引用范围不符
  6. MCP 工具表与文档声明不符（弃用工具又冒出来）
  7. 阈值/导出前缀在多个文件里各抄一份 → 漂移
"""
from __future__ import annotations

import re
import pytest
from conftest import (AW, DESIGN_LOGIC, GEN, MCP, QG, RC, REPO, REW, VOCAB_MD,
                      KNOWN_DIVERGENCES)


def md_files():
    # 排除 .git 与 hook/ 自身：hook 的 README 会按设计记录历史口径（1601 / 2,795）
    return [p for p in REPO.rglob("*.md") if ".git" not in p.parts and "hook" not in p.parts]


# ── 1. 词表口径 ──
def test_vocab_count_single_source():
    assert "3585" in VOCAB_MD.read_text(encoding="utf-8"), "词表 md 头部应有权威口径计数"
    bad = []
    for p in md_files():
        if p.name.startswith("二级、三级词汇表"):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "1601" in line:
                bad.append(f"{p.relative_to(REPO)}:{i} 出现无出处的 1601 条")
            if "2,795" in line and not any(k in line for k in ("含", "补充", "口径", "3,585")):
                bad.append(f"{p.relative_to(REPO)}:{i} 裸用 2,795（须绑定 3,585 口径说明）")
    assert not bad, "词表口径不一致：\n" + "\n".join(bad)


# ── 2. 荧光标注色数 ──
def test_highlight_colors_match_docs():
    src = (MCP / "src/exporter.py").read_text(encoding="utf-8")
    block = re.search(r"HIGHLIGHT_COLORS\s*=\s*\{(.*?)\}", src, re.S).group(1)
    exporter_colors = set(re.findall(r'"(\w+)"\s*:', block))
    assert exporter_colors == {"yellow", "turquoise", "pink"}, exporter_colors

    claude = (GEN / "CLAUDE.md").read_text(encoding="utf-8")
    assert "三种高亮色" not in claude, "CLAUDE.md 仍写「三种高亮色」"
    m = re.search(r"荧光标注图例（[^）]*?([两三二])种高亮色", claude)
    assert m, "CLAUDE.md 应有「荧光标注图例（N 种高亮色…）」"
    declared = {"两": 2, "二": 2, "三": 3}[m.group(1)]
    rows = re.findall(r"^\|[^|]*\|[^|]*WD_COLOR_INDEX\.(\w+)", claude, re.M)
    assert len(rows) == declared, f"CLAUDE.md 声明 {declared} 色但图例表有 {len(rows)} 行：{rows}"

    aw = AW.read_text(encoding="utf-8")
    assert "三种高亮色" not in aw
    assert "本流程只用**黄、粉两色**" in aw, "article-writer SKILL 应显式限定两色并说明第三色启用条件"


# ── 3. 引用路径可达 ──
REF_RE = re.compile(r"`([^`\s]+\.md)`")


@pytest.mark.parametrize("skill", [AW, QG, RC, REW])
def test_referenced_paths_exist(skill):
    missing = []
    for ref in REF_RE.findall(skill.read_text(encoding="utf-8")):
        if not (ref.startswith("references/") or ref.startswith("../")):
            continue   # 只查显式相对路径，散文里提到的 "dir/file.md" 不当作引用
        p = (skill.parent / ref.replace("\\", "/")).resolve()
        if not p.exists():
            missing.append(ref)
    assert not missing, f"{skill.name} 引用了不存在的文件：{missing}"


def test_cross_skill_contract_paths():
    for name in ("module-library.md", "mental-models-heuristics.md"):
        p = REW.parent / "references" / name
        assert p.exists(), f"article-writer 硬依赖的 {name} 不存在：{p}"
    assert "reading-explorer-writing" in AW.read_text(encoding="utf-8")


# ── 4. 「必答 N 问」与实际条目数一致 ──
@pytest.mark.parametrize("skill", [RC, REW])
def test_numbered_checkpoint_count(skill):
    lines = skill.read_text(encoding="utf-8").splitlines()
    bad = []
    for i, line in enumerate(lines):
        m = re.search(r"必答 *(\d+) *问", line)
        if not m:
            continue
        declared = int(m.group(1))
        counted = 0
        for nxt in lines[i + 1:]:
            if re.match(r"^\s*\d+[.、]\s", nxt):
                counted += 1
            elif counted and nxt.strip() and not re.match(r"^\s*\d+[.、]\s", nxt):
                break
        if counted != declared:
            bad.append(f"{skill.name}:{i+1} 写「必答 {declared} 问」但实列 {counted} 条")
    assert not bad, "\n".join(bad)


# ── 5. 反例黑名单编号与引用范围一致 ──
def test_rc_blacklist_numbering():
    rc = RC.read_text(encoding="utf-8")
    ids = [int(n) for n in re.findall(r"^\|\s*W(\d+)\s*\|", rc, re.M)]
    assert ids, "未解析到 rc 反例黑名单"
    assert max(ids) == len(ids), f"W 编号不连续：{sorted(ids)}"
    for rng in re.findall(r"W1-W(\d+)", rc):
        assert int(rng) == max(ids), f"正文引用 W1-W{rng}，但黑名单实到 W{max(ids)}"

    dl = [int(n) for n in re.findall(r"^\|\s*W(\d+)\s*\|", DESIGN_LOGIC.read_text(encoding="utf-8"), re.M)]
    if max(dl) != max(ids):
        assert "rc_blacklist_w11" in KNOWN_DIVERGENCES, (
            f"SKILL 黑名单到 W{max(ids)}、design-logic.md 到 W{max(dl)}，"
            "该差异未在 conftest.KNOWN_DIVERGENCES 登记")


# ── 6. MCP 工具表 ──
def test_mcp_tool_set():
    src = (MCP / "mcp_server.py").read_text(encoding="utf-8")
    tools = re.findall(r"@mcp\.tool\(\)\s*\ndef (\w+)", src)
    assert len(tools) == len(set(tools)), "工具名重复注册"
    assert "export_article_docx" not in tools, "弃用工具 export_article_docx 又出现在 MCP 工具表里"
    assert "run_export_article_docx" not in src, "不应再 import 弃用的导出函数"
    listed = re.findall(r"^  (\d+)\. (\w+)", src, re.M)
    assert len(listed) == len(tools), f"docstring 列了 {len(listed)} 个工具，实际注册 {len(tools)} 个"


# ── 7. 阈值与导出前缀：单一来源 ──
def test_threshold_single_source():
    src = (MCP / "mcp_server.py").read_text(encoding="utf-8")
    assert "LEVEL_THRESHOLDS = {" not in src, "mcp_server.py 又抄了一份阈值"
    assert "from src.thresholds import" in src
    tt = (MCP / "tests/test_tools.py").read_text(encoding="utf-8")
    assert "from src.thresholds import" in tt, "tests 又抄了一份阈值"
    assert "220, 240" not in tt

    vs = (GEN / "Part1-文章改写/vocab-checker/mcp_server.py").read_text(encoding="utf-8")
    mp = re.search(r'"max_proper": *(\d+)', vs)
    assert mp, "vocab-checker 应有 GRADE_LIMITS"
    if int(mp.group(1)) != 999:
        assert "grade_max_proper" in KNOWN_DIVERGENCES, (
            "vocab-checker 的 max_proper 与 zhongkao-mcp 不一致且未登记理由")


def test_export_prefix_single_source():
    lit = []
    for p in REPO.rglob("*.py"):
        if ".git" in p.parts or p.name == "exporter.py" or "hook" in p.parts:
            continue
        if '"文档已保存至' in p.read_text(encoding="utf-8") or "文档已保存" in p.read_text(encoding="utf-8"):
            lit.append(str(p.relative_to(REPO)))
    assert not lit, f"导出成功前缀被硬编码到了 {lit}（判定请走 exporter.is_export_ok）"
    ms = (MCP / "mcp_server.py").read_text(encoding="utf-8")
    assert "is_export_ok(" in ms and 'startswith("文档已保存")' not in ms
