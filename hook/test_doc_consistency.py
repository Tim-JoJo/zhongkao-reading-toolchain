"""文档一致性 hook —— 抓"改了一处、忘了另一处"的陈旧口径、悬空引用与重复定义。

对应踩过的坑：
  1. 词表口径在 5 处并存（1601 / 2,795 / 3,585 / 3,686），互相矛盾
  2. 荧光图例写"三种高亮色"但表里只有 2 行，而导出器实际支持 3 色
  3. SKILL 引用的 references 路径不存在 / 跨 skill 相对路径改名未同步
  4. "必答 N 问" 标题下的条目数与 N 不符（实列 5 条却写 3 问）
  5. 反例黑名单编号范围与正文引用范围、与 reference 文件三者不一致
  6. MCP 工具表与文档声明不符（弃用工具又冒出来）
  7. 阈值/导出前缀在多个文件里各抄一份 → 漂移
"""
from __future__ import annotations

import re

import pytest

from conftest import (AW, DESIGN_LOGIC, GEN, MCP, QG, RC, REPO, REW,
                      SHARED_THRESHOLDS, VOCAB_MD, VOCAB_SRV)

# 已废弃、无法复核的词表口径（词表说明区自己会提到它们以作禁止，其余文件一律不得出现）
FORBIDDEN_VOCAB_NUMBERS = ("1601", "2,795", "3,585", "3,581", "2,795+")
CURRENT_VOCAB_NUMBERS = ("3686", "3570")


def md_files():
    # 排除 .git 与 hook/ 自身（hook 的 README 按设计记录历史口径）
    return [p for p in REPO.rglob("*.md") if ".git" not in p.parts and "hook" not in p.parts]


# ── 1. 词表口径 ──
def test_vocab_count_single_source():
    body = VOCAB_MD.read_text(encoding="utf-8")
    for n in CURRENT_VOCAB_NUMBERS:
        assert n in body, f"词表说明区缺少实测口径 {n}"
    bad = []
    for p in md_files():
        if p.name.startswith("二级、三级词汇表"):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for n in FORBIDDEN_VOCAB_NUMBERS:
                if n in line:
                    bad.append(f"{p.relative_to(REPO)}:{i} 出现已废弃口径 {n}：{line.strip()[:60]}")
    assert not bad, "词表口径不一致：\n" + "\n".join(bad)


# ── 2. 荧光标注色数 ──
def test_highlight_colors_match_docs():
    src = (MCP / "src/exporter.py").read_text(encoding="utf-8")
    block = re.search(r"HIGHLIGHT_COLORS\s*=\s*\{(.*?)\}", src, re.S).group(1)
    exporter_colors = set(re.findall(r'"(\w+)"\s*:', block))
    assert exporter_colors == {"yellow", "turquoise", "pink"}, exporter_colors

    claude = (GEN / "CLAUDE.md").read_text(encoding="utf-8")
    assert "三种高亮色" not in claude, "CLAUDE.md 又写回「三种高亮色」"
    m = re.search(r"荧光标注图例（[^）]*?([两三二])种高亮色", claude)
    assert m, "CLAUDE.md 应有「荧光标注图例（N 种高亮色…）」"
    declared = {"两": 2, "二": 2, "三": 3}[m.group(1)]
    rows = re.findall(r"^\|[^|]*\|[^|]*WD_COLOR_INDEX\.(\w+)", claude, re.M)
    assert len(rows) == declared, f"CLAUDE.md 声明 {declared} 色但图例表有 {len(rows)} 行：{rows}"

    aw = AW.read_text(encoding="utf-8")
    assert "三种高亮色" not in aw
    assert "本流程只用**黄、粉两色**" in aw


# ── 3. 引用路径可达 ──
REF_RE = re.compile(r"`([^`\s]+\.md)`")


@pytest.mark.parametrize("skill", [AW, QG, RC, REW])
def test_referenced_paths_exist(skill):
    missing = []
    for ref in REF_RE.findall(skill.read_text(encoding="utf-8")):
        if not (ref.startswith("references/") or ref.startswith("../")):
            continue   # 只查显式相对路径；散文里提到的 "dir/file.md" 不算引用
        if not (skill.parent / ref.replace("\\", "/")).resolve().exists():
            missing.append(ref)
    assert not missing, f"{skill.name} 引用了不存在的文件：{missing}"


def test_cross_skill_contract_paths():
    for name in ("module-library.md", "mental-models-heuristics.md"):
        assert (REW.parent / "references" / name).exists(), "article-writer 硬依赖的 reference 缺失"
    assert "reading-explorer-writing" in AW.read_text(encoding="utf-8")


# ── 4. 「必答 N 问」与条目数一致 ──
@pytest.mark.parametrize("skill", [RC, REW])
def test_numbered_checkpoint_count(skill):
    lines = skill.read_text(encoding="utf-8").splitlines()
    bad = []
    for i, line in enumerate(lines):
        m = re.search(r"必答 *(\d+) *问", line)
        if not m:
            continue
        declared, counted = int(m.group(1)), 0
        for nxt in lines[i + 1:]:
            if re.match(r"^\s*\d+[.、]\s", nxt):
                counted += 1
            elif counted and nxt.strip():
                break
        if counted != declared:
            bad.append(f"{skill.name}:{i+1} 写「必答 {declared} 问」但实列 {counted} 条")
    assert not bad, "\n".join(bad)


# ── 5. 反例黑名单：SKILL / reference / 正文引用 三者编号必须一致 ──
def _w_ids(p):
    return [int(n) for n in re.findall(r"^\|\s*W(\d+)\s*\|", p.read_text(encoding="utf-8"), re.M)]


def test_rc_blacklist_numbering_is_uniform():
    rc, dl = RC.read_text(encoding="utf-8"), DESIGN_LOGIC.read_text(encoding="utf-8")
    ids, dl_ids = _w_ids(RC), _w_ids(DESIGN_LOGIC)
    assert ids and dl_ids, "未解析到 W 编号表"
    assert max(ids) == len(ids), f"SKILL 黑名单编号不连续：{sorted(ids)}"
    assert max(dl_ids) == len(dl_ids), f"design-logic 编号不连续：{sorted(dl_ids)}"
    assert max(ids) == max(dl_ids), (
        f"SKILL 黑名单到 W{max(ids)}，references/design-logic.md 到 W{max(dl_ids)} —— 必须一致")
    for rng in re.findall(r"W1-W(\d+)", rc):
        assert int(rng) == max(ids), f"正文引用 W1-W{rng}，黑名单实到 W{max(ids)}"
    m = re.search(r"## 四、反模式详解\((\d+) 条", dl)
    assert m and int(m.group(1)) == max(dl_ids), "design-logic 小节标题的条数与表体不符"
    m = re.search(r"\|\s*`references/design-logic\.md`.*?(\d+) 反模式详解", rc)
    assert m and int(m.group(1)) == max(ids), "SKILL Reference 索引里的条数与黑名单不符"


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
    assert SHARED_THRESHOLDS.exists(), "共用阈值应在 Part1-文章改写/thresholds.py（两个 server 的共同上级）"
    shared = SHARED_THRESHOLDS.read_text(encoding="utf-8")
    assert "LEVEL_THRESHOLDS = {" in shared and "GRADE_LIMITS = {" in shared

    for f in (MCP / "mcp_server.py", VOCAB_SRV, MCP / "tests/test_tools.py"):
        txt = f.read_text(encoding="utf-8")
        assert "LEVEL_THRESHOLDS = {" not in txt, f"{f.name} 又抄了一份 LEVEL_THRESHOLDS"
        assert "GRADE_LIMITS = {" not in txt, f"{f.name} 又抄了一份 GRADE_LIMITS"
        assert "from thresholds import" in txt, f"{f.name} 应 import 共用阈值"
    tt = (MCP / "tests/test_tools.py").read_text(encoding="utf-8")
    assert "220, 240" not in tt, "tests 里那份 [220,240] 旧档又回来了"

    # 专名：SKILL 第 4 步「不对专名设置数量限制」→ 阈值不得再出现 5 这类限制
    assert '"max_proper": 999' in shared
    assert '"max_proper": 5' not in VOCAB_SRV.read_text(encoding="utf-8"), \
        "vocab-checker 又自行限制了专名数量（与 SKILL 冲突）"


def test_mcp_pin_matches_code_api():
    """代码用的是 mcp v1 的 FastMCP ⇒ requirements 必须钉 <2。

    背景：mcp 2.x 把 FastMCP 改名为 MCPServer（from mcp.server.mcpserver import MCPServer），
    而 `mcp>=1.0` 这条宽松约束会让**全新安装**解析到 2.x，MCP server 直接 import 失败。
    实测：venv 装到 mcp 2.2.0 时 `from mcp.server.fastmcp import FastMCP` 抛 ModuleNotFoundError。
    若将来迁移到 2.x，请同时删除本 hook 与 requirements 里的 <2 约束。
    """
    users = [p for p in REPO.rglob("*.py")
             if "hook" not in p.parts and "mcp.server.fastmcp" in p.read_text(encoding="utf-8")]
    assert users, "预期仍有模块使用 mcp v1 的 FastMCP（已迁移到 2.x？请同步删掉本 hook）"
    bad = []
    for p in REPO.rglob("requirements.txt"):
        txt = p.read_text(encoding="utf-8")
        if any(l.strip().startswith("mcp") for l in txt.splitlines()) and "<2" not in txt:
            bad.append(str(p.relative_to(REPO)))
    assert not bad, f"这些 requirements 未把 mcp 钉在 <2，新装环境会拉到 2.x 导致 FastMCP 不存在：{bad}"


def test_export_prefix_single_source():
    lit = []
    for p in REPO.rglob("*.py"):
        if ".git" in p.parts or "hook" in p.parts or p.name == "exporter.py":
            continue
        if "文档已保存" in p.read_text(encoding="utf-8"):
            lit.append(str(p.relative_to(REPO)))
    assert not lit, f"导出成功前缀被硬编码到了 {lit}（判定请走 exporter.is_export_ok）"
    ms = (MCP / "mcp_server.py").read_text(encoding="utf-8")
    assert "is_export_ok(" in ms and 'startswith("文档已保存")' not in ms
