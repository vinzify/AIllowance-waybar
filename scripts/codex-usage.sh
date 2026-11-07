#!/usr/bin/env bash
# Render the cached account report immediately; refresh in the background.
set -euo pipefail
umask 077
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cache_file="${CODEX_USAGE_CACHE_FILE:-${XDG_CACHE_HOME:-${HOME}/.cache}/aillowance/codex-account-usage.json}"

if [[ "${1:-}" == --refresh ]]; then
  exec "$script_dir/codex-usage-refresh.sh" --force
fi

cached_epoch=0
if [[ -r "$cache_file" ]]; then
  cached_epoch="$(jq -r '.fetchedAtEpoch // 0' "$cache_file" 2>/dev/null || printf '0')"
fi
[[ "$cached_epoch" =~ ^[0-9]+$ ]] || cached_epoch=0
if (( $(date +%s) - cached_epoch >= 300 )); then
  nohup "$script_dir/codex-usage-refresh.sh" >/dev/null 2>&1 </dev/null &
fi

if [[ -r "$cache_file" ]]; then
  exec python3 "$script_dir/codex-usage-render.py" <"$cache_file"
fi
exec python3 "$script_dir/codex-usage-render.py" <<<'{}'
