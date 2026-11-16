#!/usr/bin/env python3
"""生成免手改的 .mcp.json：把模板里的 <工具根目录> 占位符替换为仓库真实绝对路径，
解释器也直接指向装好依赖的 venv，复制即可用。

install.sh / install.bat 会自动调用；也可单独运行：
  python scripts/gen_mcp_json.py --output .mcp.json   # 写文件
  python scripts/gen_mcp_json.py                      # 打印到 stdout
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL_ROOT = REPO / "阅读理解题目生成工具"   # 模板里 <工具根目录> 指工具包根，不是仓库根
TEMPLATE = TOOL_ROOT / ".mcp.json"
PLACEHOLDER = "<工具根目录>/"
# 两个自研 server：command 与 args 都要重写；其余（如可选的 mineru）按需保留
OWN_SERVERS = ("vocab-checker", "zhongkao-mcp")


def _mineru_available(python: str) -> bool:
    """mineru-open-mcp 是可选输入通道：装了才写进配置，免得会话里挂一个起不来的 server。"""
    try:
        subprocess.run([python, "-c", "import mineru_open_mcp"],
                       check=True, capture_output=True, timeout=30)
        return True
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="从模板生成路径已填好的 .mcp.json")
    ap.add_argument("--python", default=sys.executable,
                    help="运行 MCP server 的解释器（默认当前 Python；建议传 venv 内的绝对路径）")
    ap.add_argument("--output", default=None, help="写出路径（默认打印到 stdout）")
    args = ap.parse_args()

    cfg = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    servers = cfg["mcpServers"]
    # command 取绝对路径但【不】解析符号链接：venv 的 python 多是 symlink，
    # resolve 后会指到基础解释器，直接执行就落在基础环境、找不到 venv 里的依赖
    py_abs = str(pathlib.Path(os.path.abspath(args.python)))
    for name in OWN_SERVERS:
        rewritten = []
        for p in servers[name]["args"]:
            if not p.startswith(PLACEHOLDER):
                sys.exit(f"模板 {TEMPLATE} 的 {name} args 含未知路径：{p}（模板格式变了？请同步本脚本）")
            rewritten.append(str((TOOL_ROOT / p[len(PLACEHOLDER):]).resolve()))
        servers[name]["command"] = py_abs
        servers[name]["args"] = rewritten

    if "mineru-open-mcp" in servers and not _mineru_available(args.python):
        del servers["mineru-open-mcp"]

    text = json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        out = pathlib.Path(args.output)
        out.write_text(text, encoding="utf-8")
        print(f"已生成 {out}（绝对路径已填好，直接复制到 agent 项目根目录即可）", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
