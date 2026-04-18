#!/usr/bin/env bash

# 🎨 统一启动脚本：一键启动所有服务和可选功能
# 启动以下模块：
# - 9881 跟读评测      (readalong_api.py / uvicorn)
# - 9880 主服务        (wx_api.py)
# - ✨ 可选：线稿生成  (generate_coloring_lineart.py)
#
# 默认行为：启动两者（9881 后台 + 9880 前台）。Ctrl+C 会同时退出并清理 9881。

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

WX_PORT="${WX_PORT:-9880}"
WX_HOST="${WX_HOST:-0.0.0.0}"
READALONG_PORT="${READALONG_PORT:-9881}"
READALONG_HOST="${READALONG_HOST:-127.0.0.1}"
READALONG_HEALTH_WAIT_SEC="${READALONG_HEALTH_WAIT_SEC:-12}"
FORCE_KILL_PORTS="${FORCE_KILL_PORTS:-1}"

if [[ -f "$PROJECT_ROOT/venv/Scripts/python.exe" ]]; then
  PYTHON_BIN="$PROJECT_ROOT/venv/Scripts/python"
else
  PYTHON_BIN="$PROJECT_ROOT/venv/bin/python"
fi
RUNTIME_DIR="$PROJECT_ROOT/train/runtime"
mkdir -p "$RUNTIME_DIR"

LOG_WX="$RUNTIME_DIR/wx_api_${WX_PORT}.log"
LOG_READALONG="$RUNTIME_DIR/readalong_${READALONG_PORT}.log"
PID_READALONG="$RUNTIME_DIR/readalong_${READALONG_PORT}.pid"

MODE="both"  # both | wx-only | readalong-only
RESTART_READALONG=0
GENERATE_LINEART=0  # 🎨 新增：是否生成线稿
DOCS_ONLY=0  # 是否仅打开文档

usage() {
  cat <<'USAGE_END'
📖 紫宝故事园 - 一键启动脚本

用法：
  ./start_wx_api.sh                      # 启动 9881(后台) + 9880(前台)
  
服务选项：
  --wx-only                              # 启动主服务(9880)并确保跟读依赖就绪
  --readalong-only                       # 仅启动跟读评测 (9881，前台)
  --restart-readalong                    # 重启跟读评测服务
  --ports-9880-9881                      # 使用 9880(主服务) + 9881(跟读/AI) 端口组合（默认端口不变）
  
🎨 涂色小画家选项：
  --generate-lineart                     # 生成 30 张线稿和区域索引图
                                         # 需要：Volcano Engine 密钥或本地代理
                                         # 耗时：30-60 分钟
  
文档选项：
  --docs                                 # 打开涂色小画家文档导航
  --health                               # 检查所有服务健康状态
  --logs                                 # 显示最近的日志位置
  
帮助：
  -h, --help                             # 显示帮助信息
  
示例：
  # 快速启动（推荐）
  ./start_wx_api.sh

  # 生成线稿（第一次部署时）
  ./start_wx_api.sh --generate-lineart

  # 检查健康状态
  ./start_wx_api.sh --health

多人联调（局域网/公网）提示：
  - 默认主服务监听 0.0.0.0（可被其他电脑访问）
  - 默认会自动释放占用端口并重启，确保命令一次执行即生效（可设 FORCE_KILL_PORTS=0 关闭）
  - 可通过环境变量调整监听地址/端口：
      WX_HOST=0.0.0.0 WX_PORT=9880 ./start_wx_api.sh --wx-only
      READALONG_HOST=0.0.0.0 READALONG_PORT=9881 ./start_wx_api.sh --readalong-only
      ./start_wx_api.sh --ports-9880-9881
USAGE_END
}

print_header() {
  echo ""
  echo "╔════════════════════════════════════════════════════╗"
  echo "║        🎨 紫宝故事园 - 一键启动脚本                ║"
  echo "║   Coloring Artist + Story Reading Game Platform    ║"
  echo "╚════════════════════════════════════════════════════╝"
  echo ""
}

show_logs() {
  echo ""
  echo "📋 日志位置："
  echo "   主服务 (9880):     $LOG_WX"
  echo "   跟读评测 (9881):   $LOG_READALONG"
  echo ""
  echo "查看日志："
  echo "   tail -f $LOG_WX"
  echo "   tail -f $LOG_READALONG"
  echo ""
}

health_check() {
  echo ""
  echo "🏥 服务健康检查..."
  echo ""
  
  if curl --noproxy '*' -sS -m 2 "http://127.0.0.1:${WX_PORT}/" >/dev/null 2>&1; then
    echo "✅ 主服务 (9880):       运行中"
  else
    echo "❌ 主服务 (9880):       未运行或无响应"
  fi
  
  if curl --noproxy '*' -sS -m 2 "http://127.0.0.1:${READALONG_PORT}/readalong/health" >/dev/null 2>&1; then
    echo "✅ 跟读评测 (9881):     运行中"
  else
    echo "❌ 跟读评测 (9881):     未运行或无响应"
  fi
  
  if curl --noproxy '*' -sS -m 2 "http://127.0.0.1:${WX_PORT}/coloring/health" >/dev/null 2>&1; then
    echo "✅ 涂色小画家 API:     已集成"
    COLORING_SKETCHES=$(curl --noproxy '*' -sS -m 2 "http://127.0.0.1:${WX_PORT}/coloring/get_sketches?limit=1" 2>/dev/null | grep -o '"total":[0-9]*' | cut -d':' -f2 || echo "?")
    echo "   └─ 可用线稿:         $COLORING_SKETCHES 张"
  else
    echo "⚠️  涂色小画家 API:     未集成或未运行"
  fi
  
  echo ""
}

generate_lineart_async() {
  echo ""
  echo "🎨 线稿生成启动"
  echo "════════════════════════════════════════════════════"
  echo ""
  echo "说明："
  echo "  • 生成 30 张涂色线稿和区域索引图"
  echo "  • 使用 Volcano Engine API（需要配置好密钥）"
  echo "  • 或使用本地代理 (http://127.0.0.1:7890)"
  echo ""
  echo ">>> 启动服务..."
  
  if should_start_readalong; then
    start_readalong_bg
  fi
  
  echo ">>> 启动主服务（后台）..."
  start_wx_bg_for_lineart
  
  for i in {1..30}; do
    if curl --noproxy '*' -sS -m 2 "http://127.0.0.1:${WX_PORT}/coloring/health" >/dev/null 2>&1; then
      echo "✅ API 已就绪，开始生成..."
      break
    fi
    if [ $i -eq 30 ]; then
      echo "❌ 主服务启动超时"
      exit 1
    fi
    sleep 1
  done
  
  echo ""
  echo ">>> 启动线稿生成（预计 30-60 分钟）..."
  echo ""
  
  "$PYTHON_BIN" modules/coloring_artist/practice/generate_coloring_lineart.py
  
  echo ""
  echo "✅ 线稿生成完成！"
  echo ""
  echo "生成的文件位置："
  echo "  • 线稿:     practice/coloring/lineart/*.png"
  echo "  • 区域图:   practice/coloring/regionmap/*.png"
  echo "  • 索引:     practice/coloring/index.json"
  echo ""
}

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
    --wx-only)
      MODE="wx-only"
      ;;
    --readalong-only)
      MODE="readalong-only"
      ;;
    --ports-9880-9881)
      WX_PORT="9880"
      READALONG_PORT="9981"
      ;;
    --restart-readalong)
      RESTART_READALONG=1
      ;;
    --generate-lineart)
      GENERATE_LINEART=1
      MODE="wx-only"
      ;;
    --docs)
      DOCS_ONLY=1
      DOCS_PATH="modules/coloring_artist/docs/INDEX.md"
      ;;
    --health)
      DOCS_ONLY=1
      ;;
    --logs)
      DOCS_ONLY=1
      LOGS_ONLY=1
      ;;
    *)
      echo "❌ 未知参数：$arg"
      usage
      exit 2
      ;;
  esac
done

if [ "$DOCS_ONLY" = "1" ]; then
  if [ "${LOGS_ONLY:-0}" = "1" ]; then
    show_logs
  else
    health_check
  fi
  exit 0
fi

# 项目根目录必须入路径，否则 `from modules.*` 无法解析；eres2net 为 GPT-SoVITS 子模块。
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/GPT_SoVITS/eres2net:${PYTHONPATH:-}"
# Windows 控制台编码：与 wx_api 内 stdout 重配一致，减少 GBK 下 Unicode 输出异常
export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

if [ -f "$PROJECT_ROOT/env/wx_api.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$PROJECT_ROOT/env/wx_api.env"
  set +a
elif [ -f "$PROJECT_ROOT/env/wx_api.env.example" ]; then
  # 仅在未提供 wx_api.env 时才加载 example，避免示例覆盖真实配置
  set -a
  # shellcheck disable=SC1090
  . "$PROJECT_ROOT/env/wx_api.env.example"
  set +a
fi

pick_free_gpu() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits 2>/dev/null | awk -F',' '{gsub(/ /, "", $1); gsub(/ /, "", $2); print $1 "," $2}' | sort -t',' -k2,2n | head -n 1 | cut -d',' -f1
    return 0
  fi
  echo "0"
}

case "${WX_API_CUDA_VISIBLE_DEVICES:-auto}" in
  auto|AUTO|Auto)
    export CUDA_VISIBLE_DEVICES="$(pick_free_gpu)"
    ;;
  *)
    export CUDA_VISIBLE_DEVICES="${WX_API_CUDA_VISIBLE_DEVICES}"
    ;;
esac

export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

echo "[gpu] CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}"
echo "[gpu] PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF}"

port_listening() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq ":${port}$"
    return $?
  fi
  # Windows（Git Bash）：无 ss，用 netstat 判断是否 LISTEN
  if command -v netstat >/dev/null 2>&1; then
    netstat -ano 2>/dev/null | grep LISTENING | grep -E ":${port}[[:space:]]" | grep -q .
    return $?
  fi
  return 1
}

kill_port_pids() {
  local port="$1"
  if [ "${FORCE_KILL_PORTS}" != "1" ]; then
    return 0
  fi
  local pids
  if command -v ss >/dev/null 2>&1; then
    pids=$(ss -ltnp 2>/dev/null | awk -v p=":${port}" '$4 ~ p {print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)
  elif command -v netstat >/dev/null 2>&1; then
    # Windows：如果没有监听匹配，grep 会返回 1；配合 pipefail + set -e 会导致脚本直接退出
    # 因此末尾补 `|| true`，让“无匹配”视为 pids 为空即可。
    pids=$(netstat -ano 2>/dev/null | grep LISTENING | grep -E ":${port}[[:space:]]" | awk '{print $NF}' | sort -u || true)
  else
    return 0
  fi
  if [ -n "$pids" ]; then
    echo ">>> 发现占用端口 ${port} 的进程，正在关闭..."
    for pid in $pids; do
      [ -z "$pid" ] || [ "$pid" = "0" ] && continue
      if command -v ss >/dev/null 2>&1; then
        kill "$pid" 2>/dev/null || true
      elif command -v taskkill >/dev/null 2>&1; then
        taskkill //PID "$pid" //F 2>/dev/null || true
      else
        kill -9 "$pid" 2>/dev/null || true
      fi
    done
    sleep 1
  fi
}

should_start_readalong() {
  if [ -n "${READALONG_ENABLED:-}" ]; then
    case "${READALONG_ENABLED}" in
      0|false|False|FALSE) return 1;;
      *) return 0;;
    esac
  fi

  case "${READALONG_PROXY_ENABLED:-1}" in
    0|false|False|FALSE) return 1;;
    *) return 0;;
  esac
}

STARTED_READALONG=0
STARTED_READALONG_PID=""

# 是否在脚本退出时停止“本次脚本拉起”的 readalong：
# - both: 维持原行为（退出时联动停止）
# - wx-only: 保持 readalong 常驻，避免演说家/图片描述链路被中断
# - readalong-only: 前台模式，不走后台清理
STOP_READALONG_ON_EXIT=0
case "$MODE" in
  both) STOP_READALONG_ON_EXIT=1 ;;
  wx-only) STOP_READALONG_ON_EXIT=0 ;;
  readalong-only) STOP_READALONG_ON_EXIT=0 ;;
esac

cleanup() {
  if [ "$STOP_READALONG_ON_EXIT" != "1" ]; then
    return 0
  fi
  if [ "$STARTED_READALONG" = "1" ] && [ -n "$STARTED_READALONG_PID" ]; then
    if kill -0 "$STARTED_READALONG_PID" 2>/dev/null; then
      echo ">>> 正在停止 readalong..."
      kill "$STARTED_READALONG_PID" 2>/dev/null || true
    fi
  fi
}
trap cleanup EXIT INT TERM

start_readalong_bg() {
  local auto_restart="${READALONG_AUTO_RESTART:-1}"

  readalong_health() {
    local h
    h=$(curl --noproxy '*' -sS -m 2 "http://127.0.0.1:${READALONG_PORT}/readalong/health" 2>/dev/null || true)
    if [ -z "$h" ]; then
      h=$(curl --noproxy '*' -sS -m 2 "http://[::1]:${READALONG_PORT}/readalong/health" 2>/dev/null || true)
    fi
    echo -n "$h"
  }

  if port_listening "$READALONG_PORT"; then
    if [ "$RESTART_READALONG" = "1" ]; then
      echo "[readalong] 检测到 --restart-readalong，尝试重启..."
      kill_port_pids "$READALONG_PORT"
    else
      local h
      h=$(readalong_health)

      if [ -z "$h" ]; then
        echo "[readalong] 端口监听但 health 不通，强制重启..."
        kill_port_pids "$READALONG_PORT"
      elif [ "$auto_restart" != "0" ] && [ -n "${SAFETY_AI_API_KEY:-}${AI_API_KEY:-}" ] && echo "$h" | grep -q '"ai_configured":false'; then
        echo "[readalong] AI 配置不完整，自动重启..."
        kill_port_pids "$READALONG_PORT"
      elif [ "$auto_restart" != "0" ] && [ -n "${READALONG_ASR_MODEL:-}" ] && ! echo "$h" | grep -q "\"asr_model\":\"${READALONG_ASR_MODEL}\""; then
        echo "[readalong] ASR 模型配置变化，自动重启..."
        kill_port_pids "$READALONG_PORT"
      else
        echo "[readalong] 已在运行"
        return 0
      fi
    fi

    for _ in $(seq 1 20); do
      if ! port_listening "$READALONG_PORT"; then
        break
      fi
      sleep 0.5
    done
  fi

  if port_listening "$READALONG_PORT"; then
    echo "!!! readalong 端口 ${READALONG_PORT} 仍被占用"
    exit 1
  fi

  echo ">>> 启动 readalong (后台) ..."
  : > "$LOG_READALONG"
  "$PYTHON_BIN" -m uvicorn modules.speaker_game.readalong_api:app --host "$READALONG_HOST" --port "$READALONG_PORT" --log-level info >> "$LOG_READALONG" 2>&1 &
  local launched_pid="$!"
  echo "$launched_pid" > "$PID_READALONG"
  STARTED_READALONG=1
  STARTED_READALONG_PID="$launched_pid"

  local health_wait_sec="${READALONG_HEALTH_WAIT_SEC}"
  case "${READALONG_ASR_WARMUP_BLOCKING:-0}" in
    1|true|True|TRUE)
      if [ "${health_wait_sec}" -lt 360 ]; then
        health_wait_sec=360
      fi
      ;;
  esac

  for _ in $(seq 1 "${health_wait_sec}"); do
    local h
    h=$(readalong_health)
    if [ -n "$h" ]; then
      echo "✅ readalong (9881) 已启动"
      return 0
    fi
    sleep 1
  done

  echo "!!! readalong 启动失败"
  tail -n 120 "$LOG_READALONG" || true
  exit 1
}

start_readalong_fg() {
  if port_listening "$READALONG_PORT"; then
    echo "[readalong] 端口 ${READALONG_PORT} 已在监听"
    exit 0
  fi

  echo ">>> 启动 readalong (前台) ..."
  "$PYTHON_BIN" -m uvicorn modules.speaker_game.readalong_api:app --host "$READALONG_HOST" --port "$READALONG_PORT" --log-level info
}

start_wx_fg() {
  echo ">>> 检查端口 ${WX_PORT} ..."
  kill_port_pids "$WX_PORT"  # 仅在 FORCE_KILL_PORTS=1 时生效

  if port_listening "$WX_PORT"; then
    echo "!!! 端口 ${WX_PORT} 仍被占用"
    echo "    建议：设置 WX_PORT 为未占用端口，或 FORCE_KILL_PORTS=1 强制释放。"
    exit 1
  fi

  echo ">>> 启动 wx_api.py（封装入口）(前台) ..."
  : > "$LOG_WX"
  "$PYTHON_BIN" -u modules/tts_backend/wx_api.py -a "$WX_HOST" -p "$WX_PORT" 2>&1 | tee -a "$LOG_WX"
}

start_wx_bg_for_lineart() {
  echo ">>> 检查端口 ${WX_PORT} ..."
  kill_port_pids "$WX_PORT"  # 仅在 FORCE_KILL_PORTS=1 时生效

  if port_listening "$WX_PORT"; then
    echo "!!! 端口 ${WX_PORT} 仍被占用"
    echo "    建议：设置 WX_PORT 为未占用端口，或 FORCE_KILL_PORTS=1 强制释放。"
    exit 1
  fi

  echo ">>> 启动 wx_api.py（封装入口）(后台) ..."
  : > "$LOG_WX"
  "$PYTHON_BIN" -u modules/tts_backend/wx_api.py -a "$WX_HOST" -p "$WX_PORT" >> "$LOG_WX" 2>&1 &
  WX_PID=$!
  echo $! > "$RUNTIME_DIR/wx_api_lineart.pid"
  
  for _ in $(seq 1 30); do
    if curl --noproxy '*' -sS -m 2 "http://127.0.0.1:${WX_PORT}/" >/dev/null 2>&1; then
      echo "✅ wx_api (9880) 已启动"
      return 0
    fi
    sleep 1
  done
  
  echo "❌ wx_api 启动失败"
  kill $WX_PID 2>/dev/null || true
  exit 1
}

print_header

if [ "$GENERATE_LINEART" = "1" ]; then
  generate_lineart_async
  exit 0
fi

case "$MODE" in
  readalong-only)
    start_readalong_fg
    ;;
  wx-only)
    if should_start_readalong; then
      start_readalong_bg
    else
      echo "[readalong] 跟读评测未启用"
    fi
    start_wx_fg
    ;;
  both)
    if should_start_readalong; then
      start_readalong_bg
    else
      echo "[readalong] 跟读评测未启用"
    fi
    start_wx_fg
    ;;
  *)
    echo "内部错误：未知 MODE=$MODE"
    exit 2
    ;;
esac
