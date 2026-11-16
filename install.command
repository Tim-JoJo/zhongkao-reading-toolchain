#!/bin/bash
# macOS 双击安装入口：Finder 里双击本文件，终端会自动打开并执行一键安装（内部调用 install.sh）。
# 首次使用若提示「无法打开，因为来自身份不明的开发者」：右键本文件 → 打开 → 再点「打开」。
cd "$(dirname "$0")" || exit 1
exec ./install.sh
