# OuiPanel 页面结构与自动保活方案

> 目标 URL：`https://dash.ouipanel.com/server/******/console`
> 首次分析：2026-09-05 ｜ 实测自动化验证：2026-09-05（成功）

## 一、页面结构

`dash.ouipanel.com` 是一个 **React 单页应用（SPA）**，HTML 壳里只有 `<div id="root"></div>`，内容由 JavaScript 动态渲染。

### 1.1 静态资源

| 资源 | 地址 |
|------|------|
| 主 JS bundle | `https://dash.ouipanel.com/static/js/main.451c7ea5.js` |
| 主 CSS | `https://dash.ouipanel.com/static/css/main.e12c85ce.css` |
| Favicon | `https://dash.ouipanel.com/favicon.ico` |

### 1.2 技术栈

- **框架**：React 18
- **路由**：React Router
- **UI 库**：Bootstrap 5 + Material-UI（MUI）
- **图表/编辑器**：ApexCharts、CodeMirror、Xterm 等（用于控制台、日志、配置编辑）
- **防护**：Cloudflare JS Challenge（headless Chromium 实测可正常通过，无需额外处理）

### 1.3 主要路由

- `/` — 主页（登录后为 My Servers 服务器列表）
- `/login` — 登录入口（无本地表单）
- `/auth-callback` — OAuth 回调处理页（URL 带 `?token=...`）
- `server/:serverId/console` — 服务器控制台页面（受保护路由，未登录重定向到 `/login`）

## 二、登录方式

**没有本地用户名/密码表单。** 登录采用 **WHMCS OAuth2 单点登录**（OuiHeberg.com 统一鉴权）。账号信息见同目录 `account.txt`。

### 2.1 完整登录流程（实测）

1. **获取 OAuth 授权链接**

   ```http
   GET https://ouipanel.com/auth/oauth/whmcs
   ```

   返回 JSON：

   ```json
   {
     "redirect": "https://manager.ouiheberg.com/oauth/authorize.php?client_id=OUIHEBERG.l5FKfKBRhRNEzpjmc3jxyQ%3D%3D&redirect_uri=https%3A%2F%2Fouipanel.com%2Fauth%2Foauth%2Fwhmcs%2Fcallback&scope=openid+email+profile&response_type=code&state=..."
   }
   ```

2. **跳转 WHMCS 登录页**（`manager.ouiheberg.com/oauth/authorize.php?...`）

   登录表单字段（实测）：

   | 字段 | 选择器 | 说明 |
   |------|--------|------|
   | 邮箱 | `#inputEmail` | type=email，占位 "Saisissez l'adresse e-mail" |
   | 密码 | `#inputPassword` | type=password |
   | 提交按钮 | `button[type=submit]` | 文本 "Se connecter" |

3. **WHMCS 登录后** → 跳回 `https://ouipanel.com/auth/login`，页面出现按钮 **"Connexion avec OuiHeberg.com"**，必须点击它完成最终登录。

4. **点击后** → `https://dash.ouipanel.com/auth-callback?token=...` 自动处理 token 交换（**不要打断**，等待其自然跳转）。

5. **自然跳转** → `https://dash.ouipanel.com/`（标题 "OuiPanel - My Servers"），登录完成。

   实测时序：点击 Connexion 后约 4s 到 auth-callback，约 18s 到主页。**关键：此过程不能强行走下一步，必须 sleep 等待 SPA 自行完成。**

### 2.2 会话与 Token 存储

- Cookie：`pterodactyl_session`、`XSRF-TOKEN`（域 `ouipanel.com`）、`cf_clearance`（域 `.ouipanel.com`）、`WHMCS2FKIB7vAIJz4`（域 `manager.ouiheberg.com`）
- localStorage：`authState`（加密存储的 API Bearer Token，`U2FsdGVkX1/...` 为 CryptoJS AES 格式）
- 完整会话可用 Playwright `context.storage_state()` 一次性保存（cookies + localStorage 都会写入 `cookies.txt`），下次运行直接复用

### 2.3 关键接口汇总

| 接口 | 作用 |
|------|------|
| `GET https://ouipanel.com/auth/oauth/whmcs` | 获取 WHMCS OAuth 授权链接 |
| `GET https://ouipanel.com/auth/oauth/whmcs/callback` | OAuth 回调，建立 session |
| `GET https://ouipanel.com/auth/login` | 登录中转页（含 "Connexion" 按钮） |
| `POST https://ouipanel.com/api/client/servers/*****/power` | 电源控制，body `{"signal":"restart"|"start"}` |
| `GET https://ouipanel.com/api/client/news` 等 | 业务 API |

## 三、Console 页面电源按钮（实测）

| 按钮 | 位置/选择器 | 文本 | 状态 |
|------|-------------|------|------|
| 停止 | `button.sidebar-power-btn.power-stop` | Arrêter（图标按钮） | 始终可用 |
| **重启** | `button.sidebar-power-btn.power-restart` | **Redémarrer**（图标按钮） | **始终可用** |
| **启动** | `button.sidebar-power-btn.power-start` | Démarrer（图标按钮） | **始终可用** |
| Start | 工具栏 `button.btn-sm.btn-outline-success` | Start | 服务器离线时可用 |
| Stop / Restart / Force stop | 工具栏 `button.btn-sm.btn-outline-*` | 英文 | 服务器离线时 disabled |

- 服务器离线时页面提示：`[OuiPanel] Server is currently offline. Use the control buttons to start it.`
- 点击侧边栏电源按钮**无确认弹窗**，直接发送：

  ```http
  POST https://ouipanel.com/api/client/servers/*****/power
  Content-Type: application/json

  {"signal":"restart"}   # 或 {"signal":"start"}
  ```

- **推荐点击对象**：`button.sidebar-power-btn.power-restart`（在线重启）/ `button.sidebar-power-btn.power-start`（离线拉起）
- **重要实测结论**：`restart` 信号对**已离线**服务器无效（不会拉起），离线时必须发 `start` 才能启动

## 四、自动保活脚本

### 4.1 运行环境

- Python 虚拟环境：`/root/ouipanel/venv`（Python 3.11 + Playwright 1.62）
- 浏览器：系统 `/usr/bin/chromium`（headless，需 `--no-sandbox`）
- 凭据：运行时从 `account.txt` 读取（脚本内不硬编码）

### 4.2 脚本 `restart_panel.py`（智能保活）

```bash
/root/ouipanel/venv/bin/python /root/ouipanel/restart_panel.py
```

流程：

1. **快路径**：加载 `cookies.txt`（cookies + localStorage）→ 打开 console 页面
2. 若被重定向到 `/login`（会话失效）→ **慢路径**：完整 OAuth 登录 → 重新保存 `cookies.txt`
3. 等待电源按钮渲染（含 sleep，超时自动重载重试一次）
4. **智能判断服务器状态**：`Start` 按钮 disabled=在线 / 可用=离线
5. 在线 → 点击 `power-restart`（重启）；离线 → 点击 `power-start`（拉起）
6. 通过捕获 `POST /power {"signal":"restart"|"start"}` 请求确认指令已发出
7. 日志写入 `restart.log`，输出 `RESULT=SUCCESS/FAILED/ERROR`

辅助脚本 `start_panel.py`：固定发 start 信号（手动拉起用）。

### 4.3 定时任务（已启用 2026-09-05，每半小时）

```cron
*/30 * * * * /root/ouipanel/venv/bin/python /root/ouipanel/restart_panel.py >> /root/ouipanel/cron.log 2>&1
```

- 整点与半点各执行一次
- 在线则重启、离线则自动拉起，确保服务器不掉线

## 五、目录文件清单

| 文件 | 说明 |
|------|------|
| `OuiPanel_login_analysis.md` | 本文档 |
| `account.txt` | 帐号+密码（`main:<邮箱>` / `pass：<密码>`） |
| `cookies.txt` | 登录态（cookies + localStorage），脚本自动读写 |
| `restart_panel.py` | 智能保活主脚本（cron 调用） |
| `start_panel.py` | 手动启动脚本（固定发 start） |
| `check_status.py` | 手动检查服务器状态 |
| `restart.log` | 运行日志 |
| `venv/` | Python 虚拟环境 |
| `recon*.py` | 侦察/调试脚本（可清理） |

## 六、注意事项

- 自动化仅使用用户自己授权的账号（`account.txt`），不使用任何第三方凭据
- 登录过程中**不要打断 SPA 的 auth-callback 跳转**，需要 sleep 等待渲染
- 每半小时执行一次保活：在线则重启、离线则自动拉起（会真实影响服务器运行）
- 若重启后服务器仍频繁掉线，说明是游戏服自身崩溃，需查 console 日志定位原因
