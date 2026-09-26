#!/bin/sh
# Make the s6 run script start Supervisor on Python 3.15, keeping 3.14 as a fallback. Switches come from the
# container environment or from /data/sup-py315.conf (HAOS: /mnt/data/supervisor/sup-py315.conf), one KEY=value per
# line; only these keys are read, the file is never sourced:
#   SUP_PYTHON=3.14   start the original interpreter, unchanged command
#   SUP_LAZY=1        PEP 810 lazy imports on (-X lazy_imports=all + the exclusion filter). Default 0.
#   SUP_PY_FLAGS=...  extra interpreter flags for 3.15
#   PYTHONMALLOC=...  allocator (the official run script defaults to mimalloc)
# The exclusion list is edited in /data/sup-lazy-filter.json (see ha_lazy_hook.py). Restart Supervisor to apply.
set -e
f=/etc/services.d/supervisor/run
grep -q '^exec python3 -m supervisor$' "$f"
cat > /tmp/py315.snippet <<'EOF'
SUP_PYTHON="${SUP_PYTHON:-3.15}"; SUP_LAZY="${SUP_LAZY:-0}"; SUP_PY_FLAGS="${SUP_PY_FLAGS:-}"
if [[ -f /data/sup-py315.conf ]]; then
  while IFS='=' read -r key value || [[ -n "${key}" ]]; do
    value="${value%$'\r'}"; value="${value#\"}"; value="${value%\"}"
    case "${key}" in SUP_PYTHON|SUP_LAZY|SUP_PY_FLAGS|PYTHONMALLOC) printf -v "${key}" '%s' "${value}" ;; esac
  done < /data/sup-py315.conf
  export PYTHONMALLOC
fi
if [[ "${SUP_PYTHON}" != "3.14" ]]; then
  py_flags=()
  if [[ "${SUP_LAZY}" == "1" ]]; then py_flags+=(-X lazy_imports=all); fi
  bashio::log.info "Starting Supervisor on Python 3.15 (lazy imports: ${SUP_LAZY}, flags: ${SUP_PY_FLAGS:-none}, allocator: ${PYTHONMALLOC})"
  # shellcheck disable=SC2086
  exec python3.15 "${py_flags[@]}" ${SUP_PY_FLAGS} -m supervisor
fi
bashio::log.info "Starting Supervisor on Python 3.14 (SUP_PYTHON=3.14, allocator: ${PYTHONMALLOC})"
EOF
awk 'FNR == NR { snippet = snippet $0 "\n"; next }
     /^exec python3 -m supervisor$/ { printf "%s", snippet }
     { print }' /tmp/py315.snippet "$f" > /tmp/run.new
cat /tmp/run.new > "$f"; rm /tmp/run.new /tmp/py315.snippet
bash -n "$f"
grep -n "python3" "$f"
