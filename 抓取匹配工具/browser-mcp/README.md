# browser-mcp — 通用浏览器抓取工具

通过**真实 Chrome + CDP**（Chrome DevTools Protocol）绕过 Aliyun WAF 等 JS 质询，
抓取任意网站渲染完成后的 HTML。**兼容任何网页**——只负责"打开网页、拿渲染结果"，
不做特定网站的解析。

## 为什么用真实 Chrome + CDP

- 纯 `requests`：被 WAF 的 JS 质询拦截（返回"已阻断"页）
- 无头 Chrome `--headless --dump-dom`：也被 WAF 识别拦截
- **真实 Chrome + remote-debugging + websocket**：正常执行 JS，绕过质询，拿完整渲染结果

## 工具

| 工具 | 作用 |
|------|------|
| `fetch_page` | 抓取单页，返回 HTML 或保存到文件 |
| `batch_fetch` | 批量抓取多个页面，同一 Chrome 实例复用 |
| `open_in_browser` | 在真实 Chrome 打开页面（供手动操作，如加试题篮） |
| `extract_items` | 从已抓取 HTML 中按 CSS 选择器抽取文本/属性（本地解析） |

## 依赖

- Python 3.10+
- 已安装 Google Chrome

```bash
pip install -r requirements.txt
```

## 配置到 .mcp.json

本目录下 `mcp_server.py` 是 MCP server 入口。把 `<本目录>` 替换为
`browser-mcp` 所在的实际路径（**路径中含空格或中文必须用双引号包住**）。

### 方式 A：直接指定 Python

Windows：

```json
{
  "mcpServers": {
    "browser-mcp": {
      "command": "C:\\Users\\<你的用户名>\\AppData\\Local\\Programs\\Python\\Python3xx\\python.exe",
      "args": ["<本目录>\\browser-mcp\\mcp_server.py"],
      "description": "通用浏览器抓取 — 真实Chrome+CDP绕过WAF，兼容任何网页"
    }
  }
}
```

macOS：

```json
{
  "mcpServers": {
    "browser-mcp": {
      "command": "/usr/bin/python3",
      "args": ["<本目录>/browser-mcp/mcp_server.py"],
      "description": "通用浏览器抓取 — 真实Chrome+CDP绕过WAF，兼容任何网页"
    }
  }
}
```

### 方式 B：用当前默认 python（避免猜绝对 python 路径）

```bash
python -m pip install -r <本目录>/browser-mcp/requirements.txt
python <本目录>/browser-mcp/mcp_server.py
```

然后 .mcp.json 里 `command` 用你的 `python`，`args` 指向 `mcp_server.py`。

## Chrome 找不到？设置 CHROME_PATH

`cdp.py` 与两个命令行脚本 `_cdp_fetch.py` / `_cdp_batch.py` 都按以下顺序找 Chrome：

1. 环境变量 `CHROME_PATH`
2. 常见安装路径（Windows 的 Program Files / LOCALAPPDATA）

macOS 用户 Chrome 通常在 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`，
Windows 用户一般无需设置。若找不到，设置环境变量即可：

```bash
# macOS
export CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

## 命令行直用（不依赖 MCP）

```bash
# 抓取单页到文件
python cdp.py https://example.com/page out.html

# Python 调用
python -c "from cdp import fetch_html; print(len(fetch_html('https://example.com')))"

# 批量抓取：stdin 每行一个 "url<TAB>输出路径"，同一 Chrome 实例复用
printf "%s\t%s\n" "URL1" "out1.html" "URL2" "out2.html" | python _cdp_batch.py
```

## 工作原理

1. 启动真实 Chrome，带 `--remote-debugging-port=XXXX --remote-allow-origins=* --user-data-dir=...`
2. 通过 `http://127.0.0.1:PORT/json` 拿到页面 websocket 调试地址
3. 用 websocket 发 `Page.navigate` 打开目标 URL
4. 轮询 `document.readyState` 至 `complete`，再额外等几秒让 JS 渲染
5. `Runtime.evaluate` 取 `document.documentElement.outerHTML`

## 常见问题

- **找不到 Chrome**：设置环境变量 `CHROME_PATH`，或改 `cdp.py` 里 `CHROME_CANDIDATES`
- **websocket 403 / Rejected**：必须带 `--remote-allow-origins=*`
- **端口被占用**：换 `debug_port`（默认 9666），或先结束残留的 Chrome 调试进程；
  命令行脚本可用环境变量 `CDP_DEBUG_PORT` 覆盖
- **页面需要登录**：`fetch_page` 会拿到登录页 HTML；需手动操作时用 `open_in_browser`
- **MCP 报找不到模块**：确认已 `pip install -r requirements.txt`；若 python 版本不对，
  改用方式 B 或换 python 路径
