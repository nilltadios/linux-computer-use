#!/usr/bin/env bash
# Recording check: 3 s of each monitor, an area, all monitors at once (--all, KDE), and a probe window;
# checks duration and size.
# KDE needs a saved screen-share grant (`lcu capture record-setup`); GNOME and COSMIC need none.
# Usage: tests/test-record.sh [OUTDIR]     Expected: every line "ok", exit 0.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; L="$here/lcu"; PY=/usr/bin/python3
out="${1:-$(mktemp -d)}"; fail=0; mkdir -p "$out"; M=class:org.lcu.InputProbe
run() {  # name ext args...
    local name=$1 ext=$2; shift 2; local t0=$SECONDS dur=
    if timeout 40 "$L" capture record "$out/$name.$ext" --seconds 3 "$@" </dev/null >"$out/$name.json" 2>"$out/$name.err" \
        && dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out/$name.$ext") \
        && awk -v d="$dur" 'BEGIN{exit !(d>2.4 && d<3.8)}'; then
        size=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$out/$name.$ext")
        echo "ok   $name ($((SECONDS-t0)) s, ${dur} s video, $size)"
    else echo "FAIL $name: $(tail -1 "$out/$name.err") ${dur:-}"; fail=1; fi
}
for o in $("$L" capture screens | jq -r '.[].name'); do run "screen-$o" webm --screen "$o"; done
run area webm --area 100 100 640 360
[[ $("$L" detect | jq -r .desktop) == kde ]] && run all mp4 --all   # every monitor in one session (KDE only)
$PY "$here/tests/input_probe.py" "$(mktemp)" 30 --windowed 2>/dev/null & p=$!
"$L" window wait-stable $M >/dev/null && run window webm --window $M
"$L" window close $M >/dev/null 2>&1; kill $p 2>/dev/null
echo "videos: $out"; exit $fail
