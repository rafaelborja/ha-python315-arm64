#!/bin/sh
# Make the s6 run script start Core on Python 3.15 (PEP 810 lazy imports on by default), keeping 3.14 as fallback:
#   HA_PYTHON=3.14      -> original interpreter, unchanged command
#   HA_PY_FLAGS=""      -> 3.15 without lazy imports
set -e
f=/etc/services.d/home-assistant/run
grep -q '^exec python3 -P -m homeassistant --config /config' "$f"
awk '
/^exec python3 -P -m homeassistant --config \/config/ {
  print "if [[ \"${HA_PYTHON:-3.15}\" == \"3.15\" ]]; then"
  print "  exec python3.15 ${HA_PY_FLAGS--X lazy_imports=all} -P -m homeassistant --config /config"
  print "fi"
}
{ print }' "$f" > /tmp/run.new
cat /tmp/run.new > "$f"; rm /tmp/run.new
grep -n "python3" "$f"
