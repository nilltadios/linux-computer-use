#!/usr/bin/env bash
# Resize windows by pointer from all 8 handles with `lcu window drag-resize --edge` (KDE).
#   tests/test-drag-resize.sh [MATCH...]
# With no MATCH, launches the GTK4 probe (KWin title bar). Pass windows of other toolkits to
# cover client-side decorations, e.g. class:org.kde.kwrite (Qt, KWin title bar),
# class:it.mijorus.gearlever (GTK4/libadwaita CSD with a shadow margin),
# class:dev.nilltadios.CosmicAuthenticator (libcosmic CSD). Only use windows the user
# opened for testing. Each one is placed in the middle of its output with room on every side
# (window geometry), then for each of the 8 edges and corners it is grown by 50 px and shrunk
# back by pointer, and finally put back at the user's original geometry.
# A step passes when drag-resize exits 0, the size is within 1 px of the target and every
# edge that is not being dragged stays within 1 px of where it was.
# Expected: 16 "ok" lines per window and one "below minimum" ok line, exit 0.
set -uo pipefail
here=$(cd "$(dirname "$0")/.." && pwd); L="$here/lcu"; fail=0
[[ $("$L" detect | jq -r .desktop) == kde ]] || { echo "skip: drag-resize is KDE only"; exit 0; }
matches=("$@"); probe=
if [[ ${#matches[@]} -eq 0 ]]; then
    if [[ $("$L" window list | jq '[.[]|select(.class=="org.lcu.InputProbe")]|length') != 0 ]]; then
        echo "ABORT: a probe already exists; do not modify it"; exit 2
    fi
    mon=$("$L" capture screens | jq -r 'max_by(.x).name')
    "$L" window launch --on "$mon" -- /usr/bin/python3 "$here/tests/input_probe.py" "$(mktemp)" 300 --windowed >/dev/null || exit 2
    probe=$("$L" window info class:org.lcu.InputProbe | jq -r '.[0].id')
    matches=("id:$probe")
    trap '"$L" window close "id:$probe" >/dev/null 2>&1 || true' EXIT
fi
edges(){ "$L" window info --first "$1" | jq -c '.[0]|{l:.x,t:.y,r:(.x+.width),b:(.y+.height),w:.width,h:.height}'; }
step(){  # MATCH EDGE W H
    local M=$1 E=$2 before after r rc
    before=$(edges "$M")
    r=$("$L" window drag-resize "$M" "$3" "$4" --edge "$E"); rc=$?
    after=$(edges "$M")
    # edges the handle does not include must not move
    local still
    still=$(jq -nr --argjson a "$before" --argjson b "$after" --arg e "$E" '
        [ [ {k:"l",n:"left"},{k:"r",n:"right"},{k:"t",n:"top"},{k:"b",n:"bottom"} ][]
        | . as $edge | select(($e|split("-")|index($edge.n))|not)
        | select((($a[.k]-$b[.k])|fabs) > 1) | .n ] | join(",")') || { fail=1; return; }
    local size_ok=$(jq -n --argjson b "$after" --argjson w "$3" --argjson h "$4" '(($b.w-$w)|fabs) <= 1 and (($b.h-$h)|fabs) <= 1')
    if [[ $rc -eq 0 && $size_ok == true && -z $still ]]; then
        echo "ok   $M $E -> $(jq -r '"\(.w)x\(.h)"' <<<"$after")"
    else
        echo "FAIL $M $E target ${3}x$4 (exit $rc, moved: ${still:-none}): $(jq -c '{error,to,attempts}' <<<"$r" 2>/dev/null || echo "$r")"; fail=1
    fi
}
for M in "${matches[@]}"; do
    w=$("$L" window info --first "$M" | jq -c '.[0]') || { echo "FAIL $M: no such window"; fail=1; continue; }
    read -r x y W H mw mh <<<"$(jq -r '"\(.x) \(.y) \(.width) \(.height) \(.min_size.width) \(.min_size.height)"' <<<"$w")"
    # test size: the window's own size, but at least 150 px above its minimum and with 150 px free on every side
    read -r tx ty tw th <<<"$(jq -r '.area as $a | [([.width, .min_size.width+150] | max), ([.height, .min_size.height+150] | max)]
        | [([.[0], $a.width-300] | min | floor), ([.[1], $a.height-300] | min | floor)]
        | "\($a.x + (($a.width-.[0])/2|floor)) \($a.y + (($a.height-.[1])/2|floor)) \(.[0]) \(.[1])"' <<<"$w")"
    "$L" window geometry "$M" "$tx" "$ty" "$tw" "$th" >/dev/null; sleep 0.6
    read -r w0 h0 <<<"$(edges "$M" | jq -r '"\(.w) \(.h)"')"
    for E in right bottom left top bottom-right bottom-left top-right top-left; do
        gw=$w0; gh=$h0
        [[ $E == *left* || $E == *right* ]] && gw=$(jq -n "$w0+50")
        [[ $E == *top* || $E == *bottom* ]] && gh=$(jq -n "$h0+50")
        step "$M" "$E" "$gw" "$gh"   # grow
        step "$M" "$E" "$w0" "$h0"   # and back
    done
    # below the minimum: drag-resize stops at the app's limit and says so (exit 3)
    r=$("$L" window drag-resize "$M" $((mw / 2)) $((mh / 2)) --edge bottom-right); rc=$?
    if [[ $rc -eq 3 && $(jq -r .note <<<"$r") == *short* ]]; then echo "ok   $M below minimum: $(jq -c .to <<<"$r") ($(jq -r .note <<<"$r"))"
    else echo "FAIL $M below minimum (exit $rc): $(jq -c '{error,to,note}' <<<"$r" 2>/dev/null || echo "$r")"; fail=1; fi
    "$L" window geometry "$M" "$x" "$y" "$W" "$H" >/dev/null  # back where the user had it
    echo "     $M restored to $x,$y ${W}x$H"
done
exit $fail
