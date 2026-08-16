# -*- coding: utf-8 -*-
"""Batch fetch multiple pages via one Chrome instance, saving each to an output file."""
import json, subprocess, time, urllib.request, sys, os, tempfile
import websocket

CHROME = os.environ.get("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DEBUG_PORT = int(os.environ.get("CDP_DEBUG_PORT", "9666"))
USER_DIR = os.path.join(tempfile.gettempdir(), "zk_cdp_profile_batch")

# input: one line per "url<TAB>output_path"
tasks = []
for line in sys.stdin.read().splitlines():
    line = line.strip()
    if not line:
        continue
    parts = line.split("\t")
    if len(parts) == 2:
        tasks.append((parts[0], parts[1]))

if not tasks:
    print("NO TASKS")
    sys.exit(0)

proc = subprocess.Popen([
    CHROME,
    "--remote-debugging-port=%d" % DEBUG_PORT,
    "--remote-allow-origins=*",
    "--user-data-dir=" + USER_DIR,
    "--window-size=1280,900",
    "--no-first-run",
    "about:blank",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_json(url):
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("debug endpoint unavailable")

def ws_send(ws, method, params=None, msg_id=1):
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        resp = json.loads(ws.recv())
        if resp.get("id") == msg_id:
            return resp.get("result", {})

time.sleep(1)
targets = get_json("http://127.0.0.1:%d/json" % DEBUG_PORT)
page = None
for t in targets:
    if t.get("type") == "page":
        page = t
        break
assert page, "no page target"

ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
ws_send(ws, "Page.enable")
ws_send(ws, "Runtime.enable")
ws_send(ws, "Network.enable")

for idx, (url, out) in enumerate(tasks):
    if os.path.exists(out) and os.path.getsize(out) > 50000:
        print("SKIP existing", out)
        continue
    ws_send(ws, "Page.navigate", {"url": url})
    time.sleep(2)
    for _ in range(40):
        try:
            st = ws_send(ws, "Runtime.evaluate", {
                "expression": "document.readyState", "returnByValue": True})
            if st.get("result", {}).get("value") == "complete":
                break
        except Exception:
            pass
        time.sleep(1)
    time.sleep(6)
    html = ws_send(ws, "Runtime.evaluate", {
        "expression": "document.documentElement.outerHTML", "returnByValue": True})
    content = html.get("result", {}).get("value", "")
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    print("DONE %s len=%d" % (out, len(content)), flush=True)

try:
    ws.close()
except Exception:
    pass
proc.terminate()
print("ALL DONE")
