#!/usr/bin/env bash
# Check everything linux-computer-use needs on KDE Plasma, without changing anything.
# Usage: lcu check      Exit 0 = all required parts present.
# "need" lines are required for the named feature; "opt" lines only for that feature.
set -uo pipefail
missing=0
ok()   { printf 'ok    %-34s %s\n' "$1" "$2"; }
bad()  { printf '%-5s %-34s %s\n' "$3" "$1" "$2"; [[ $3 == need ]] && missing=1; }
have() { command -v "$1" >/dev/null 2>&1; }
check_cmd() { if have "$1"; then ok "$1" "$2"; else bad "$1" "missing ($2)" "${3:-need}"; fi; }

[[ ${XDG_SESSION_TYPE:-} == wayland && ${XDG_CURRENT_DESKTOP:-} == *KDE* ]] \
    && ok "session" "KDE Wayland" || bad "session" "not KDE Plasma on Wayland (${XDG_CURRENT_DESKTOP:-?}/${XDG_SESSION_TYPE:-?})" need
if gdbus introspect --session --dest org.kde.KWin --object-path /org/kde/KWin/EIS/RemoteDesktop 2>/dev/null | grep -q connectToEIS; then
    ok "KWin EIS interface" "input without root"
else bad "KWin EIS interface" "org.kde.KWin.EIS.RemoteDesktop missing (needs Plasma 6.1+)" need; fi
if ldconfig -p 2>/dev/null | grep -q 'libei.so.1 ' || [[ -e /usr/lib64/libei.so.1 || -e /usr/lib/libei.so.1 || -e /usr/lib/x86_64-linux-gnu/libei.so.1 ]]; then
    ok "libei.so.1" "input"; else bad "libei.so.1" "missing (package libei / libei1)" need; fi
[[ -x /usr/bin/python3 ]] && ok "/usr/bin/python3" "runs the scripts" || bad "/usr/bin/python3" "missing" need
/usr/bin/python3 -s -c 'import gi; gi.require_version("Gio","2.0"); gi.require_version("GdkPixbuf","2.0"); from gi.repository import Gio, GdkPixbuf' 2>/dev/null \
    && ok "python gi (Gio, GdkPixbuf)" "scripts" || bad "python gi (Gio, GdkPixbuf)" "missing (python3-gobject, gdk-pixbuf2)" need
check_cmd spectacle "screenshots"
check_cmd kscreen-doctor "monitor layout"
check_cmd gtk-launch "starting apps" opt
check_cmd ffmpeg "frames + crops of recordings"
check_cmd ffprobe "recording checks"
check_cmd gst-launch-1.0 "real-time recording" opt
if have gst-inspect-1.0; then
    for el in pipewiresrc vp8enc webmmux videoconvert videorate; do
        gst-inspect-1.0 "$el" >/dev/null 2>&1 && ok "gstreamer: $el" "real-time recording" || bad "gstreamer: $el" "missing" opt
    done
fi
busctl --user list 2>/dev/null | grep -q org.freedesktop.impl.portal.desktop.kde \
    && ok "xdg-desktop-portal-kde" "screen-share grant" || bad "xdg-desktop-portal-kde" "not running (real-time recording)" opt
# Ask portal.py, so this sees the same per-app grant and fallbacks that `capture record` uses.
PYTHONPATH="$(dirname "${BASH_SOURCE[0]}")/.." /usr/bin/python3 -s -c \
    'import sys, portal; sys.exit(0 if portal.load_token(portal.SCREENCAST_TOKEN) else 1)' 2>/dev/null \
    && ok "screen-share grant" "saved (real-time recording)" || bad "screen-share grant" "not yet: lcu capture record-setup (dialog, with the user)" opt
/usr/bin/python3 -s -c 'import gi; gi.require_version("Atspi","2.0"); from gi.repository import Atspi' 2>/dev/null \
    && ok "python gi Atspi" "find/press controls by name" || bad "python gi Atspi" "missing (at-spi2-core)" opt
a11y=$(gsettings get org.gnome.desktop.interface toolkit-accessibility 2>/dev/null)
[[ $a11y == true ]] && ok "accessibility switch" "on" || bad "accessibility switch" "off; see README" opt
check_cmd tesseract "OCR" opt
have tesseract && { tesseract --list-langs 2>/dev/null | grep -qx eng && ok "tesseract eng data" "OCR" || bad "tesseract eng data" "missing" opt; }
check_cmd jq "tests" opt
/usr/bin/python3 -s -c 'import gi; gi.require_version("Gtk","4.0"); from gi.repository import Gtk' 2>/dev/null \
    && ok "python gi Gtk 4" "test probe and dialogs" || bad "python gi Gtk 4" "missing (gtk4)" opt
check_cmd wl-copy "paste (any text), clipboard restore" opt
exit $missing
