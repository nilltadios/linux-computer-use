#!/usr/bin/env bash
# Accessibility + OCR check on throwaway GTK4 dialogs (tests/dialog.py, opened and answered here).
# The dialog's exit code proves which button was activated: 0 = Yes, 1 = No.
# Usage: tests/test-a11y.sh        Expected: three "ok" lines (OCR skipped without tesseract), exit 0.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; L="$here/lcu"; PY=/usr/bin/python3; T=$(mktemp -d); fail=0; tag=$$
dialog() {  # title text: opens it, waits until placed, then focuses it
    ($PY "$here/tests/dialog.py" "$1" "$2" 30; echo $? > "$T/$1.rc") &
    "$L" window wait-stable "title:$1" >/dev/null
    "$L" window activate "title:$1" >/dev/null; sleep 0.4
}
click_if_active() {  # title x y
    if "$L" window active | jq -e --arg t "$1" '.[0].title==$t' >/dev/null; then "$L" input move "$2" "$3" click left
    else echo "     (not clicked: $1 was not the active window)"; fi
}
result() {  # title want label
    sleep 0.8; local rc; rc=$(cat "$T/$1.rc" 2>/dev/null || echo open)
    if [[ $rc == "$2" ]]; then echo "ok   $3"; else echo "FAIL $3 (exit $rc, want $2)"; fail=1
        "$L" window close "title:$1" >/dev/null 2>&1; fi   # never leave a test dialog behind
}

t="a11y-press-$tag"; dialog "$t" "press Yes"
"$L" a11y press "$t" --name yes --role button --exact >/dev/null
result "$t" 0 "press Yes by name (accessibility action)"

t="a11y-click-$tag"; dialog "$t" "click No"
read -r x y < <("$L" a11y find "$t" --name no --role button --exact | jq -r '.matches[0].box.center|"\(.[0]) \(.[1])"')
echo "     a11y No at $x,$y"; click_if_active "$t" "$x" "$y"
result "$t" 1 "click No at accessibility coordinates"

if command -v tesseract >/dev/null; then
    t="ocr-click-$tag"; dialog "$t" "click No"
    read -r x y < <("$L" ocr No --window "title:$t" | jq -r '.matches[0].box.center|"\(.[0]) \(.[1])"')
    echo "     OCR No at $x,$y"; click_if_active "$t" "$x" "$y"
    result "$t" 1 "click No at OCR coordinates"
else echo "skip OCR (tesseract not installed)"; fi
exit $fail
