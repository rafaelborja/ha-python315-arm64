#!/bin/bash
# One shard of HA's test suite on Python 3.15, eager and with lazy imports, then a rerun of the files holding
# candidate regressions in both modes (flaky tests vs real regressions).
# Usage: run-tests.sh TEST_IMAGE SHARD_FILE OUTDIR    (run from the directory holding the core/ checkout)
set -uo pipefail
IMG=$1; SHARD=$2; OUT=$(realpath -m "$3"); CORE=$PWD/core; mkdir -p "$OUT"
common=(--rm --memory 12g -w /usr/src/homeassistant -e PYTHONDONTWRITEBYTECODE=1 --entrypoint python3.15
        -v "$CORE/tests:/usr/src/homeassistant/tests" -v "$CORE/script:/usr/src/homeassistant/script"
        -v "$CORE/pylint:/usr/src/homeassistant/pylint" -v "$CORE/pyproject.toml:/usr/src/homeassistant/pyproject.toml"
        -v "$OUT:/r")
lazy_env=(-e PYTHON_LAZY_IMPORTS=all -e LAZY_FILTER=/etc/ha-lazy-filter-test.json -e LAZY_MOCK_FIX=1)

pt() {  # pt <tag> <paths file> [docker env args...]
  local tag=$1 list=$2; shift 2
  mapfile -t paths < "$list"
  [ ${#paths[@]} -eq 0 ] && return 0
  timeout 170m docker run "${common[@]}" "$@" "$IMG" -m pytest -p no:cacheprovider -n 4 --dist loadfile \
    --timeout 120 --continue-on-collection-errors -o junit_family=xunit1 -q -rfE --junitxml="/r/$tag.xml" "${paths[@]}" > "$OUT/$tag.log" 2>&1
  echo "$tag: $(tail -1 "$OUT/$tag.log")"
}

pt eager "$SHARD"
pt lazy "$SHARD" "${lazy_env[@]}"
# A session that never started (e.g. conftest import error) writes no junit: that is a failure, not "0 regressions".
for tag in eager lazy; do
  [ -s "$OUT/$tag.xml" ] || { echo "::error::$tag session produced no results:"; tail -5 "$OUT/$tag.log"; exit 1; }
done
python3 scripts/compare_tests.py "$OUT" "$CORE"
pt eager-rerun "$OUT/rerun_files.txt"
pt lazy-rerun "$OUT/rerun_files.txt" "${lazy_env[@]}"
python3 scripts/compare_tests.py "$OUT" "$CORE" --final
