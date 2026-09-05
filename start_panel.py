#!/root/ouipanel/venv/bin/python
"""
OuiPanel 启动服务器脚本 (离线时用 Start 拉起)
逻辑与 restart_panel.py 相同, 只是点击 Start 而不是 Redémarrer
"""
import json, re, os, sys, time, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
TARGET = "https://dash.ouipanel.com/server/df36f0e3/console"
STATE_FILE = os.path.join(BASE, "cookies.txt")
LOG_FILE = os.path.join(BASE, "restart.log")
ACCOUNT_FILE = os.path.join(BASE, "account.txt")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def log(msg):
    line = "[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_account():
    acct = {"user": None, "pw": None}
    for line in open(ACCOUNT_FILE, encoding="utf-8"):
        line = line.strip()
        m = re.match(r"main[:\uff1a](\S+)", line)
        if m:
            acct["user"] = m.group(1)
        m = re.match(r"pass[:\uff1a](\S+)", line)
        if m:
            acct["pw"] = m.group(1)
    if not acct["user"] or not acct["pw"]:
        raise RuntimeError("account.txt 缺少帐号或密码")
    return acct


def load_state(ctx):
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        ctx.add_cookies(state.get("cookies", []))
        return state
    except Exception:
        return None


def restore_localstorage(pg, state):
    if not state:
        return
    for origin_entries in state.get("origins", []):
        for kv in origin_entries.get("localStorage", []):
            try:
                pg.evaluate("(ls) => { localStorage.setItem(ls[0], ls[1]); }", [kv["name"], kv["value"]])
            except Exception:
                pass


def open_console(pg):
    pg.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
    for _ in range(12):
        pg.wait_for_timeout(2000)
        if "/login" not in pg.url:
            pg.wait_for_timeout(5000)
            return True
    return False


def do_full_login(pg, ctx):
    acct = read_account()
    pg.goto("https://dash.ouipanel.com/login", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(3000)
    resp = pg.evaluate("() => fetch('https://ouipanel.com/auth/oauth/whmcs').then(r => r.json())")
    pg.goto(resp["redirect"], wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(3000)
    pg.fill("#inputEmail", acct["user"])
    pg.fill("#inputPassword", acct["pw"])
    pg.click("button[type=submit], input[type=submit]")
    pg.wait_for_timeout(7000)
    el = pg.query_selector("button:has-text('Connexion'), a:has-text('Connexion')")
    if not el:
        raise RuntimeError("登录后未找到 Connexion 按钮")
    el.click()
    for _ in range(20):
        pg.wait_for_timeout(2000)
        if "/login" not in pg.url and "dash.ouipanel.com" in pg.url:
            break
    ctx.storage_state(path=STATE_FILE)
    log("完整登录完成，登录态已保存")


def find_start_btn(pg):
    sels = [
        "button.sidebar-power-btn.power-start",
        "button:has-text('Démarrer')",
        "button:has-text('Start')",
        "[role=button]:has-text('Démarrer')",
        "[role=button]:has-text('Start')",
    ]
    for s in sels:
        try:
            el = pg.query_selector(s)
            if el:
                vis = el.evaluate("e => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0")
                dis = el.evaluate("e => !!e.disabled")
                if vis and not dis:
                    return el, s
        except Exception:
            continue
    return None, None


def click_start(pg):
    power_calls = []

    def on_req(r):
        if r.method == "POST" and "power" in r.url:
            power_calls.append((r.url, r.post_data or ""))

    pg.on("request", on_req)
    el, sel = find_start_btn(pg)
    if not el:
        return False, "未找到可用的启动按钮"
    log("找到启动按钮 (selector=%s)，等待 2s 后点击" % sel)
    pg.wait_for_timeout(2000)
    el.click()
    log("已点击启动按钮，等待 20s 确认启动指令")
    for _ in range(20):
        pg.wait_for_timeout(1000)
        if power_calls:
            pg.wait_for_timeout(5000)
            return True, "已捕获 POST %s body=%s" % (power_calls[0][0], power_calls[0][1])
    return False, "点击后 20 秒内未捕获到 power 请求 (selector=%s)" % sel


def main():
    from playwright.sync_api import sync_playwright
    log("=== OuiPanel 启动服务器任务开始 ===")
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/chromium", headless=True,
                              args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US")
        pg = ctx.new_page()

        state = load_state(ctx)
        if state:
            pg.goto("https://dash.ouipanel.com/", wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(2000)
            restore_localstorage(pg, state)

        ok = open_console(pg)
        if not ok:
            log("保存的会话已失效，执行完整登录")
            do_full_login(pg, ctx)
            ok = open_console(pg)
            if not ok:
                raise RuntimeError("登录后仍无法打开 console 页面")

        for attempt in range(2):
            try:
                pg.wait_for_selector("button.sidebar-power-btn, button:has-text('Start'), button:has-text('Démarrer')",
                                     timeout=40000)
                break
            except Exception:
                if attempt == 0:
                    log("等待启动按钮超时，sleep 5s 后重载页面重试")
                    pg.wait_for_timeout(5000)
                    pg.reload(wait_until="domcontentloaded")
                    pg.wait_for_timeout(10000)
                else:
                    log("重载后仍找不到启动按钮")

        succ, detail = click_start(pg)
        if succ:
            log("启动指令已发送: " + detail)
            print("RESULT=SUCCESS")
            b.close()
            return 0
        log("启动失败: " + detail)
        print("RESULT=FAILED")
        b.close()
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log("异常: %s" % e)
        print("RESULT=ERROR")
        sys.exit(1)
