#!/usr/bin/env bash

set -euo pipefail

CAMPUS_USER="${CAMPUS_USER:-2024090058}"
CAMPUS_PASS="${CAMPUS_PASS:-Zkjzkj31815}"
CHECK_URL="${CHECK_URL:-https://www.baidu.com}"
CAPTIVE_PROBE_URL="${CAPTIVE_PROBE_URL:-http://connect.rom.miui.com/generate_204}"
CAMPUS_PORTAL_LOGIN_URL="${CAMPUS_PORTAL_LOGIN_URL:-}"

trim() {
  local s
  s="${1:-}"
  s="${s#${s%%[![:space:]]*}}"
  s="${s%${s##*[![:space:]]}}"
  printf '%s' "$s"
}

is_online() {
  curl --noproxy '*' -sS -m 5 "$CHECK_URL" >/dev/null 2>&1
}

extract_location_from_headers() {
  sed -n 's/^[Ll]ocation:[[:space:]]*//p' | tr -d '\r' | head -n 1
}

portal_base_from_url() {
  local u
  u="$(trim "${1:-}")"
  if [[ -z "$u" ]]; then
    return 0
  fi
  printf '%s' "$u" | sed -E 's#^(https?://[^/]+).*#\1#'
}

try_login_request() {
  local url="$1"
  local payload="$2"
  local name="$3"
  local resp=""

  if [[ -z "$url" ]]; then
    return 1
  fi

  echo "[campus_login] 尝试 $name -> $url"
  resp="$(curl --noproxy '*' -sS -m 12 -A 'Mozilla/5.0' \
    -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
    --data "$payload" "$url" || true)"

  if printf '%s' "$resp" | tr '[:upper:]' '[:lower:]' | grep -Eq 'success|ok|online|already|认证成功|已在线|login_ok'; then
    echo "[campus_login] $name 返回成功信号"
    return 0
  fi

  # 部分校园网接口在返回 JSON 时仍可通过 code=0 判断
  if printf '%s' "$resp" | tr -d ' ' | grep -Eq '"code":0|"result":"success"|"ret_code":0'; then
    echo "[campus_login] $name 返回成功码"
    return 0
  fi

  echo "[campus_login] $name 未确认成功，响应片段: $(printf '%s' "$resp" | head -c 160)"
  return 1
}

main() {
  if is_online; then
    echo "[campus_login] 当前网络已可用，无需认证。"
    exit 0
  fi

  local redirect_url=""
  local portal_base=""
  local header_dump=""

  header_dump="$(curl --noproxy '*' -sSI -m 8 "$CAPTIVE_PROBE_URL" || true)"
  redirect_url="$(printf '%s\n' "$header_dump" | extract_location_from_headers)"
  portal_base="$(portal_base_from_url "$redirect_url")"

  if [[ -n "${CAMPUS_PORTAL_LOGIN_URL}" ]]; then
    portal_base="$(portal_base_from_url "$CAMPUS_PORTAL_LOGIN_URL")"
  fi

  if [[ -z "$portal_base" ]]; then
    portal_base="http://172.16.253.3"
  fi

  local eportal_url="${CAMPUS_PORTAL_LOGIN_URL:-$portal_base/eportal/InterFace.do?method=login}"
  local eportal_payload="userId=${CAMPUS_USER}&password=${CAMPUS_PASS}&service=&queryString=&operatorPwd=&operatorUserId=&validcode=&passwordEncrypt=false"

  local srun_url="$portal_base/cgi-bin/srun_portal"
  local srun_payload="action=login&username=${CAMPUS_USER}&password=${CAMPUS_PASS}&ac_id=1&ip=&chksum=&info=&n=200&type=1&os=Linux&name=Linux&double_stack=0"

  local drcom_url="$portal_base/drcom/login"
  local drcom_payload="callback=dr1003&DDDDD=${CAMPUS_USER}&upass=${CAMPUS_PASS}&0MKKey=123456"

  if try_login_request "$eportal_url" "$eportal_payload" "eportal" || \
     try_login_request "$srun_url" "$srun_payload" "srun" || \
     try_login_request "$drcom_url" "$drcom_payload" "drcom"; then
    if is_online; then
      echo "[campus_login] 校园网登录成功，外网已连通。"
      exit 0
    fi
  fi

  echo "[campus_login] 未能确认登录成功。你可以手动指定登录地址后重试："
  echo "  CAMPUS_PORTAL_LOGIN_URL='http://<portal>/eportal/InterFace.do?method=login' bash tools/campus_net_login.sh"
  exit 1
}

main "$@"
