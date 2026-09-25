#!/bin/bash
# Start the image the way HAOS does (s6 /init, the patched run script) with an empty config + default_config and
# report whether Core comes up, its errors, and the Core process RSS 60 s after "initialized".
# Usage: ha-start-check.sh IMAGE LABEL OUTDIR [KEY=VALUE for /config/ha-py315.conf ...]
set -uo pipefail
IMG=$1; LABEL=$2; OUT=$(realpath -m "$3"); shift 3; mkdir -p "$OUT"
cfg=$(mktemp -d)
cat > "$cfg/configuration.yaml" <<'EOF'
default_config:
homeassistant:
  name: ci
  latitude: 45.5
  longitude: -73.6
  elevation: 30
  time_zone: America/Toronto
  unit_system: metric
  country: CA
logger:
  default: warning
  logs:
    homeassistant.bootstrap: info
EOF
printf '%s\n' "$@" > "$cfg/ha-py315.conf"
name="hs-$LABEL"
docker run -d --name "$name" -v "$cfg:/config" -e TZ=America/Toronto "$IMG" > /dev/null
up=""
for _ in $(seq 1 100); do
  sleep 3
  docker logs "$name" 2>&1 | grep -q "Home Assistant initialized in" && { up=yes; break; }
  [ "$(docker inspect -f '{{.State.Running}}' "$name")" = true ] || break
done
[ -n "$up" ] && sleep 60
rss=$(docker exec "$name" sh -c 'for p in /proc/[0-9]*; do grep -q "homeassistant" $p/cmdline 2>/dev/null && awk "/VmRSS/{print \$2}" $p/status; done' 2>/dev/null | sort -n | tail -1)
docker logs "$name" > "$OUT/$LABEL.log" 2>&1
docker rm -f "$name" > /dev/null
L="$OUT/$LABEL.log"
c() { grep -c -E "$1" "$L"; }
printf '| %s | %s | %s | %s | %s | %s | %s | %s |\n' "$LABEL" "${up:-NO}" "$(grep -o 'Starting Core on Python [0-9.]* ([^)]*)' "$L" | head -1)" \
  "$(( ${rss:-0} / 1024 ))" "$(c ' ERROR ')" "$(c 'Traceback')" "$(c 'Detected blocking call')" \
  "$(c 'ImportError|NameError|AttributeError|circular import|ImportCycleError|Error setting up entry|Setup failed')" \
  | tee -a "$OUT/summary.md"
rm -rf "$cfg" 2>/dev/null || sudo rm -rf "$cfg"
[ -n "$up" ]
