# 抓取匹配工具（可分发版）

通过**真实 Chrome + CDP** 在题库网站（组卷网/学科网等）上**找与给定阅读文章主题相似的文章**。
本包为可分发版本：不含本机写死的路径，对方拿到后按下方步骤配置即可在自己机器上用 agent 跑通。

## 包含内容

```
抓取匹配工具-可分发版/
├── README.md                 ← 本文件：总览 + 快速开始
├── .mcp.json                 ← MCP 配置模板（复制到项目根目录后改路径）
├── browser-mcp/              ← 通用浏览器抓取 MCP server（真实Chrome + CDP 绕过 WAF）
│   ├── mcp_server.py         ← MCP 入口
│   ├── cdp.py                ← CDP 抓取核心
│   ├── _cdp_fetch.py         ← 命令行单页抓取（无 MCP 时退化用）
│   ├── _cdp_batch.py         ← 命令行批量抓取（无 MCP 时退化用）
│   ├── requirements.txt
│   └── README.md             ← browser-mcp 详细文档
└── theme-matcher/
    └── SKILL.md              ← 主题匹配 Skill（找相似文章的工作流）
```

## 对方需要什么

- **Google Chrome**（真实安装版，用于 CDP 抓取；本工具不依赖无头模式）
- **Python 3.10+**（跑 MCP server 与抓取脚本）
- 一个**支持 MCP 的 agent**（Claude Code / Claude Desktop 等）
- 目标题库网站（默认组卷网 zujuan.xkw.com，需登录操作的部分由人手动完成）

## 快速开始

### 1. 安装依赖

```bash
cd <本目录>
pip install -r browser-mcp/requirements.txt
```

### 2. 注册 browser-mcp

把 `browser-mcp` 注册为 MCP server：

```bash
cp .mcp.json <你的项目根目录>/.mcp.json
```

然后打开 `.mcp.json`，把两处 `<本目录>` 替换为 `browser-mcp` 所在的实际绝对路径，
并按你机器的 python 改 `command`。Windows 路径用双反斜杠 `\\`，示例见
[browser-mcp/README.md](browser-mcp/README.md) 的「配置到 .mcp.json」。

配置好后，agent 里应能调用 `browser-mcp` 的工具（`fetch_page` / `batch_fetch` / `open_in_browser` / `extract_items`）。

### 3. 安装 theme-matcher Skill

把 `theme-matcher/` 目录放到 agent 的 skills 目录（Claude Code 为 `.claude/skills/`），
或用 `/theme-matcher` 触发。Skill 会驱动完整工作流：解析基准文章 → 定主题维度 →
按知识点树找目录 → 抓列表页 → 提取概要 → 判断相似度 → 写入匹配 JSON → 打开页面手动加试题篮。

### 4. 验证

```bash
# 冒烟测试：不依赖 MCP，直接抓一个页面
python browser-mcp/cdp.py https://example.com
```

若输出 `html len: ...`，说明 Chrome 与 CDP 链路正常。

## Chrome 找不到？

设置环境变量 `CHROME_PATH` 指向 Chrome 可执行文件：

```bash
# macOS
export CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

详见 [browser-mcp/README.md](browser-mcp/README.md)。

## 常见问题

- **MCP 起不来**：`pip install` 没装好，或 python 路径不对 → 见 [browser-mcp/README.md](browser-mcp/README.md)
- **抓取被 WAF 拦截**：确认用的是真实 Chrome（非无头），且带 `--remote-allow-origins=*`（代码已内置）
- **页面需要登录**：`fetch_page` 拿到的是登录页；需手动操作时用 `open_in_browser` 打开后人工加试题篮
