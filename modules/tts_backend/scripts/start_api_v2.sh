#!/usr/bin/env bash

# 一键启动 api_v2（历史脚本，当前主流程推荐使用 start_wx_api.sh）：
# 1. 自动找到并关闭占用端口的旧进程
# 2. 固化 PYTHONPATH，确保 ERes2NetV2 可被导入
# 3. 使用项目自带 venv 启动 api_v2.py

set -e

# modules/tts_backend/scripts -> project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PORT="${PORT:-9880}"
HOST="${HOST:-127.0.0.1}"
CONFIG="${CONFIG:-$PROJECT_ROOT/GPT_SoVITS/configs/tts_infer.yaml}"
if [[ -f "$PROJECT_ROOT/venv/Scripts/python.exe" ]]; then
  PYTHON_BIN="$PROJECT_ROOT/venv/Scripts/python"
else
  PYTHON_BIN="$PROJECT_ROOT/venv/bin/python"
fi

cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/GPT_SoVITS/eres2net:${PYTHONPATH:-}"

echo ">>> 检查是否有进程占用端口 $PORT ..."
PIDS=$(ss -ltnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p {print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)

if [ -n "$PIDS" ]; then
  echo ">>> 发现占用端口 $PORT 的进程: $PIDS，尝试关闭..."
  for pid in $PIDS; do
    if kill "$pid" 2>/dev/null; then
      echo "  已发送 SIGTERM 给 PID $pid"
    fi
  done
  sleep 1
fi

echo ">>> 确认端口状态..."
if ss -ltnp 2>/dev/null | grep -q ":$PORT\\b"; then
  echo "!!! 端口 $PORT 仍被占用，请手动检查进程后重试"
  ss -ltnp | grep ":$PORT\\b" || true
  exit 1
fi

echo ">>> 使用虚拟环境启动 api_v2（封装入口）..."
exec "$PYTHON_BIN" -u modules/tts_backend/api_v2.py -a "$HOST" -p "$PORT" -c "$CONFIG"
