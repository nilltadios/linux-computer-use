#!/usr/bin/env bash
# `lcu panel`: record every monitor from the real scanout for 2 s and check the file.
# Needs the one-time `lcu panel setup`; exits 77 (skipped) without it. Expected: 3 `ok`, exit 0.
set -uo pipefail
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"; L="$here/../lcu"
out=$(mktemp -d); trap 'rm -rf "$out"' EXIT
"$L" panel status >/dev/null || { echo "skip: lcu panel is not set up (run \`lcu panel setup\`)"; exit 77; }
fail=0
json=$("$L" panel record "$out/all.mkv" --all --seconds 2 --fps 30) && echo "ok record --all" || { echo "FAIL record --all"; fail=1; }
frames=$(ffprobe -v error -select_streams v -count_frames -show_entries stream=nb_read_frames -of csv=p=0 "$out/all.mkv" 2>/dev/null)
[[ ${frames:-0} == 60 ]] && echo "ok 60 frames" || { echo "FAIL frames: ${frames:-none} (expected 60)"; fail=1; }
[[ $json == *'"late": 0'* ]] && echo "ok no late ticks" || { echo "FAIL late ticks: $json"; fail=1; }
exit $fail
