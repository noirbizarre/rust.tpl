#!/usr/bin/env bash
# `.github/workflows/ci.yaml`'s test matrix and `.github/codecov.yml` agree on
# three things by hand: the set of OS flags each leg uploads under, and the
# count of legs both `after_n_builds` entries wait for before Codecov posts.
# Neither file is Jinja — no answer reaches either — so no render-time check
# ever sees a mismatch. Adding a fourth leg (or renaming a flag) in one file
# without the other passes `actionlint`, `git tpl lint`, and CI itself; the
# only symptom is Codecov silently never posting, which looks like Codecov
# being slow. This script is the check that would otherwise not exist.
#
# Run against a rendered project's root by `tests/full.toml`'s [commands].
set -euo pipefail

ci=".github/workflows/ci.yaml"
codecov=".github/codecov.yml"

matrix_flags=$(yq '.jobs.test.strategy.matrix.os[].flag' "$ci" | sort -u)
matrix_count=$(echo "$matrix_flags" | grep -c .)
codecov_flags=$(yq '.flags | keys | .[]' "$codecov" | sort -u)

if [ "$matrix_flags" != "$codecov_flags" ]; then
  echo "$ci's matrix flags and $codecov's [flags] disagree:" >&2
  diff <(echo "$matrix_flags") <(echo "$codecov_flags") >&2
  exit 1
fi

# Both occurrences (notify + comment) must equal the leg count above — a
# fourth leg with a correctly-added flag but a stale count still leaves
# Codecov waiting on one build that never reports back.
notify_n=$(yq '.codecov.notify.after_n_builds' "$codecov")
comment_n=$(yq '.comment.after_n_builds' "$codecov")

if [ "$notify_n" != "$comment_n" ] || [ "$notify_n" != "$matrix_count" ]; then
  echo "$codecov's after_n_builds (notify: $notify_n, comment: $comment_n) does not match the matrix's $matrix_count leg(s)" >&2
  exit 1
fi
