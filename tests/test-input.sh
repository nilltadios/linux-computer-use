#!/usr/bin/env bash
# End-to-end check of `lcu input` against tests/input_probe.py on one monitor, on any desktop.
# Usage: tests/test-input.sh [MONITOR] [OUTDIR]   (default: right-most monitor, a mktemp dir)
# Exit 0 = every expected event was seen by the probe window. Exit 2 = aborted before input.
# Safety: no click or key is sent until the probe is the active, full-screen window on
# MONITOR AND has logged pointer motion over itself.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; L="$here/lcu"; PY=/usr/bin/python3
mon="${1:-$("$L" capture screens | jq -r 'max_by(.x).name')}"; out="${2:-$(mktemp -d)}"; log="$out/probe.jsonl"; : > "$log"
desk=$("$L" detect | jq -r .desktop); M=class:com.claude.InputProbe
read -r gx gy gw gh < <("$L" capture screens | jq -r --arg m "$mon" '.[]|select(.name==$m)|"\(.x) \(.y) \(.width) \(.height)"')
cx=$(( ${gx%.*} + ${gw%.*}/2 )); cy=$(( ${gy%.*} + ${gh%.*}/2 ))
$PY "$here/tests/input_probe.py" "$log" 40 --windowed >"$out/probe.out" 2>&1 &
probe=$!
abort() { echo "ABORT: $*"; kill $probe 2>/dev/null; exit 2; }
"$L" window wait-stable $M >/dev/null || abort "probe window not found"
"$L" window move-to $M "$mon" >/dev/null || abort "could not move the probe to $mon"
[[ $desk != cosmic ]] && "$L" window keep-above $M >/dev/null
"$L" window fullscreen $M >/dev/null
"$L" window activate $M >/dev/null
sleep 0.8
"$L" window active | jq -e '.[0].class|ascii_downcase|startswith("com.claude.inputprobe")' >/dev/null || abort "probe is not the active window"
"$L" window info $M | jq -e --arg m "$mon" '.[0]|.fullscreen and .output==$m' >/dev/null || abort "probe is not full screen on $mon"
mark=$(date +%s.%N)
"$L" input move $((cx-30)) $((cy-30)) move "$cx" "$cy"; sleep 0.4
$PY -c "
import json,sys; ev=[json.loads(l) for l in open('$log')]
sys.exit(0 if any(e['ev']=='motion' and e['t']>=$mark-0.05 for e in ev) else 1)" \
    || abort "probe saw no pointer motion: something else is under the pointer"
clip_before=$(wl-paste --no-newline 2>/dev/null | sha256sum)
"$L" input click left sleep 150 click right sleep 300 key escape sleep 150 click left 2 sleep 150 \
    keydown shift click left keyup shift sleep 150 keydown ctrl click left keyup ctrl sleep 150 \
    scroll 2 scroll -1 sleep 150 drag $((cx-200)) $((cy-100)) $((cx+200)) $((cy+100)) sleep 150 \
    type "Hi!" key ctrl+a paste "probe-paste" 2>"$out/input.err"
clip_after=$(wl-paste --no-newline 2>/dev/null | sha256sum)
sleep 0.5
kill $probe 2>/dev/null
fail=0
check() { if $PY - "$log" "$@" <<'PY'
import json,sys
ev=[json.loads(l) for l in open(sys.argv[1])]
want=json.loads(sys.argv[3]); n=int(sys.argv[4]) if len(sys.argv)>4 else 1
hits=[e for e in ev if all(e.get(k)==v for k,v in want.items())]
sys.exit(0 if len(hits)>=n else 1)
PY
then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }
check "left click"          '{"ev":"button-press","num":1,"mods":[]}'
check "right click"         '{"ev":"button-press","num":3}'
check "double click (>=5 left presses total)" '{"ev":"button-press","num":1}' 5
check "shift+click"         '{"ev":"button-press","num":1,"mods":["shift"]}'
check "ctrl+click"          '{"ev":"button-press","num":1,"mods":["ctrl"]}'
check "drag motion"         '{"ev":"drag-motion"}' 5
check "wheel down x2 (delta -120)" '{"ev":"wheel","delta":-120}' 2
check "wheel up (delta +120)" '{"ev":"wheel","delta":120}'
check "type H"              '{"ev":"key-press","keysym":"H"}'
check "type i"              '{"ev":"key-press","keysym":"i"}'
check "type !"              '{"ev":"key-press","keysym":"exclam"}'
check "ctrl+a"              '{"ev":"key-press","keysym":"a","mods":["ctrl"]}'
check "paste sends ctrl+v"  '{"ev":"key-press","keysym":"v","mods":["ctrl"]}'
if [[ $clip_before == "$clip_after" ]]; then echo "ok   paste put the clipboard back"; else echo "FAIL paste changed the clipboard"; fail=1; fi
echo "log: $log"; exit $fail
