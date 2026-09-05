# OuiPanel Keep-Alive 自动保活脚本

> 自动化登录 OuiPanel 面板控制台，定时重启 / 拉起服务器（Minecraft 等）。
> 本项目为 **Python + Playwright** 实现，完全在本地浏览器环境运行。

---

## ⚠️ 严肃声明（必读 / READ THIS FIRST）

**本项目仅供学习交流使用（for educational purposes only）。**

- **严禁**将本项目部署到 **GitHub Actions 或任何 CI/CD 平台**上运行。
- 如此**短周期的 cron 保活任务**会给 **GitHub 公益服务器带来巨大压力**，属于**滥用公共资源**，可能导致账号封禁甚至影响他人使用。
- 请务必在你**自己的本地电脑或远程 VPS** 上运行本脚本，并合理设置运行频率（建议 ≥30 分钟/次）。
- 请遵守 OuiPanel / OuiHeberg 服务条款，不要对你的服务器进行超出需求的频繁操作。
- **使用本项目产生的任何后果由使用者自行承担。**

---

## 功能特性

- 每 30 分钟自动登录 OuiPanel 面板控制台
- **智能保活**：
  - 服务器**在线** → 自动发送 `restart`（重启）
  - 服务器**离线** → 自动发送 `start`（拉起）
- 会话失效自动重新登录（WHMCS OAuth2 完整流程）
- 登录态自动保存复用（cookies + localStorage），大幅降低登录频率
- 完整运行日志（`restart.log`、`cron.log`）

## 环境要求

- Python 3.11+
- Playwright + Chromium（Linux VPS / 本地电脑均可）

## 快速开始

### 1. 安装依赖

```bash
cd ouipanel-keepalive
python3 -m venv venv
./venv/bin/pip install playwright
# 安装 Playwright 浏览器（或修改脚本 executable_path 指向系统 chromium）
./venv/bin/playwright install chromium
```

### 2. 配置账号

编辑 `account.txt`（**已被 .gitignore 排除，不会上传**）：

```
main:你的登录邮箱
pass：你的登录密码
```

### 3. 修改目标服务器

编辑 `restart_panel.py` 中的 `TARGET` 为你的服务器控制台地址：

```python
TARGET = "https://dash.ouipanel.com/server/YOUR_SERVER_ID/console"
```

### 4. 手动运行测试

```bash
./venv/bin/python restart_panel.py
```

看到 `RESULT=SUCCESS` 即表示保活指令已成功发出。

## 定时任务（cron job 版）

### 方式一：一键安装

```bash
bash install_cron.sh
```

### 方式二：手动添加 crontab

每 30 分钟执行一次：

```cron
*/30 * * * * /绝对路径/venv/bin/python /绝对路径/restart_panel.py >> /绝对路径/cron.log 2>&1
```

### 移除定时任务

```bash
crontab -l | grep -v restart_panel.py | crontab -
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `restart_panel.py` | 主脚本（智能保活：在线重启 / 离线拉起） |
| `start_panel.py` | 手动启动脚本（固定发送 start） |
| `check_status.py` | 检查服务器当前状态 |
| `install_cron.sh` | 一键安装 cron 定时任务 |
| `OuiPanel_login_analysis.md` | OuiPanel 面板结构与自动化方案分析文档 |
| `account.txt` | 账号配置（本地，不上传） |
| `cookies.txt` | 登录态缓存（本地，不上传） |

## 工作原理

1. 复用保存的登录态直接进入控制台页面（快路径）
2. 会话失效时走 WHMCS OAuth2 完整登录并重新保存（慢路径）
3. 通过 `Start` 按钮的 disabled 状态判断服务器在线/离线
4. 点击对应电源按钮，通过捕获 `POST /power {"signal":"restart"|"start"}` 验证指令送达
5. 结果写入日志，退出码 0=成功 / 1=失败

---

## 免责声明

本项目仅用于**技术交流与学习**，请在遵守相关服务条款与法律法规的前提下合理使用。
**切勿部署到 GitHub Actions / CI 平台运行定时任务，以免给 GitHub 公益服务器带来压力。**
