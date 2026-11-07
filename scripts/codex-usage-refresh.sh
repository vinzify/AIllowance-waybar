#!/usr/bin/env bash
set -euo pipefail
umask 077

command -v jq >/dev/null 2>&1 || exit 1

cache_file="${CODEX_USAGE_CACHE_FILE:-${XDG_CACHE_HOME:-${HOME}/.cache}/aillowance/codex-account-usage.json}"
cache_dir="$(dirname "$cache_file")"
lock_file="${cache_file}.refresh.lock"

mkdir -p "$cache_dir"
chmod 700 "$cache_dir" 2>/dev/null || true

exec 9>"${lock_file}"
flock -n 9 || exit 0

# Limit failed refresh attempts to once per minute across bar instances.
if [[ "${1:-}" != --force && -e "${cache_file}.attempt" ]] &&
   (( $(date +%s) - $(stat -c %Y "${cache_file}.attempt") < 60 )); then
  exit 0
fi
touch "${cache_file}.attempt"

resolve_codex_bin() {
  if [[ -n "${CODEX_USAGE_CODEX_BIN:-}" && -x "${CODEX_USAGE_CODEX_BIN}" ]]; then
    printf '%s' "$CODEX_USAGE_CODEX_BIN"
    return
  fi

  if command -v codex >/dev/null 2>&1; then
    command -v codex
    return
  fi

  local candidates=()
  shopt -s nullglob
  candidates=("${HOME}"/.nvm/versions/node/*/bin/codex)
  shopt -u nullglob

  if (( ${#candidates[@]} > 0 )); then
    printf '%s\n' "${candidates[@]}" | sort -V | tail -n 1
  fi
}

codex_bin="$(resolve_codex_bin)"
[[ -n "$codex_bin" && -x "$codex_bin" ]] || exit 1
codex_bin_dir="$(dirname "$codex_bin")"

server_pid=''
server_in=''
server_out=''
tmp_file=''

cleanup() {
  if [[ -n "$server_in" ]]; then
    eval "exec ${server_in}>&-" 2>/dev/null || true
  fi
  if [[ -n "$server_out" ]]; then
    eval "exec ${server_out}<&-" 2>/dev/null || true
  fi
  if [[ -n "$server_pid" ]]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  if [[ -n "$tmp_file" && -e "$tmp_file" ]]; then
    rm -f -- "$tmp_file"
  fi
}
trap cleanup EXIT

coproc CODEX_ACCOUNT_SERVER {
  export PATH="${codex_bin_dir}:${PATH}"
  exec "$codex_bin" app-server --stdio 2>/dev/null
}
server_pid="$CODEX_ACCOUNT_SERVER_PID"
exec {server_out}<&"${CODEX_ACCOUNT_SERVER[0]}"
exec {server_in}>&"${CODEX_ACCOUNT_SERVER[1]}"

printf '%s\n' '{"method":"initialize","id":0,"params":{"clientInfo":{"name":"waybar_codex_usage","title":"Waybar Codex Usage","version":"0.1.0"}}}' >&"$server_in"
initialized=false
initialize_deadline=$((SECONDS + 8))
while (( SECONDS < initialize_deadline )); do
  if IFS= read -r -t 1 line <&"$server_out"; then
    if jq -e '.id == 0 and has("result")' <<<"$line" >/dev/null 2>&1; then
      initialized=true
      break
    fi
    if jq -e '.id == 0 and has("error")' <<<"$line" >/dev/null 2>&1; then
      exit 1
    fi
  elif ! kill -0 "$server_pid" 2>/dev/null; then
    break
  fi
done
[[ "$initialized" == true ]] || exit 1
printf '%s\n' '{"method":"initialized","params":{}}' >&"$server_in"
printf '%s\n' '{"method":"account/rateLimits/read","id":6}' >&"$server_in"
printf '%s\n' '{"method":"account/usage/read","id":7}' >&"$server_in"

rate_limits=''
account_usage=''
deadline=$((SECONDS + 12))

while (( SECONDS < deadline )) && [[ -z "$rate_limits" || -z "$account_usage" ]]; do
  if IFS= read -r -t 1 line <&"$server_out"; then
    response_id="$(jq -r '.id // empty' <<<"$line" 2>/dev/null || true)"
    case "$response_id" in
      6)
        rate_limits="$(jq -c '.result // null' <<<"$line" 2>/dev/null || printf 'null')"
        ;;
      7)
        account_usage="$(jq -c '.result // null' <<<"$line" 2>/dev/null || printf 'null')"
        ;;
    esac
  elif ! kill -0 "$server_pid" 2>/dev/null; then
    break
  fi
done

jq -e 'type == "object" and ((.rateLimits | type == "object") or (.rateLimitsByLimitId | type == "object"))' <<<"${rate_limits:-null}" >/dev/null 2>&1 || exit 1
if ! jq -e 'type == "object"' <<<"${account_usage:-null}" >/dev/null 2>&1; then
  account_usage='null'
fi

fetched_at_epoch="$(date +%s)"
fetched_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
tmp_file="$(mktemp "${cache_file}.tmp.XXXXXX")"

jq -nc \
  --argjson schemaVersion 1 \
  --argjson fetchedAtEpoch "$fetched_at_epoch" \
  --arg fetchedAt "$fetched_at" \
  --arg source 'app-server' \
  --argjson rateLimits "$rate_limits" \
  --argjson usage "$account_usage" \
  '{
    schemaVersion:$schemaVersion,
    fetchedAtEpoch:$fetchedAtEpoch,
    fetchedAt:$fetchedAt,
    source:$source,
    rateLimits:$rateLimits,
    usage:$usage
  }' >"$tmp_file"

chmod 600 "$tmp_file"
mv -f -- "$tmp_file" "$cache_file"
tmp_file=''
