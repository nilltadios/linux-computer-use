#!/usr/bin/env bash
# Run against one skill checkout; only opens and closes its own isolated probe.
set -uo pipefail
REPO="$(cd -- "$(dirname -- "$0")/.." && pwd)"
OUT="${1:-$(mktemp -d)}"; mkdir -p "$OUT"
L="$REPO/lcu"
[[ $("$L" window list | jq '[.[]|select(.class=="org.lcu.InputProbe")]|length') == 0 ]] || { echo 'ABORT existing probe'; exit 2; }
mapfile -t mons < <("$L" capture screens | jq -r 'sort_by(.x)[:2][].name')
[[ ${#mons[@]} == 2 ]] || { echo 'SKIP: two monitors required'; exit 77; }
"$L" window launch --on "${mons[0]}" -- /usr/bin/python3 "$REPO/tests/input_probe.py" "$OUT/probe.jsonl" 120 --windowed > "$OUT/launch.json" || exit 2
M="id:$(jq -r '.[0].id' "$OUT/launch.json")"
trap '"$L" window close "$M" >/dev/null 2>&1 || true' EXIT
fail=0
for state in fullscreen maximize; do
 "$L" window unfullscreen "$M" >/dev/null
 "$L" window unmaximize "$M" >/dev/null
 "$L" window move-to "$M" "${mons[0]}" >/dev/null
 "$L" window "$state" "$M" >/dev/null
 "$L" window wait-stable "$M" >/dev/null
 for mon in "${mons[1]}" "${mons[0]}"; do
  "$L" window move-to "$M" "$mon" >/dev/null
  "$L" window wait-stable "$M" > "$OUT/$state-$mon.json"
  field=screen; flag=fullscreen
  [[ $state == maximize ]] && { field=area; flag=maximized; }
  if jq -e --arg f "$field" --arg flag "$flag" --arg mon "$mon" '
    .[0] as $w | $w[$f] as $a | $w[$flag] and $w.output==$mon and
    (["x","y","width","height"]|all(. as $k | (($w[$k]-$a[$k])|fabs)<=1))' "$OUT/$state-$mon.json" >/dev/null; then
    echo "PASS $state move-to $mon fills $field"
  else
    echo "FAIL $state move-to $mon"; jq -c '.[0]|{x,y,width,height,screen,area,fullscreen,maximized}' "$OUT/$state-$mon.json"; fail=1
  fi
 done
done
exit "$fail"
