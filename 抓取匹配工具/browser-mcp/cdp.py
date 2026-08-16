# -*- coding: utf-8 -*-
"""
CDP (Chrome DevTools Protocol) 抓取核心 — 通用、不绑定任何特定网站。

通过启动真实 Chrome + remote-debugging 端口 + websocket 连接，
绕过 Aliyun WAF 等 JS 质询（无头浏览器/纯 requests 都会被拦截），
拿到页面渲染完成后的 HTML。

只负责"打开网页、返回渲染后的 HTML"，具体解析交给调用方。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

import websocket

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def find_chrome() -> str:
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("未找到 Chrome，请手动设置 CHROME_PATH")


class Browser:
    """管理一个真实 Chrome 实例（单页会话）。"""

    def __init__(self, debug_port: int = 9666, user_dir: str | None = None,
                 chrome_path: str | None = None):
        self.debug_port = debug_port
        self.user_dir = user_dir or os.path.join(
            os.environ.get("TEMP", "/tmp"), f"zk_cdp_{debug_port}")
        self.chrome_path = chrome_path or os.environ.get("CHROME_PATH") or find_chrome()
        self.proc = None
        self.ws = None

    def start(self):
        self.proc = subprocess.Popen([
            self.chrome_path,
            f"--remote-debugging-port={self.debug_port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.user_dir}",
            "--window-size=1280,900",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        page = self._wait_for_page()
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60)
        self.send("Page.enable")
        self.send("Runtime.enable")
        self.send("Network.enable")

    def _wait_for_page(self, timeout: float = 30.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.debug_port}/json", timeout=2) as r:
                    targets = json.loads(r.read().decode())
                for t in targets:
                    if t.get("type") == "page":
                        return t
            except Exception:
                pass
            time.sleep(0.4)
        raise RuntimeError("Chrome 调试端口未就绪")

    def send(self, method: str, params: dict | None = None, msg_id: int = 1) -> dict:
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == msg_id:
                return resp.get("result", {})

    def eval_js(self, expr: str) -> str:
        r = self.send("Runtime.evaluate", {
            "expression": expr, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            return "EXC:" + json.dumps(r["exceptionDetails"], ensure_ascii=False)[:300]
        return r.get("result", {}).get("value")

    def wait_ready(self, timeout: int = 60, wait_extra: float = 5.0):
        """等待 document.readyState == 'complete'，再额外等 JS 渲染完成。"""
        for _ in range(timeout):
            try:
                if self.eval_js("document.readyState") == "complete":
                    break
            except Exception:
                pass
            time.sleep(1)
        time.sleep(wait_extra)

    def navigate(self, url: str, wait_ready: bool = True, wait_extra: float = 5.0):
        self.send("Page.navigate", {"url": url})
        if wait_ready:
            self.wait_ready(wait_extra=wait_extra)

    def get_html(self) -> str:
        return self.eval_js("document.documentElement.outerHTML") or ""

    def get_text(self) -> str:
        return self.eval_js("document.body.innerText") or ""

    def get_location(self) -> str:
        return self.eval_js("location.href") or ""

    def get_title(self) -> str:
        return self.eval_js("document.title") or ""

    def extract(self, selector: str, attribute: str | None = None) -> list[str]:
        """按 CSS 选择器提取元素文本或属性。"""
        if attribute:
            js = (f"Array.from(document.querySelectorAll({json.dumps(selector)}))"
                  f".map(e => e.getAttribute({json.dumps(attribute)}))")
        else:
            js = (f"Array.from(document.querySelectorAll({json.dumps(selector)}))"
                  f".map(e => e.innerText)")
        val = self.eval_js(js)
        return val if isinstance(val, list) else []

    def close(self):
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        if self.proc:
            self.proc.terminate()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()


def fetch_html(url: str, debug_port: int = 9666, wait_extra: float = 5.0,
               chrome_path: str | None = None) -> str:
    """抓取单页渲染后 HTML。"""
    with Browser(debug_port=debug_port, chrome_path=chrome_path) as b:
        b.navigate(url, wait_extra=wait_extra)
        return b.get_html()


def fetch_to_file(url: str, out_path: str, debug_port: int = 9666,
                  wait_extra: float = 5.0, chrome_path: str | None = None) -> str:
    """抓取单页并保存到文件，返回保存路径。"""
    html = fetch_html(url, debug_port=debug_port, wait_extra=wait_extra,
                      chrome_path=chrome_path)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def batch_fetch(tasks: list[tuple[str, str]], debug_port: int = 9666,
                skip_existing: bool = True, wait_extra: float = 5.0,
                chrome_path: str | None = None) -> dict[str, str]:
    """批量抓取。tasks = [(url, out_path), ...]，返回 {url: out_path}。"""
    results: dict[str, str] = {}
    with Browser(debug_port=debug_port, chrome_path=chrome_path) as b:
        for url, out_path in tasks:
            if skip_existing and os.path.exists(out_path) and os.path.getsize(out_path) > 50000:
                results[url] = out_path
                continue
            b.navigate(url, wait_extra=wait_extra)
            html = b.get_html()
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)
            results[url] = out_path
    return results


if __name__ == "__main__":
    # 简单自测：python cdp.py <url> [out.html]
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    if out:
        path = fetch_to_file(url, out)
        print("saved:", path, os.path.getsize(path), "bytes")
    else:
        html = fetch_html(url)
        print("html len:", len(html))
