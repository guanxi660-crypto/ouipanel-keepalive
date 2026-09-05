#!/root/ouipanel/venv/bin/python
"""快速检查 OuiPanel 服务器当前状态 (输出按钮状态 + 提示文本)"""
import json, re
from playwright.sync_api import sync_playwright

TARGET = "https://dash.ouipanel.com/server/df36f0e3/console"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/chromium", headless=True,
                          args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US")
    with open("/root/ouipanel/cookies.txt", encoding="utf-8") as f:
        state = json.load(f)
    ctx.add_cookies(state.get("cookies", []))
    pg = ctx.new_page()

    pg.goto("https://dash.ouipanel.com/", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(2000)
    for origin_entries in state.get("origins", []):
        for kv in origin_entries.get("localStorage", []):
            try:
                pg.evaluate("(ls) => { localStorage.setItem(ls[0], ls[1]); }", [kv["name"], kv["value"]])
            except Exception:
                pass

    pg.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
    for _ in range(10):
        pg.wait_for_timeout(2000)
        if "/login" not in pg.url:
            break
    pg.wait_for_timeout(5000)

    print("URL:", pg.url)
    # 侧边栏电源按钮
    try:
        sb = pg.eval_on_selector_all("button.sidebar-power-btn",
            "els => els.map(e => ({cls: e.className.replace('sidebar-power-btn','').strip(), title: e.getAttribute('title')||'', dis: e.disabled}))")
        print("SIDEBAR POWER:", json.dumps(sb, ensure_ascii=False))
    except Exception as e:
        print("sidebar err:", e)
    # 工具栏电源按钮
    try:
        tb = pg.eval_on_selector_all("button.btn-sm",
            "els => els.map(e => ({txt: (e.textContent||'').trim().slice(0,20), dis: e.disabled, cls: (e.className||'').slice(0,50)}))")
        print("TOOLBAR:", json.dumps(tb, ensure_ascii=False))
    except Exception as e:
        print("toolbar err:", e)
    # 状态提示行
    body = pg.evaluate("() => document.body.innerText")
    for line in body.split("\n"):
        s = line.strip()
        if any(k in s.lower() for k in ["offline", "online", "starting", "démarrage", "running", "redémarrage", "restarting", "en ligne", "hors ligne"]):
            print("STATUS LINE:", s[:200])
    b.close()
