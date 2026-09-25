#!/bin/sh
# Builds a cp315 wheel for every "name==version" line of $1 into $2/wh, one package at a time, never stopping on a
# failure. Downloads a ready wheel when PyPI has one (PIP_PREFER_BINARY), compiles the sdist otherwise.
# WITH_DEPS=1 also builds each package's dependencies (constrained by $CONSTRAINTS when set): used for the test list.
# Writes $2/status.tsv (OK|FAIL <tab> package <tab> seconds) and $2/logs/<name>.log for failures.
# PREV_STATUS=<status.tsv of an earlier run>: packages that were OK there are not rebuilt (their wheels must already
# be in $2/wh); they are recorded as OK with 0 seconds.
LIST=$1; OUT=$2; mkdir -p "$OUT/wh" "$OUT/logs"; : > "$OUT/status.tsv"
DEPS=--no-deps; [ "${WITH_DEPS:-0}" = 1 ] && DEPS=
CONS=; [ -n "${CONSTRAINTS:-}" ] && CONS="-c $CONSTRAINTS"
[ -n "${PREV_STATUS:-}" ] && cut -f1,2 "$PREV_STATUS" > /tmp/prev.ok
# With dependencies, resolve the whole list ONCE: one version of every package (per-package resolution gave two
# versions of isort, pylint, librt...). Fall back to one package at a time only if that fails.
if [ "${WITH_DEPS:-0}" = 1 ]; then
  rm -f "$OUT"/wh/*  # never mix with wheels reused from an earlier run: they may carry other versions
  t=$(date +%s)
  # shellcheck disable=SC2086
  if timeout 90m pip wheel $CONS -w "$OUT/wh" -r "$LIST" > "$OUT/logs/_all.log" 2>&1; then
    rm -f "$OUT/logs/_all.log"
    grep -v '^$' "$LIST" | while IFS= read -r p; do printf 'OK\t%s\t%s\n' "$p" "$(( $(date +%s) - t ))"; done | tee "$OUT/status.tsv"
    echo "done: resolved and built the whole list at once"; exit 0
  fi
  echo "whole-list build failed (logs/_all.log); falling back to one package at a time"; rm -f "$OUT"/wh/*
fi
while IFS= read -r p || [ -n "$p" ]; do
  [ -z "$p" ] && continue
  n=${p%%==*}; t=$(date +%s)
  if [ -n "${PREV_STATUS:-}" ] && grep -q -F -x "$(printf 'OK\t%s' "$p")" /tmp/prev.ok 2>/dev/null; then
    printf 'OK\t%s\t0\n' "$p" >> "$OUT/status.tsv"; continue
  fi
  # shellcheck disable=SC2086
  if timeout 45m pip wheel $DEPS $CONS -w "$OUT/wh" "$p" > "$OUT/logs/$n.log" 2>&1; then
    s=OK; rm -f "$OUT/logs/$n.log"
  else
    s=FAIL
  fi
  printf '%s\t%s\t%s\n' "$s" "$p" "$(( $(date +%s) - t ))" | tee -a "$OUT/status.tsv"
done < "$LIST"
[ -n "${PREV_STATUS:-}" ] && echo "reused from the earlier run: $(grep -c "$(printf '\t0$')" "$OUT/status.tsv")"
echo "done: $(grep -c '^OK' "$OUT/status.tsv") ok, $(grep -c '^FAIL' "$OUT/status.tsv") failed"
