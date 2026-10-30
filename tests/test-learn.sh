#!/usr/bin/env bash
# Checks `lcu learn` on a temporary copy of LEARNINGS.md (the real file is not touched).
# Expected: 12 "ok" lines and exit 0.
set -u
here="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
export LCU_LEARN_LOG="$tmp/LEARNINGS.md"
L=("$here/lcu" learn)
fails=0
ok()  { echo "ok   $1"; }
bad() { echo "FAIL $1"; fails=$((fails+1)); }

cp "$here/LEARNINGS.md" "$LCU_LEARN_LOG"
"${L[@]}" check >/dev/null && ok "real log passes check" || bad "real log passes check"

"${L[@]}" add --kind new --title "Probe lesson" --what "w" --do "d" --evidence "e" >/dev/null \
  && grep -q '^### .* · new · Probe lesson$' "$LCU_LEARN_LOG" && grep -q '^- Desktop: ' "$LCU_LEARN_LOG" && grep -q '^- Seen on: ' "$LCU_LEARN_LOG" \
  && ok "add appends a stamped entry" || bad "add appends a stamped entry"

"${L[@]}" add --kind new --title "probe LESSON" --what w --do d --evidence e >/dev/null 2>&1 \
  && bad "duplicate title rejected" || ok "duplicate title rejected"

"${L[@]}" add --kind better --title "Leaky" --what "saw /home/alice/x" --do d --evidence e >/dev/null 2>&1 \
  && bad "home path rejected" || ok "home path rejected"

"${L[@]}" add --kind better --title "Leaky2" --what w --do d --evidence "token ghp_abcdefghijklmnop" >/dev/null 2>&1 \
  && bad "token rejected" || ok "token rejected"

"${L[@]}" add --kind app --title "No app" --what w --do d --evidence e >/dev/null 2>&1 \
  && bad "app kind needs --app" || ok "app kind needs --app"

printf '\n### 2026-01-01 · new · Hand edit without fields\n- Status: active\n' >> "$LCU_LEARN_LOG"
"${L[@]}" check >/dev/null && bad "check catches missing fields" || ok "check catches missing fields"

"${L[@]}" add --local --kind app --app ProbeApp --title "Local probe" --what "w at /home/alice" --do d --evidence e >/dev/null \
  && grep -q 'Local probe' "$tmp/LEARNINGS.local.md" && ! grep -q 'Local probe' "$LCU_LEARN_LOG" \
  && ok "--local writes only the local file (no public privacy rule)" || bad "--local writes only the local file (no public privacy rule)"

"${L[@]}" add --kind new --title "local PROBE" --what w --do d --evidence e >/dev/null 2>&1 \
  && bad "duplicate across shared and local rejected" || ok "duplicate across shared and local rejected"

"${L[@]}" list --app probeapp | grep -q 'Local probe' && ok "list filters by app and reads the local file" || bad "list filters by app and reads the local file"


"${L[@]}" add --kind new --desktop gnome --title "Gnome only probe" --what w --do d --evidence e >/dev/null \
  && "${L[@]}" list --desktop kde | grep -q 'Gnome only probe' && bad "list hides other desktops' entries" || ok "list hides other desktops' entries"
"${L[@]}" list --desktop any | grep -q 'Gnome only probe' && ok "list --desktop any shows every entry" || bad "list --desktop any shows every entry"
[ "$fails" -eq 0 ]
