#!/usr/bin/env bash
# Keep console output live, disk usage bounded, and the original command's status.
set -euo pipefail
log="$1"
shift
mkdir -p "$(dirname "$log")"
: > "$log.warnings"
# Shell redirection works with native Windows pipes where /dev/stderr may not.
# Keep consuming at the warning limit to avoid SIGPIPE in successful commands.
"$@" 2>&1 | {
  export LC_ALL=C
  bytes=0
  truncated=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    printf '%s\n' "$line" >&2
    printf '%s\n' "$line"
    case "$line" in
      *"warning: "*".profraw: invalid instrumentation profile data"*)
        length=$((${#line} + 1))
        if (( bytes + length <= 65536 )); then
          printf '%s\n' "$line" >> "$log.warnings"
          bytes=$((bytes + length))
        elif (( truncated == 0 )); then
          printf '%s\n' 'Profile warning list truncated at 65536 bytes' >> "$log.warnings"
          truncated=1
        fi
        ;;
    esac
  done
} | tail -c 2097152 > "$log"
