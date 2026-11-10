#!/usr/bin/env bash
# One-time root setup for `lcu panel` (recording what the monitors really show).
#   setup.sh            build the helper as you, then install it with sudo (asks for your password once)
#   setup.sh --remove   undo: delete the installed helper
# What root does, and nothing else:
#   install -o root -g root -m 0755  lcu-panel-grab  /usr/local/libexec/lcu-panel-grab
#   setcap cap_sys_admin+ep /usr/local/libexec/lcu-panel-grab
# The capability stays on the file across reboots and system updates; rerun only if the helper's
# source changes. Effect to know about: after this, any program running under your account can
# read the screen through this helper without a share dialog.
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
dest=/usr/local/libexec/lcu-panel-grab
if [[ ${1:-} == --remove ]]; then
  sudo rm -f "$dest" && echo "removed $dest"
  exit 0
fi
command -v gcc >/dev/null || { echo "gcc is needed to build the helper" >&2; exit 1; }
command -v setcap >/dev/null || { echo "setcap (libcap) is needed" >&2; exit 1; }
[[ -x /usr/bin/ffmpeg && $(/usr/bin/ffmpeg -hide_banner -devices 2>/dev/null) == *kmsgrab* ]] \
  || { echo "/usr/bin/ffmpeg with the kmsgrab input is needed" >&2; exit 1; }
build=$(mktemp -d); trap 'rm -rf "$build"' EXIT
gcc -O2 -Wall -Wextra -o "$build/lcu-panel-grab" "$here/lcu-panel-grab.c"
echo "Installing $dest with CAP_SYS_ADMIN (sudo will ask for your password):"
sudo install -D -o root -g root -m 0755 "$build/lcu-panel-grab" "$dest"
sudo setcap cap_sys_admin+ep "$dest"
getcap "$dest"
"$dest" list
echo "done: \`lcu panel record OUT.mkv --screen NAME\` now works"
