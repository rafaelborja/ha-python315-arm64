#!/bin/sh
# Make the s6 run script start Core on Python 3.15, keeping 3.14 as a fallback. Switches come from the container
# environment or, on a Supervisor-managed install (where the environment cannot be changed), from
# /config/ha-py315.conf, one KEY=value per line; only these keys are read, the file is never sourced:
#   HA_PYTHON=3.14    start the original interpreter, unchanged command
#   HA_LAZY=1         PEP 810 lazy imports on (-X lazy_imports=all + the exclusion filter). Default 0.
#   HA_PY_FLAGS=...   extra interpreter flags for 3.15
# The exclusion list itself is edited in /config/ha-lazy-filter.json (see ha_lazy_hook.py). Restart Core to apply.
set -e
f=/etc/services.d/home-assistant/run
grep -q '^exec python3 -P -m homeassistant --config /config$' "$f"
cat > /tmp/py315.snippet <<'EOF'
HA_PYTHON="${HA_PYTHON:-3.15}"; HA_LAZY="${HA_LAZY:-0}"; HA_PY_FLAGS="${HA_PY_FLAGS:-}"
if [[ -f /config/ha-py315.conf ]]; then
  while IFS='=' read -r key value || [[ -n "${key}" ]]; do
    value="${value%$'\r'}"; value="${value#\"}"; value="${value%\"}"
    case "${key}" in HA_PYTHON|HA_LAZY|HA_PY_FLAGS) printf -v "${key}" '%s' "${value}" ;; esac
  done < /config/ha-py315.conf
fi
if [[ "${HA_PYTHON}" != "3.14" ]]; then
  # HA installs runtime requirements with `python -m uv pip install` and UV_SYSTEM_PYTHON; without UV_PYTHON, uv
  # would pick python3 (3.14) from PATH and install into the wrong interpreter.
  export UV_PYTHON=/usr/local/bin/python3.15
  py_flags=()
  if [[ "${HA_LAZY}" == "1" ]]; then py_flags+=(-X lazy_imports=all); fi
  bashio::log.info "Starting Core on Python 3.15 (lazy imports: ${HA_LAZY}, flags: ${HA_PY_FLAGS:-none})"
  # shellcheck disable=SC2086
  exec python3.15 "${py_flags[@]}" ${HA_PY_FLAGS} -P -m homeassistant --config /config
fi
bashio::log.info "Starting Core on Python 3.14 (HA_PYTHON=3.14)"
EOF
awk 'FNR == NR { snippet = snippet $0 "\n"; next }
     /^exec python3 -P -m homeassistant --config \/config$/ { printf "%s", snippet }
     { print }' /tmp/py315.snippet "$f" > /tmp/run.new
cat /tmp/run.new > "$f"; rm /tmp/run.new /tmp/py315.snippet
bash -n "$f"
grep -n "python3" "$f"
