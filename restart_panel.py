#!/root/ouipanel/venv/bin/python
"""
OuiPanel 每半小时保活脚本 (智能: 在线则重启, 离线则拉起)
目标: https://dash.ouipanel.com/server/df36f0e3/console
- 优先使用保存的 cookies/localStorage (快路径)
- 会话失效时走完整 WHMCS OAuth 登录并重新保存状态 (慢路径)
- 判断服务器状态: Start 按钮 disabled=在线 / 可用=离线
- 在线 -> 点击侧边栏 Redémarrer (restart); 离线 -> 点击 Start (start)
- 通过捕获 POST /power {"signal":...} 请求验证指令已发出
- 关键步骤之间加入 sleep, 等待 React 渲染完成再操作
退出码: 0=成功 1=失败
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


def is_server_running(pg):
    """Start 按钮 disabled = 在线; 可用 = 离线. 返回 True/False/None(未知)"""
    for s in ["button.sidebar-power-btn.power-start",
              "button.btn-sm:has-text('Start')",
              "button:has-text('Start')"]:
        try:
            el = pg.query_selector(s)
            if el:
                dis = el.evaluate("e => !!e.disabled")
                vis = el.evaluate("e => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0")
                if vis:
                    return dis
        except Exception:
            continue
    return None


def find_power_btn(pg, kind):
    """kind: 'restart' 或 'start', 返回 (el, selector)"""
    if kind == "restart":
        sels = [
            "button.sidebar-power-btn.power-restart",
            "button:has-text('Redémarrer')",
            "button:has-text('Restart')",
            "[role=button]:has-text('Redémarrer')",
            "[role=button]:has-text('Restart')",
            "a:has-text('Redémarrer')",
            "a:has-text('Restart')",
        ]
    else:
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


def click_power(pg, kind):
    power_calls = []

    def on_req(r):
        if r.method == "POST" and "power" in r.url:
            power_calls.append((r.url, r.post_data or ""))

    pg.on("request", on_req)
    el, sel = find_power_btn(pg, kind)
    if not el:
        return False, "未找到可用的%s按钮" % ("重启" if kind == "restart" else "启动")
    log("找到%s按钮 (selector=%s)，等待 2s 后点击" % ("重启" if kind == "restart" else "启动", sel))
    pg.wait_for_timeout(2000)
    el.click()
    log("已点击%s按钮，等待 20s 确认指令" % ("重启" if kind == "restart" else "启动"))
    for _ in range(20):
        pg.wait_for_timeout(1000)
        if power_calls:
            pg.wait_for_timeout(5000)
            return True, "已捕获 POST %s body=%s" % (power_calls[0][0], power_calls[0][1])
    return False, "点击后 20 秒内未捕获到 power 请求 (selector=%s)" % sel


def main():
    from playwright.sync_api import sync_playwright
    log("=== OuiPanel 保活任务开始 ===")
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

        # 等待电源按钮出现 (最多 40s, 一次重载重试)
        for attempt in range(2):
            try:
                pg.wait_for_selector("button.sidebar-power-btn", timeout=40000)
                break
            except Exception:
                if attempt == 0:
                    log("等待电源按钮超时，sleep 5s 后重载页面重试")
                    pg.wait_for_timeout(5000)
                    pg.reload(wait_until="domcontentloaded")
                    pg.wait_for_timeout(10000)
                else:
                    log("重载后仍找不到电源按钮")

        # 判断服务器状态, 决定 restart 还是 start
        running = is_server_running(pg)
        if running is None:
            log("无法判断服务器状态，默认执行 restart")
            kind = "restart"
        elif running:
            log("服务器当前在线，执行重启 (restart)")
            kind = "restart"
        else:
            log("服务器当前离线，执行启动 (start)")
            kind = "start"

        succ, detail = click_power(pg, kind)
        if succ:
            log("操作成功: " + detail)
            print("RESULT=SUCCESS")
            b.close()
            return 0
        log("操作失败: " + detail)
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
