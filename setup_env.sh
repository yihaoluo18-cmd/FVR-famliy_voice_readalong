#!/usr/bin/env bash
set -euo pipefail

# 根目录一键环境初始化入口（实际逻辑在 env/setup_env.sh）
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$PROJECT_ROOT/env/setup_env.sh" "$@"
