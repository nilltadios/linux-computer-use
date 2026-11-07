#!/usr/bin/env bash
# Real desktop: fixed sleep against --settle against --since, on tests/settle_probe.py.
# Usage: tests/test-settle-live.sh [MONITOR] [OUTDIR] [REPEATS] [SLEEP_S]
# One row per delay and method: correct final frames, median seconds after the click.
# Exit 0 = every --since frame was correct.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; L="$here/lcu"; PY=/usr/bin/python3
mon="${1:-$("$L" capture screens | jq -r 'max_by(.x).name')}"; out="${2:-$(mktemp -d)}"; reps="${3:-3}"; nap="${4:-2.5}"
prev=$("$L" window active | jq -r '.[0].id // empty')
life=$(( (reps * 9 + 2) * 8 ))
$PY "$here/tests/settle_probe.py" "$life" 1 0.5 >/dev/null 2>&1 & p=$!
trap 'kill $p 2>/dev/null; [[ -n $prev ]] && "$L" window activate "id:$prev" >/dev/null 2>&1' EXIT
W=pid:$p
"$L" window wait-stable $W >/dev/null || { echo "ABORT: probe did not appear"; exit 2; }
"$L" window move-to $W "$mon" >/dev/null; "$L" window activate $W >/dev/null; sleep 0.6
read -r wx wy ww wh < <("$L" window info $W | jq -r '.[0]|"\(.x|floor) \(.y|floor) \(.width|floor) \(.height|floor)"')
cx=$((wx+ww/2)); cy=$((wy+wh/2)); A="$wx $wy $ww $wh"
colour() { $PY -c "
import gi,sys
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf as G
b=G.Pixbuf.new_from_file(sys.argv[1]);o=b.get_rowstride()*(b.get_height()//2)+b.get_n_channels()*(b.get_width()//2);p=b.get_pixels()
print('%02x%02x%02x'%(p[o],p[o+1],p[o+2]))" "$1"; }
n=0; tsv="$out/trials.tsv"; printf 'delay\tmethod\tok\tseconds\tsettle\n' > "$tsv"
want() { (( n % 2 )) && echo 00c800 || echo 0000c8; }
for key in 1:0.1 2:1 3:3; do
  "$L" input --window $W key "${key%%:*}"
  for r in $(seq "$reps"); do for m in sleep settle since; do
    "$L" capture shot "$out/base.png" --area $A --no-raise --settle --settle-timeout 8 >/dev/null 2>&1 || true
    n=$((n+1)); f="$out/t$n.png"
    "$L" input --window $W move $cx $cy click left
    t0=$(date +%s.%N); info=""
    case $m in
      sleep)  sleep "$nap"; "$L" capture shot "$f" --area $A --no-raise >/dev/null ;;
      settle) info=$("$L" capture shot "$f" --area $A --no-raise --settle 2>/dev/null | jq -c .settle) ;;
      since)  info=$("$L" capture shot "$f" --area $A --no-raise --since "$out/base.png" 2>/dev/null | jq -c .settle) ;;
    esac
    t1=$(date +%s.%N); c=$(colour "$f"); okv=0; [[ $c == "$(want)" ]] && okv=1
    printf '%s\t%s\t%s\t%.2f\t%s\n' "${key##*:}" "$m" "$okv" "$(echo "$t1 - $t0" | bc)" "$info" >> "$tsv"
    # let the probe finish before the next baseline
    [[ $okv == 1 ]] || sleep 4
  done; done
done
$PY - "$tsv" <<'PY'
import csv, statistics as s, sys, collections
rows = list(csv.DictReader(open(sys.argv[1]), delimiter="\t"))
g = collections.defaultdict(list)
for r in rows: g[(float(r["delay"]), r["method"])].append(r)
print("start_delay_s method  correct  median_s")
bad = 0
for (d, m), rs in sorted(g.items()):
    c = sum(int(r["ok"]) for r in rs)
    print(f"{d:>13} {m:<7} {c}/{len(rs)}      {s.median(float(r['seconds']) for r in rs):.2f}")
    bad += (m == "since" and c != len(rs))
sys.exit(1 if bad else 0)
PY
rc=$?; echo "trials: $tsv"; exit $rc
