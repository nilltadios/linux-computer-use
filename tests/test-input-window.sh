#!/usr/bin/env bash
# `lcu input --window`: refusals send nothing, and accepted input reaches only the target.
# Usage: tests/test-input-window.sh [MONITOR] [OUTDIR]   (default: right-most monitor, a mktemp dir)
# KDE only for the covered-window and pointer cases (hit test). Exit 0 = all `ok`. Focus goes back at the end.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; L="$here/lcu"; PY=/usr/bin/python3
mon="${1:-$("$L" capture screens | jq -r 'max_by(.x).name')}"; out="${2:-$(mktemp -d)}"
read -r gx gy gw gh < <("$L" capture screens | jq -r --arg m "$mon" '.[]|select(.name==$m)|"\(.x|floor) \(.y|floor) \(.width|floor) \(.height|floor)"')
prev=$("$L" window active | jq -r '.[0].id // empty')
la="$out/a.jsonl"; lb="$out/b.jsonl"; : > "$la"; : > "$lb"
$PY "$here/tests/input_probe.py" "$la" 90 --windowed >/dev/null 2>&1 & pa=$!
$PY "$here/tests/input_probe.py" "$lb" 90 --windowed >/dev/null 2>&1 & pb=$!
cleanup() { kill $pa $pb 2>/dev/null; [[ -n $prev ]] && "$L" window activate "id:$prev" >/dev/null 2>&1; }
trap cleanup EXIT
A=pid:$pa; B=pid:$pb; fail=0
"$L" window wait-stable $A >/dev/null && "$L" window wait-stable $B >/dev/null || { echo "ABORT: probes did not appear"; exit 2; }
ax=$((gx+40)); ay=$((gy+60))
"$L" window move-to $A "$mon" >/dev/null; "$L" window move-to $B "$mon" >/dev/null
"$L" window geometry $A $ax $ay 700 450 >/dev/null
"$L" window geometry $B $((ax+450)) $((ay+150)) 400 250 >/dev/null
"$L" window keep-above $B >/dev/null
sleep 0.6
read -r ax ay aw ah < <("$L" window info $A | jq -r '.[0]|"\(.x|floor) \(.y|floor) \(.width|floor) \(.height|floor)"')
read -r bx by bw bh < <("$L" window info $B | jq -r '.[0]|"\(.x|floor) \(.y|floor) \(.width|floor) \(.height|floor)"')
# on A only / on B over A / on nothing of ours
ox=$((ax+100)); oy=$((ay+120)); cx=$((bx+100)); cy=$((by+120)); nx=$((bx+bw+60)); ny=$((by+bh+60))
presses() { jq -c 'select(.ev=="button-press" or .ev=="key-press")' "$1" | wc -l; }
ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
refused() { local name=$1; shift; local a0 b0 rc; a0=$(presses "$la"); b0=$(presses "$lb")
  "$L" input --window "$@" >"$out/last.out" 2>"$out/last.err"; rc=$?; sleep 0.4
  if [[ $rc == 2 && $(presses "$la") == "$a0" && $(presses "$lb") == "$b0" ]]; then ok "$name  [$(cut -c1-90 "$out/last.err")]"
  else bad "$name (exit $rc, a $a0->$(presses "$la"), b $b0->$(presses "$lb"), $(cat "$out/last.err"))"; fi; }
got() { jq -e --argjson w "$2" 'select(contains($w))' "$1" >/dev/null; }
refused "no such window"            class:org.lcu.NoSuchApp move $ox $oy click left
refused "ambiguous match"           class:org.lcu.InputProbe move $ox $oy click left
refused "point on a covering window" $A move $cx $cy click left
refused "point outside the window"  $A move $nx $ny click left
refused "bad later point: first click not sent" $A move $ox $oy click left move $cx $cy click left
refused "drag starting off the window" $A drag $cx $cy $ox $oy
"$L" window activate $B >/dev/null; sleep 0.3
"$L" input --window $A move $ox $oy click left key x; rc=$?; sleep 0.4
[[ $rc == 0 ]] && got "$la" '{"ev":"button-press","num":1}' && ok "click reaches the target from another focus" || bad "click reaches the target (exit $rc)"
got "$la" '{"ev":"key-press","keysym":"x"}' && ok "key reaches the target" || bad "key reaches the target"
[[ $(presses "$lb") == 0 ]] && ok "the other window got nothing" || bad "the other window got input"
"$L" window active | jq -e --argjson p "$pa" '.[0].pid==$p' >/dev/null && ok "target has focus afterwards" || bad "target has focus afterwards"
"$L" window activate $B >/dev/null; sleep 0.3
"$L" input --window $A type z; sleep 0.4
got "$la" '{"ev":"key-press","keysym":"z"}' && ok "keys only: focus moved first" || bad "keys only"
"$L" input --window $A type "move 99999 99999"; rc=$?; sleep 0.4
[[ $rc == 0 ]] && got "$la" '{"ev":"key-press","keysym":"m"}' && ok "typed words are not read as actions" || bad "typed words (exit $rc)"
"$L" input move $cx $cy
refused "click with no move, pointer on another window" $A click left
"$L" input move $ox $oy
a0=$(presses "$la"); "$L" input --window $A click left; rc=$?; sleep 0.4
[[ $rc == 0 && $(presses "$la") -gt $a0 ]] && ok "click with no move, pointer on the window" || bad "click with no move (exit $rc)"
echo "log: $out"; exit $fail
