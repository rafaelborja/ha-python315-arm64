#!/bin/sh
# Builds a cp315 wheel for every "name==version" line of $1 into $2/wh, one package at a time, never stopping on a
# failure. Downloads a ready wheel when PyPI has one (PIP_PREFER_BINARY), compiles the sdist otherwise.
# WITH_DEPS=1 also builds each package's dependencies (constrained by $CONSTRAINTS when set): used for the test list.
# Writes $2/status.tsv (OK|FAIL <tab> package <tab> seconds) and $2/logs/<name>.log for failures.
LIST=$1; OUT=$2; mkdir -p "$OUT/wh" "$OUT/logs"; : > "$OUT/status.tsv"
DEPS=--no-deps; [ "${WITH_DEPS:-0}" = 1 ] && DEPS=
CONS=; [ -n "${CONSTRAINTS:-}" ] && CONS="-c $CONSTRAINTS"
while IFS= read -r p || [ -n "$p" ]; do
  [ -z "$p" ] && continue
  n=${p%%==*}; t=$(date +%s)
  # shellcheck disable=SC2086
  if timeout 45m pip wheel $DEPS $CONS -w "$OUT/wh" "$p" > "$OUT/logs/$n.log" 2>&1; then
    s=OK; rm -f "$OUT/logs/$n.log"
  else
    s=FAIL
  fi
  printf '%s\t%s\t%s\n' "$s" "$p" "$(( $(date +%s) - t ))" | tee -a "$OUT/status.tsv"
done < "$LIST"
echo "done: $(grep -c '^OK' "$OUT/status.tsv") ok, $(grep -c '^FAIL' "$OUT/status.tsv") failed"
