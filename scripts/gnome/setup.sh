#!/usr/bin/env bash
# One-time GNOME setup for linux-computer-use (`lcu setup`) (user level, no root). Safe to rerun; reruns update
# the installed extension.
#   1. installs the Computer Use Bridge shell extension into ~/.local/share/gnome-shell/extensions
#      and adds it to org.gnome.shell enabled-extensions (active from the next login)
#   2. turns on toolkit accessibility, so GTK3/Qt/Electron apps started afterwards expose controls
# Then: log out and back in once, or run scripts/gnome/load-extension-live.py to load it now.
# Undo: gnome-extensions uninstall computer-use@lcu.local
#       gsettings set org.gnome.desktop.interface toolkit-accessibility false
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; uuid=computer-use@lcu.local
exts="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions"; dest="$exts/$uuid"
mkdir -p "$dest"
cp "$here/extension/$uuid/"* "$dest/"
echo "installed $dest"
enabled=$(gsettings get org.gnome.shell enabled-extensions)
if [[ $enabled != *"'$uuid'"* ]]; then
    if [[ $enabled == "@as []" || $enabled == "[]" ]]; then new="['$uuid']"; else new="${enabled%]}, '$uuid']"; fi
    gsettings set org.gnome.shell enabled-extensions "$new"
    echo "added to enabled-extensions"
fi
gsettings set org.gnome.desktop.interface toolkit-accessibility true
busctl --user set-property org.a11y.Bus /org/a11y/bus org.a11y.Status IsEnabled b true 2>/dev/null || true
echo "toolkit accessibility on (restart GTK3/Qt/Electron apps to expose their controls)"
if gdbus introspect --session --dest org.gnome.Shell --object-path /org/lcu/ComputerUse 2>/dev/null | grep -q 'interface org\.lcu\.ComputerUse '; then
    echo "bridge is running (rerun scripts/gnome/load-extension-live.py --force to load changed code)"
else
    echo "bridge not running yet: log out and back in once, or run scripts/gnome/load-extension-live.py"
fi
