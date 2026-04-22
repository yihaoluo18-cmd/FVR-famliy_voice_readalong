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

PYTHON_BIN="$PROJECT_ROOT/venv/bin/python"
RUNTIME_DIR="$PROJECT_ROOT/runtime"
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

export PYTHONPATH="$PROJECT_ROOT/GPT_SoVITS/eres2net:${PYTHONPATH:-}"

ENV_CANDIDATES=(
  "$PROJECT_ROOT/wx_api.env"
  "$PROJECT_ROOT/env/wx_api.env"
  "$PROJECT_ROOT/wx_api.env.example"
  "$PROJECT_ROOT/env/wx_api.env.example"
)
for env_file in "${ENV_CANDIDATES[@]}"; do
  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
    echo "[env] loaded: $env_file"
    break
  fi
done

pick_free_gpu() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits 2>/dev/null | awk -F',' '{gsub(/ /, "", $1); gsub(/ /, "", $2); print $1 "," $2}' | sort -t',' -k2,2n | head -n 1 | cut -d',' -f1
    return 0
  fi
  echo "0"
}

pick_secondary_gpu() {
  local primary="$1"
  if command -v nvidia-smi >/dev/null 2>&1; then
    local secondary
    secondary=$(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits 2>/dev/null | awk -F',' -v p="$primary" '{gsub(/ /, "", $1); gsub(/ /, "", $2); if ($1 != p) print $1 "," $2}' | sort -t',' -k2,2n | head -n 1 | cut -d',' -f1)
    if [ -n "$secondary" ]; then
      echo "$secondary"
      return 0
    fi
  fi
  echo "$primary"
}

pick_n_free_gpus() {
  local need="${1:-2}"
  local exclude_csv="${2:-}"
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "0"
    return 0
  fi

  local picked
  picked=$(
    nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits 2>/dev/null \
      | awk -F',' -v ex="$exclude_csv" '
          BEGIN{
            split(ex, arr, ",");
            for(i in arr){
              gsub(/ /, "", arr[i]);
              if(arr[i]!=""){ excl[arr[i]]=1; }
            }
          }
          {
            gsub(/ /, "", $1); gsub(/ /, "", $2);
            if(!($1 in excl)){ print $1 "," $2; }
          }' \
      | sort -t',' -k2,2nr \
      | head -n "$need" \
      | cut -d',' -f1 \
      | paste -sd, -
  )
  if [ -z "$picked" ]; then
    picked="$(pick_free_gpu)"
  fi
  echo "$picked"
}

WX_PROCESS_CUDA_VISIBLE_DEVICES=""
READALONG_PROCESS_CUDA_VISIBLE_DEVICES=""

# 支持外部直接传 CUDA_VISIBLE_DEVICES，不被脚本 auto 选择覆盖。
if [ -z "${WX_API_CUDA_VISIBLE_DEVICES:-}" ] && [ -n "${CUDA_VISIBLE_DEVICES:-}" ]; then
  WX_API_CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES}"
fi

case "${WX_API_CUDA_VISIBLE_DEVICES:-auto}" in
  auto|AUTO|Auto)
    WX_PROCESS_CUDA_VISIBLE_DEVICES="$(pick_free_gpu)"
    if [ -n "${READALONG_CUDA_VISIBLE_DEVICES:-}" ]; then
      READALONG_PROCESS_CUDA_VISIBLE_DEVICES="${READALONG_CUDA_VISIBLE_DEVICES}"
    else
      READALONG_PROCESS_CUDA_VISIBLE_DEVICES="$(pick_secondary_gpu "${WX_PROCESS_CUDA_VISIBLE_DEVICES}")"
    fi
    ;;
  *)
    WX_PROCESS_CUDA_VISIBLE_DEVICES="${WX_API_CUDA_VISIBLE_DEVICES}"
    READALONG_PROCESS_CUDA_VISIBLE_DEVICES="${READALONG_CUDA_VISIBLE_DEVICES:-${WX_PROCESS_CUDA_VISIBLE_DEVICES}}"
    ;;
esac

[ -n "${WX_PROCESS_CUDA_VISIBLE_DEVICES}" ] || WX_PROCESS_CUDA_VISIBLE_DEVICES="0"
[ -n "${READALONG_PROCESS_CUDA_VISIBLE_DEVICES}" ] || READALONG_PROCESS_CUDA_VISIBLE_DEVICES="${WX_PROCESS_CUDA_VISIBLE_DEVICES}"

# 兼容脚本内其他依赖该变量的逻辑。
export CUDA_VISIBLE_DEVICES="${WX_PROCESS_CUDA_VISIBLE_DEVICES}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
# 在 CUDA_VISIBLE_DEVICES 子集映射下固定逻辑设备号，避免进程内按全局序号选卡触发 invalid device ordinal。
export INFER_DEVICE="${INFER_DEVICE:-cuda:0}"

# 训练优化默认参数（可被外部环境变量覆盖）：
# - 自动开启预处理并行
# - 自动探测可用卡用于 prepare 并行和 S2
# - v2Pro 默认启用 DDP find_unused 兼容项
export TRAIN_PREP_PARALLEL="${TRAIN_PREP_PARALLEL:-1}"
export TRAIN_PREP_CACHE="${TRAIN_PREP_CACHE:-0}"
export TRAIN_PREP_TINY_PARALLEL_STEPS="${TRAIN_PREP_TINY_PARALLEL_STEPS:-step2,step2b,step3}"
export TRAIN_PREP_COMBINE_2_2B_3="${TRAIN_PREP_COMBINE_2_2B_3:-1}"
export TRAIN_PREP_STEP1_FORCE_SINGLE_GPU="${TRAIN_PREP_STEP1_FORCE_SINGLE_GPU:-1}"
# 默认复用预处理 GPU 列表中的第一个 GPU 给 step1（也可外部覆盖）
export TRAIN_PREP_STEP1_CUDA_VISIBLE_DEVICES="${TRAIN_PREP_STEP1_CUDA_VISIBLE_DEVICES:-}"
if [ -z "${TRAIN_PREP_CUDA_VISIBLE_DEVICES:-}" ]; then
  TRAIN_PREP_CUDA_VISIBLE_DEVICES="$(pick_n_free_gpus 2 "${WX_PROCESS_CUDA_VISIBLE_DEVICES},${READALONG_PROCESS_CUDA_VISIBLE_DEVICES}")"
fi
if [ -z "${TRAIN_PREP_STEP1_CUDA_VISIBLE_DEVICES:-}" ]; then
  TRAIN_PREP_STEP1_CUDA_VISIBLE_DEVICES="$(echo "${TRAIN_PREP_CUDA_VISIBLE_DEVICES}" | awk -F',' '{print $1}')"
fi
if [ -z "${TRAIN_S1_CUDA_VISIBLE_DEVICES:-}" ]; then
  TRAIN_S1_CUDA_VISIBLE_DEVICES="$(pick_n_free_gpus 2 "${WX_PROCESS_CUDA_VISIBLE_DEVICES},${READALONG_PROCESS_CUDA_VISIBLE_DEVICES}")"
fi
if [ -z "${TRAIN_S2_CUDA_VISIBLE_DEVICES:-}" ]; then
  TRAIN_S2_CUDA_VISIBLE_DEVICES="$(pick_n_free_gpus 2 "${WX_PROCESS_CUDA_VISIBLE_DEVICES},${READALONG_PROCESS_CUDA_VISIBLE_DEVICES},${TRAIN_S1_CUDA_VISIBLE_DEVICES}")"
fi
export TRAIN_PREP_CUDA_VISIBLE_DEVICES
export TRAIN_S1_CUDA_VISIBLE_DEVICES
export TRAIN_S2_CUDA_VISIBLE_DEVICES
export S2_FIND_UNUSED_PARAMETERS="${S2_FIND_UNUSED_PARAMETERS:-1}"
# S1 默认参数（可被外部覆盖）
export TRAIN_S1_BATCH_SIZE="${TRAIN_S1_BATCH_SIZE:-32}"
export TRAIN_S1_MAX_EPOCHS="${TRAIN_S1_MAX_EPOCHS:-15}"
export TRAIN_PARALLEL_S1_S2="${TRAIN_PARALLEL_S1_S2:-1}"
export TRAIN_FORCE_SERIAL_SAME_GPU_PAIR="${TRAIN_FORCE_SERIAL_SAME_GPU_PAIR:-0}"
export TRAIN_SERIAL_GPU_GUARD_MIN_FREE_MB="${TRAIN_SERIAL_GPU_GUARD_MIN_FREE_MB:-8192}"
export TRAIN_SERIAL_GPU_GUARD_TIMEOUT_SEC="${TRAIN_SERIAL_GPU_GUARD_TIMEOUT_SEC:-120}"
# S2 精调默认（当前默认：batch=16, epochs=6，双卡见 TRAIN_S2_CUDA_VISIBLE_DEVICES；可被外部环境变量覆盖）
export TRAIN_S2_BATCH_SIZE="${TRAIN_S2_BATCH_SIZE:-16}"
export TRAIN_S2_MAX_EPOCHS="${TRAIN_S2_MAX_EPOCHS:-6}"

echo "[gpu] WX CUDA_VISIBLE_DEVICES=${WX_PROCESS_CUDA_VISIBLE_DEVICES}"
echo "[gpu] READALONG CUDA_VISIBLE_DEVICES=${READALONG_PROCESS_CUDA_VISIBLE_DEVICES}"
echo "[gpu] PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF}"
echo "[train-opt] TRAIN_PREP_PARALLEL=${TRAIN_PREP_PARALLEL}"
echo "[train-opt] TRAIN_PREP_CACHE=${TRAIN_PREP_CACHE}"
echo "[train-opt] TRAIN_PREP_TINY_PARALLEL_STEPS=${TRAIN_PREP_TINY_PARALLEL_STEPS}"
echo "[train-opt] TRAIN_PREP_COMBINE_2_2B_3=${TRAIN_PREP_COMBINE_2_2B_3}"
echo "[train-opt] TRAIN_PREP_STEP1_FORCE_SINGLE_GPU=${TRAIN_PREP_STEP1_FORCE_SINGLE_GPU}"
echo "[train-opt] TRAIN_PREP_STEP1_CUDA_VISIBLE_DEVICES=${TRAIN_PREP_STEP1_CUDA_VISIBLE_DEVICES}"
echo "[train-opt] TRAIN_PREP_CUDA_VISIBLE_DEVICES=${TRAIN_PREP_CUDA_VISIBLE_DEVICES}"
echo "[train-opt] TRAIN_S1_CUDA_VISIBLE_DEVICES=${TRAIN_S1_CUDA_VISIBLE_DEVICES}"
echo "[train-opt] TRAIN_S2_CUDA_VISIBLE_DEVICES=${TRAIN_S2_CUDA_VISIBLE_DEVICES}"
echo "[train-opt] TRAIN_S1_BATCH_SIZE=${TRAIN_S1_BATCH_SIZE}"
echo "[train-opt] TRAIN_S1_MAX_EPOCHS=${TRAIN_S1_MAX_EPOCHS}"
echo "[train-opt] TRAIN_PARALLEL_S1_S2=${TRAIN_PARALLEL_S1_S2}"
echo "[train-opt] TRAIN_FORCE_SERIAL_SAME_GPU_PAIR=${TRAIN_FORCE_SERIAL_SAME_GPU_PAIR}"
echo "[train-opt] TRAIN_SERIAL_GPU_GUARD_MIN_FREE_MB=${TRAIN_SERIAL_GPU_GUARD_MIN_FREE_MB}"
echo "[train-opt] TRAIN_SERIAL_GPU_GUARD_TIMEOUT_SEC=${TRAIN_SERIAL_GPU_GUARD_TIMEOUT_SEC}"
echo "[train-opt] TRAIN_S2_BATCH_SIZE=${TRAIN_S2_BATCH_SIZE}"
echo "[train-opt] TRAIN_S2_MAX_EPOCHS=${TRAIN_S2_MAX_EPOCHS}"
echo "[train-opt] S2_FIND_UNUSED_PARAMETERS=${S2_FIND_UNUSED_PARAMETERS}"

port_listening() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq ":${port}$"
    return $?
  fi
  return 1
}

kill_port_pids() {
  local port="$1"
  if [ "${FORCE_KILL_PORTS}" != "1" ]; then
    return 0
  fi
  if ! command -v ss >/dev/null 2>&1; then
    return 0
  fi
  local pids
  pids=$(ss -ltnp 2>/dev/null | awk -v p=":${port}" '$4 ~ p {print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)
  if [ -n "$pids" ]; then
    echo ">>> 发现占用端口 ${port} 的进程，正在关闭..."
    for pid in $pids; do
      kill "$pid" 2>/dev/null || true
    done
    # 模型进程退出可能需要几秒，避免 1 秒后误判“端口仍占用”。
    local wait_round
    for wait_round in 1 2 3 4 5 6; do
      if ! port_listening "$port"; then
        break
      fi
      sleep 1
    done

    if port_listening "$port"; then
      local force_pids
      force_pids=$(ss -ltnp 2>/dev/null | awk -v p=":${port}" '$4 ~ p {print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)
      if [ -n "$force_pids" ]; then
        echo ">>> 端口 ${port} 仍被占用，升级强制关闭..."
        for pid in $force_pids; do
          kill -9 "$pid" 2>/dev/null || true
        done
        sleep 1
      fi
    fi
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
  CUDA_VISIBLE_DEVICES="${READALONG_PROCESS_CUDA_VISIBLE_DEVICES}" "$PYTHON_BIN" -m uvicorn modules.speaker_game.readalong_api:app --host "$READALONG_HOST" --port "$READALONG_PORT" --log-level info >> "$LOG_READALONG" 2>&1 &
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
  CUDA_VISIBLE_DEVICES="${READALONG_PROCESS_CUDA_VISIBLE_DEVICES}" "$PYTHON_BIN" -m uvicorn modules.speaker_game.readalong_api:app --host "$READALONG_HOST" --port "$READALONG_PORT" --log-level info
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
  CUDA_VISIBLE_DEVICES="${WX_PROCESS_CUDA_VISIBLE_DEVICES}" "$PYTHON_BIN" -u modules/tts_backend/wx_api.py -a "$WX_HOST" -p "$WX_PORT" 2>&1 | tee -a "$LOG_WX"
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
  CUDA_VISIBLE_DEVICES="${WX_PROCESS_CUDA_VISIBLE_DEVICES}" "$PYTHON_BIN" -u modules/tts_backend/wx_api.py -a "$WX_HOST" -p "$WX_PORT" >> "$LOG_WX" 2>&1 &
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
