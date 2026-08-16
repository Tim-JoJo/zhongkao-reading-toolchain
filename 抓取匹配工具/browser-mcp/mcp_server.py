# -*- coding: utf-8 -*-
"""
browser-mcp — 通用浏览器抓取 MCP Server
========================================
通过真实 Chrome + CDP 绕过 WAF/JS 质询，提供通用网页抓取工具。
兼容任何网站：只负责"打开网页、返回渲染后 HTML / 文本 / 选择器抽取"，
不做特定网站的解析。

工具：
  1. fetch_page       — 抓取单页，返回 HTML 或保存到文件
  2. batch_fetch      — 批量抓取多个页面
  3. open_in_browser  — 在真实 Chrome 打开页面（供手动操作，如加试题篮）
"""
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "browser-mcp",
    instructions="通用浏览器抓取工具 — 通过真实 Chrome + CDP 绕过 WAF，抓取任意网站渲染后的 HTML。兼容任何网页。",
)

from cdp import (
    batch_fetch as _batch_fetch,
    fetch_to_file as _fetch_to_file,
    find_chrome,
)
import os
import subprocess


@mcp.tool()
def fetch_page(
    url: str,
    output_path: str | None = None,
    wait_seconds: float = 5.0,
) -> str:
    """抓取单页渲染后内容。

    用真实 Chrome 打开 url，等待页面渲染完成后返回 HTML。
    可自动绕过 Aliyun WAF 等 JS 质询（无头浏览器/纯 requests 会被拦截）。

    Args:
        url: 要抓取的完整 URL
        output_path: 可选。传则把 HTML 保存到该文件并返回路径；
                     不传则直接返回 HTML 内容
        wait_seconds: 页面加载后额外等待秒数（给 JS 渲染留时间），默认 5

    Returns:
        str: output_path 传了则返回保存路径；否则返回渲染后的 HTML
    """
    if output_path:
        path = _fetch_to_file(url, output_path, wait_extra=wait_seconds)
        return f"saved: {path} ({os.path.getsize(path)} bytes)"
    from cdp import fetch_html
    html = fetch_html(url, wait_extra=wait_seconds)
    return html


@mcp.tool()
def batch_fetch(
    urls: list[str],
    output_dir: str,
    name_pattern: str = "{i}.html",
    wait_seconds: float = 5.0,
) -> str:
    """批量抓取多个页面并保存到目录。

    用同一 Chrome 实例逐个打开，跳过已存在且大于 50KB 的文件。

    Args:
        urls: 要抓取的 URL 列表
        output_dir: 保存目录（不存在则自动创建）
        name_pattern: 文件名模板，支持 {i}（从 1 起序号）、{n}（url 的 hash 前 8 位）
        wait_seconds: 每页加载后额外等待秒数，默认 5

    Returns:
        str: 每个 url 对应的保存路径（换行分隔）
    """
    os.makedirs(output_dir, exist_ok=True)
    tasks = []
    for i, url in enumerate(urls, start=1):
        if "{n}" in name_pattern:
            name = name_pattern.replace("{n}", url.split("/")[-1][:8])
        else:
            name = name_pattern.replace("{i}", str(i))
        tasks.append((url, str(Path(output_dir) / name)))
    results = _batch_fetch(tasks, wait_extra=wait_seconds)
    return "\n".join(f"{url}\t{path}" for url, path in results.items())


@mcp.tool()
def open_in_browser(url: str) -> str:
    """在真实 Chrome 中打开页面（用户可手动操作）。

    用于需要登录或人工确认的场景（如加入试题篮、下载文件）。

    Args:
        url: 要打开的完整 URL

    Returns:
        str: 确认信息
    """
    chrome = find_chrome()
    subprocess.Popen([chrome, url])
    return f"已在 Chrome 打开: {url}"


@mcp.tool()
def extract_items(
    html: str,
    selector: str,
    attribute: str | None = None,
    limit: int = 50,
) -> list[str]:
    """从 HTML 中按 CSS 选择器抽取文本或属性（本地解析，无浏览器）。

    用于从已抓取的 HTML 中提取列表项、题目等结构化内容。

    Args:
        html: 已抓取的 HTML 内容
        selector: CSS 选择器，如 ".art-overview"、"[data-type=\"addToExam\"]"
        attribute: 可选。提取元素的该属性（如 href）而非 innerText
        limit: 最多返回条数，默认 50

    Returns:
        list[str]: 提取到的内容列表
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    els = soup.select(selector)[:limit]
    if attribute:
        return [e.get(attribute, "") for e in els]
    return [e.get_text(separator=" ", strip=True) for e in els]


if __name__ == "__main__":
    mcp.run()
