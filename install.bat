@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+ 并勾选 "Add python.exe to PATH"
    pause
    exit /b 1
)

echo [1/4] 创建虚拟环境 .venv（已存在则复用）
if not exist .venv\Scripts\python.exe python -m venv .venv
set VENV_PY=.venv\Scripts\python.exe

echo [2/4] 安装依赖（生成工具 + 追加工具）
"%VENV_PY%" -m pip install --quiet --upgrade pip
if errorlevel 1 goto :fail
"%VENV_PY%" -m pip install --quiet -r 阅读理解题目生成工具\requirements.txt -r 阅读理解题目追加工具\requirements.txt
if errorlevel 1 goto :fail

echo [3/4] 下载 spaCy 模型 en_core_web_sm（生词核查的词形还原）
"%VENV_PY%" -m spacy download en_core_web_sm
if errorlevel 1 echo [警告] 模型下载失败：生词核查暂不可用，联网后重跑本脚本补装

echo [4/4] 生成 .mcp.json（绝对路径已填好，无需手改）
"%VENV_PY%" scripts\gen_mcp_json.py --python .venv\Scripts\python.exe --output .mcp.json
if errorlevel 1 goto :fail

echo.
echo [OK] 安装完成。接下来二选一：
echo    a) 直接在本仓库根目录开 agent 会话（Claude Code 会自动读取根目录 .mcp.json）
echo    b) 把刚生成的 .mcp.json 整个复制到你的 agent 项目根目录
echo    然后重启 agent 会话，确认出现 mcp__zhongkao-mcp__* 与 mcp__vocab-checker__* 工具。
pause
exit /b 0

:fail
echo [错误] 安装失败，请检查上方输出后重试。
pause
exit /b 1
