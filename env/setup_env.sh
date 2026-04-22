#!/usr/bin/env bash
# 在新主机上从 env/requirements.txt（pip freeze）重建与本机一致的 Python 虚拟环境（不随包分发 venv）。
# 依赖：建议 Python 3.10.x（与当前开发环境一致）；Linux 下 GPU 可选见下方环境变量。
#
# 用法：
#   chmod +x setup_env.sh
#   ./setup_env.sh
#   ./setup_env.sh --recreate          # 删除已有 venv 后重建
#
# GPU（推荐：先从官方索引预装 CUDA 版 PyTorch，再装全量 lock；需 Linux + 对应 NVIDIA 驱动）：
#   CUDA_PIP=1 ./setup_env.sh
# 仅 CPU / 无 NVIDIA：不要设 CUDA_PIP，将安装 PyPI 上的 CPU 版 torch。

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

RECREATE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --recreate) RECREATE=1 ;;
    -h|--help)
      sed -n '1,25p' "$0"
      exit 0
      ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
  shift
done

py_ge_310() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
}

# Windows/Git Bash：python3 常为 Microsoft Store 占位符；PATH 里可能先有 python 3.8（conda）。
# 仅当可执行且版本 >= 3.10 时才采纳；否则尝试「py -3」解析出的真实解释器路径。
pick_python() {
  local c
  for c in python3.10 python3.11 python3.12 python3.13 python3; do
    if command -v "$c" >/dev/null 2>&1 && py_ge_310 "$c"; then
      echo "$c"
      return 0
    fi
  done
  if command -v python >/dev/null 2>&1 && py_ge_310 python; then
    echo "python"
    return 0
  fi
  if command -v py >/dev/null 2>&1; then
    # 优先较新的 3.11/3.12（wheel 更全），避免默认的 py -3 指向 3.13 时部分包需本地编译。
    for pv in 3.11 3.12 3.10 3; do
      if py "-$pv" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        py "-$pv" -c 'import sys; print(sys.executable)'
        return 0
      fi
    done
  fi
  echo ""
  return 1
}

PYTHON_CMD="$(pick_python)"
if [[ -z "$PYTHON_CMD" ]]; then
  echo "错误：未找到 Python 3.10+（已尝试 python3.x、python、Windows 的 py -3）。请安装官方 Python 3.10+ 并勾选「Add to PATH」。" >&2
  exit 1
fi

LOCK_FILE="$PROJECT_ROOT/env/requirements.txt"
if [[ ! -f "$LOCK_FILE" ]]; then
  echo "错误：未找到 env/requirements.txt（请在发布前用运行环境执行 pip freeze > env/requirements.txt）。" >&2
  exit 1
fi

VENV_DIR="$PROJECT_ROOT/venv"
if [[ "$RECREATE" -eq 1 ]] && [[ -d "$VENV_DIR" ]]; then
  echo "移除已有虚拟环境: $VENV_DIR"
  rm -rf "$VENV_DIR"
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "创建虚拟环境: $VENV_DIR ($PYTHON_CMD)"
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

if [[ -f "$VENV_DIR/Scripts/python.exe" ]]; then
  PIP="$VENV_DIR/Scripts/pip"
  PY="$VENV_DIR/Scripts/python"
else
  PIP="$VENV_DIR/bin/pip"
  PY="$VENV_DIR/bin/python"
fi

# torch 2.x 要求 setuptools<82；与 pip 升级一并约束，避免反复升降级。
"$PIP" install -U pip wheel "setuptools<82"

# 先装 CUDA wheel 可避免仅从 PyPI 拉到 CPU 版 torch（仅 Linux 场景）。
if [[ "${CUDA_PIP:-}" == "1" ]]; then
  echo "预装 PyTorch（CUDA 12.4 官方 wheel）…"
  # 仅将 torch/torchaudio/triton 指向 PyTorch 官方 cu124 索引，其它依赖仍从默认 PyPI 镜像解析，避免网络不通导致卡死。
  "$PIP" install torch==2.6.0 torchaudio==2.6.0 triton==3.2.0 \
    --index-url https://download.pytorch.org/whl/cu124 \
    --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple
fi

echo "安装依赖（来自 env/requirements.txt）…"
"$PIP" install -r "$LOCK_FILE"

echo
echo "完成。Python: $($PY -c 'import sys; print(sys.executable)')"
echo "启动服务请使用: ./start_wx_api.sh"
