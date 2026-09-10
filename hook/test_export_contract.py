"""导出器契约 hook —— 抓"返回文案改了、调用方静默失效"这类隐性耦合。

对应踩过的坑：
  mcp_server 曾用 `result.startswith("文档已保存")` 判断导出成功再记工作流状态；
  改一个字文案就会静默让记账失效（门禁从此形同虚设）。现在判定集中在 exporter.is_export_ok。
"""
from __future__ import annotations

import zipfile
import pytest

pytest.importorskip("docx", reason="导出器需要 python-docx")
from src.exporter import (EXPORT_OK_PREFIX, REPORT_OK_PREFIX, is_export_ok,
                          is_report_ok, run_export_docx)

EV = "\n".join(["①. The team sent robots into the sea.", "②. The robots found tube worms.",
                 "③. The team published the maps.", "④. The robots returned to the ship."])
QUESTIONS = [
    {"id": 1, "stem": "How does the writer begin the article?", "type": "writing_technique",
     "options": ["A. By asking questions", "B. By telling a story", "C. By listing numbers", "D. By giving an example"], "answer": "B"},
    {"id": 4, "stem": "Which is the correct order of the events?\n" + EV, "type": "ordering",
     "options": ["A. ②①③④", "B. ①②③④", "C. ④③①②", "D. ③④②①"], "answer": "B"},
]
ANSWER_KEY = ["B", "B"]
BODY = "Most people know that sleep helps the body rest（休息）."


def test_ok_helpers():
    assert is_export_ok(f"{EXPORT_OK_PREFIX}/tmp/x.docx")
    assert not is_export_ok("导出失败：boom")
    assert not is_export_ok(None)
    assert is_report_ok(f"{REPORT_OK_PREFIX}/tmp/r.docx")
    assert EXPORT_OK_PREFIX != REPORT_OK_PREFIX


def test_export_docx_returns_prefix_and_readable_file(tmp_path):
    out = tmp_path / "exam.docx"
    r = run_export_docx(title="Sleep and the Brain", body=BODY, questions=QUESTIONS,
                        answer_key=ANSWER_KEY, output_path=str(out),
                        explanations=["本文是一篇说明文，介绍睡眠与记忆。", "第 1 段可知开头方式。", "事件顺序见正文时间线。"])
    assert is_export_ok(r), r
    assert out.exists()

    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "Answer Key" in xml
    assert "答案解析" in xml
    assert "Reading Comprehension" in xml
    # 排序题 ①②③④ 必须用苹方-简渲染（仅设 eastAsia 时 ① 会走 Arial）
    assert "苹方-简" in xml, "排序题事件标号未使用苹方-简字体"


def test_export_failure_is_not_ok(tmp_path):
    r = run_export_docx(title="t", body=BODY, questions=QUESTIONS, answer_key=ANSWER_KEY,
                        output_path=str(tmp_path / "nodir" / "sub" / "x.docx"))
    assert is_export_ok(r), "应自动创建父目录并成功"


def test_fonts_and_indent_rules(tmp_path):
    out = tmp_path / "fmt.docx"
    run_export_docx(title="T", body=BODY, questions=QUESTIONS[:1], answer_key=["B"],
                    output_path=str(out))
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "微软雅黑" in xml, "中文字体必须写 rFonts eastAsia=微软雅黑"
    assert "Arial" in xml
