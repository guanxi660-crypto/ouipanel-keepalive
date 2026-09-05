#!/bin/bash
# OuiPanel Keep-Alive - cron 一键安装脚本
# 用法: bash install_cron.sh [分钟间隔，默认30]
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
INTERVAL="${1:-30}"

if [ ! -x "$DIR/venv/bin/python" ]; then
  echo "[错误] 未找到 $DIR/venv/bin/python，请先执行: python3 -m venv venv && ./venv/bin/pip install playwright"
  exit 1
fi

if [ ! -f "$DIR/restart_panel.py" ]; then
  echo "[错误] 未找到 $DIR/restart_panel.py"
  exit 1
fi

CRON_LINE="*/$INTERVAL * * * * $DIR/venv/bin/python $DIR/restart_panel.py >> $DIR/cron.log 2>&1"

# 先移除旧的该任务行，再追加，避免重复
(crontab -l 2>/dev/null | grep -v "restart_panel.py"; echo "$CRON_LINE") | crontab -

echo "[完成] cron 已安装:"
echo "  $CRON_LINE"
echo "  当前生效任务:"
crontab -l | grep restart_panel.py
