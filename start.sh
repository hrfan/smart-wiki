#!/bin/bash
# smart-wiki 转换服务管理脚本 (端口 9200)
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/venv"
PORT=9200
[ -d "$VENV" ] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install -q -r "$DIR/requirements.txt" -i https://mirrors.cloud.tencent.com/pypi/simple
# ===== 配置区（改这里）=====
export SMARTWIKI_KEYS="${SMARTWIKI_KEYS:-smartwiki2026}"        # API 密钥，逗号分隔可多个
export SMART_AUTH_URL="${SMART_AUTH_URL:-http://127.0.0.1:9000/system/auth/validate}"  # smart 单点认证校验地址（POST，body.code=200 才放行）
# ============================
case "$1" in
  stop)  pkill -f "uvicorn app:app" 2>/dev/null && echo "stopped" || echo "not running" ;;
  status) curl -s "http://127.0.0.1:$PORT/health" || echo "not running" ;;
  restart) "$0" stop; sleep 1; "$0" start ;;
  *)  pkill -f "uvicorn app:app" 2>/dev/null; sleep 1
      nohup uvicorn app:app --host 0.0.0.0 --port $PORT > "$DIR/service.log" 2>&1 &
      echo $! > "$DIR/service.pid"; echo "started pid $!" ;;
esac
