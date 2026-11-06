#!/usr/bin/env bash
# Keep console output live, disk usage bounded, and the original command's status.
set -euo pipefail
log="$1"
shift
mkdir -p "$(dirname "$log")"
# awk keeps consuming after the warning budget is exhausted, avoiding SIGPIPE
# failures in otherwise successful commands. Retain warnings separately from tails.
# ENVIRON avoids awk -v interpreting backslashes in Windows paths as escapes.
"$@" 2>&1 | tee /dev/stderr | CI_DIAGNOSTIC_WARNINGS="$log.warnings" LC_ALL=C awk '
  BEGIN { warnings = ENVIRON["CI_DIAGNOSTIC_WARNINGS"]; printf "" > warnings }
  /warning: .*\.profraw: invalid instrumentation profile data/ {
    if (bytes + length($0) + 1 <= 65536) {
      print > warnings
      bytes += length($0) + 1
    } else if (!truncated++) {
      print "Profile warning list truncated at 65536 bytes" > warnings
    }
  }
  { print }
' | tail -c 2097152 > "$log"
