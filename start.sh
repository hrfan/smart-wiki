#!/bin/bash
# smart-wiki 转换服务管理脚本 (端口 18100)
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/venv"
PORT=18100
[ -d "$VENV" ] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install -q -r "$DIR/requirements.txt" -i https://mirrors.cloud.tencent.com/pypi/simple
case "$1" in
  stop)  pkill -f "uvicorn app:app" 2>/dev/null && echo "stopped" || echo "not running" ;;
  status) curl -s "http://127.0.0.1:$PORT/health" || echo "not running" ;;
  restart) "$0" stop; sleep 1; "$0" start ;;
  *)  pkill -f "uvicorn app:app" 2>/dev/null; sleep 1
      nohup uvicorn app:app --host 127.0.0.1 --port $PORT > "$DIR/service.log" 2>&1 &
      echo $! > "$DIR/service.pid"; echo "started pid $!" ;;
esac
