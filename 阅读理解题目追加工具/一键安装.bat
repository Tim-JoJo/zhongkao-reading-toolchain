@echo off
chcp 65001 >nul
echo ==========================================
echo  阅读理解题目追加工具 - 一键安装
echo ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时务必勾选 "Add python.exe to PATH"
    pause
    exit /b 1
)

echo [1/2] 检测到 Python，开始安装依赖...
python -m pip install --user -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

echo.
echo [2/2] 安装完成！
echo.
echo 使用方式：
echo   交互式：  python 阅读理解题目追加工具.py --interactive
echo   按spec：  python 阅读理解题目追加工具.py 文章.docx spec文件.json
echo   生成示例：python 阅读理解题目追加工具.py --example
echo.
pause
