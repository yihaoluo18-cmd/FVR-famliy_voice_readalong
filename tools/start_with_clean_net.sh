#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 清理代理污染，避免本机回环/局域网请求被错误代理。
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY no_proxy NO_PROXY
export NO_PROXY='*'

if [[ "${SKIP_CAMPUS_LOGIN:-0}" != "1" ]]; then
  if ! bash "$SCRIPT_DIR/campus_net_login.sh"; then
    echo "[start_with_clean_net] 校园网自动认证未确认成功，可先手动联网后再启动服务。"
  fi
fi

cd "$PROJECT_ROOT"
exec bash "$PROJECT_ROOT/start_wx_api.sh" "$@"
