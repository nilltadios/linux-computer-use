#!/usr/bin/env bash
# Exercise every `lcu window` action the desktop supports on a throwaway probe window (no input sent).
# Usage: tests/test-window.sh [MONITOR]   Expected: "ok" for every action, exit 0.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; L="$here/lcu"; PY=/usr/bin/python3
desk=$("$L" detect | jq -r .desktop)
mon="${1:-$("$L" capture screens | jq -r 'max_by(.x).name')}"
other=$("$L" capture screens | jq -r --arg m "$mon" '[.[]|select(.name!=$m)][0].name // empty')
M=class:com.claude.InputProbe; fail=0
$PY "$here/tests/input_probe.py" "$(mktemp)" 40 --windowed 2>/dev/null & p=$!
"$L" window wait-stable $M >/dev/null || { echo "FAIL probe window did not appear"; exit 2; }
st() {  # label jq-condition
    sleep 0.5; local j; j=$("$L" window info $M | jq -c '.[0]|{minimized,maximized,fullscreen,keepAbove,sticky,active,output,x,y,width,height}')
    if jq -e "$2" <<<"$j" >/dev/null; then echo "ok   $1: $j"; else echo "FAIL $1: $j (want $2)"; fail=1; fi
}
if [[ -n $other ]]; then "$L" window move-to $M "$other" >/dev/null; st "move-to $other" ".output==\"$other\""; fi
"$L" window move-to $M "$mon" >/dev/null; st "move-to $mon" ".output==\"$mon\""
if [[ $desk != cosmic ]]; then
    read -r gx gy < <("$L" capture screens | jq -r --arg m "$mon" '.[]|select(.name==$m)|"\(.x|floor) \(.y|floor)"')
    "$L" window geometry $M $((gx+150)) $((gy+150)) 500 300 >/dev/null; st geometry ".x==$((gx+150)) and .y==$((gy+150)) and .width==500"
    "$L" window keep-above $M >/dev/null; st keep-above '.keepAbove'
    "$L" window no-keep-above $M >/dev/null; st no-keep-above '.keepAbove|not'
fi
"$L" window maximize $M >/dev/null; st maximize '.maximized'
"$L" window unmaximize $M >/dev/null; st unmaximize '.maximized|not'
"$L" window fullscreen $M >/dev/null; st fullscreen '.fullscreen'
"$L" window unfullscreen $M >/dev/null; st unfullscreen '.fullscreen|not'
if [[ $desk == cosmic ]]; then
    "$L" window sticky $M >/dev/null; st sticky '.sticky'
    "$L" window unsticky $M >/dev/null; st unsticky '.sticky|not'
fi
"$L" window minimize $M >/dev/null; st minimize '.minimized'
"$L" window activate $M >/dev/null; st activate '.minimized==false and .active'
"$L" window close $M >/dev/null; sleep 0.8
if kill -0 $p 2>/dev/null; then echo "FAIL close: probe still running"; kill $p; fail=1; else echo "ok   close: probe exited"; fi
j=$("$L" window launch --on "$mon" --maximize -- $PY "$here/tests/input_probe.py" "$(mktemp)" 20 --windowed 2>/dev/null | jq -c '.[0]|{output,maximized,class}')
if jq -e --arg m "$mon" '.output==$m and .maximized' <<<"$j" >/dev/null; then echo "ok   launch --on $mon --maximize: $j"; else echo "FAIL launch: $j"; fail=1; fi
"$L" window close $M >/dev/null 2>&1
exit $fail
