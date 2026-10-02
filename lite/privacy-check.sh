#!/bin/bash
# HA Lite privacy gate: fail if any given file contains something that identifies a particular install or person.
# Usage: privacy-check.sh FILE|DIR ...   (directories are searched recursively; this script never checks itself)
#
# Two pattern sets, both extended regexes:
#  - generic ones below (private/CGNAT IPv4, MAC addresses, e-mail addresses, Windows and Git-Bash user paths,
#    host data paths, remote-access URLs, session links, key material, tokens, HA config internals);
#  - PRIVACY_PATTERNS from the environment (a repository secret, one regex per line): names, host names, integration
#    and custom-component names that must never appear. They are setup-revealing by themselves, so they live only in
#    the secret.
# PRIVACY_ALLOW (newline-separated literal words, e.g. the repository owner) is removed from every line before
# matching, so the public GitHub handle in URLs does not trip a pattern for the person's name.
# A hit prints file:line and the pattern's label or number, never the matching text: the log of a public repository's
# run is public too.
set -uo pipefail
self=$(realpath "$0")
generic=(
  'private IPv4|(^|[^0-9.])(10\.[0-9]{1,3}|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]{1,3}\.[0-9]{1,3}([^0-9]|$)'
  'CGNAT IPv4|(^|[^0-9.])100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}([^0-9]|$)'
  'MAC address|(^|[^0-9A-Fa-f:])([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}([^0-9A-Fa-f:]|$)'
  'e-mail|[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}'
  'Windows path|(^|[^A-Za-z])[A-Za-z]:\\\\(Users|Info|git)\\\\'
  'Git-Bash path|(^|[^A-Za-z0-9_./-])/[a-z]/(Users|Info)/'
  'HAOS host data path|/mnt/data/'
  'remote URL|[a-z0-9]{16,}\.ui\.nabu\.casa'
  'session link|claude\.ai/code/session_'
  'key material|BEGIN [A-Z ]*PRIVATE KEY|_ed25519([^_A-Za-z0-9]|$)'
  'token|gh[pousr]_[A-Za-z0-9]{30,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}'
  'HA config internals|custom_components/|\.storage/core\.'
)
# e-mail addresses that are fine: GitHub noreply
allow_email='@users\.noreply\.github\.com|noreply@'
files=()
for a in "$@"; do
  if [ -d "$a" ]; then while IFS= read -r -d '' f; do files+=("$f"); done < <(find "$a" -type f -print0)
  elif [ -f "$a" ]; then files+=("$a")
  else echo "privacy-check: $a does not exist"; exit 2; fi
done
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
sed_allow=()
while IFS= read -r w; do
  w="${w%$'\r'}"; [ -n "$w" ] || continue
  [[ "$w" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "privacy-check: PRIVACY_ALLOW entries must be plain words"; exit 2; }
  sed_allow+=(-e "s/$w//g")
done <<< "${PRIVACY_ALLOW:-}"
declare -A clean  # original path -> copy with the allowed words removed
i=0
for f in "${files[@]}"; do
  [ "$(realpath "$f")" = "$self" ] && continue
  i=$((i + 1)); clean[$f]="$tmp/$i"
  if [ ${#sed_allow[@]} -gt 0 ]; then sed "${sed_allow[@]}" "$f" > "$tmp/$i" 2>/dev/null || cp "$f" "$tmp/$i"; else cp "$f" "$tmp/$i"; fi
done
hits=0
check() {  # label, regex
  local f n
  for f in "${!clean[@]}"; do
    while IFS= read -r n; do
      [ -n "$n" ] || continue
      if [ "$1" = e-mail ] && ! sed -n "${n}p" "${clean[$f]}" | grep -E -o -- "$2" | grep -v -E -q -- "$allow_email"; then
        continue  # only allowed addresses on this line
      fi
      echo "::error file=$f,line=$n::privacy-check: $1"; hits=$((hits + 1))
    done < <(grep -n -E -I -- "$2" "${clean[$f]}" 2>/dev/null | cut -d: -f1)
  done
}
for p in "${generic[@]}"; do check "${p%%|*}" "${p#*|}"; done
if [ -n "${PRIVACY_PATTERNS:-}" ]; then
  i=0
  while IFS= read -r p; do
    p="${p%$'\r'}"; [ -n "$p" ] || continue; i=$((i + 1))
    check "secret pattern #$i" "$p"
  done <<< "$PRIVACY_PATTERNS"
  echo "privacy-check: ${#generic[@]} generic + $i secret patterns over ${#clean[@]} files"
else
  echo "::warning::privacy-check: PRIVACY_PATTERNS is not set; only the ${#generic[@]} generic patterns ran"
fi
[ "$hits" -eq 0 ] || { echo "privacy-check: $hits hit(s)"; exit 1; }
echo "privacy-check: clean"
