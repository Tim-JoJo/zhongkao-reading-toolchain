#!/usr/bin/env bash
# 中考英语阅读 AI 命题工作链 —— 一键安装（macOS / Linux）
# 做四件事：建 .venv → 装两个工具的依赖 → 下载 spaCy 词形还原模型 → 生成免手改的 .mcp.json
set -euo pipefail
cd "$(dirname "$0")"

PY=python3
command -v "$PY" >/dev/null 2>&1 || { echo "❌ 未找到 python3，请先安装 Python 3.10+"; exit 1; }

echo "[1/4] 创建虚拟环境 .venv（已存在则复用）"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
VENV_PY=.venv/bin/python

echo "[2/4] 安装依赖（生成工具 + 追加工具）"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet \
  -r 阅读理解题目生成工具/requirements.txt \
  -r 阅读理解题目追加工具/requirements.txt

echo "[3/4] 下载 spaCy 模型 en_core_web_sm（生词核查的词形还原）"
if ! "$VENV_PY" -m spacy download en_core_web_sm; then
  echo "⚠️  模型下载失败（网络原因？）：vocab-checker 的生词核查暂不可用，联网后重跑本脚本补装。"
fi

echo "[4/4] 生成 .mcp.json（绝对路径已填好，无需手改）"
"$VENV_PY" scripts/gen_mcp_json.py --python "$PWD/.venv/bin/python" --output .mcp.json

echo
echo "✅ 安装完成。接下来二选一："
echo "   a) 直接在本仓库根目录开 agent 会话（Claude Code 会自动读取根目录 .mcp.json）"
echo "   b) 把刚生成的 .mcp.json 整个复制到你的 agent 项目根目录"
echo "   然后重启 agent 会话，确认出现 mcp__zhongkao-mcp__* 与 mcp__vocab-checker__* 工具。"
