#!/usr/bin/env bash
# Check everything linux-computer-use needs on GNOME, without changing anything.
# Usage: lcu check      Exit 0 = all required parts present.
# "need" lines are required for the named feature; "opt" lines only for that feature.
set -uo pipefail
missing=0
ok()   { printf 'ok    %-36s %s\n' "$1" "$2"; }
bad()  { printf '%-5s %-36s %s\n' "$3" "$1" "$2"; [[ $3 == need ]] && missing=1; }
have() { command -v "$1" >/dev/null 2>&1; }
check_cmd() { if have "$1"; then ok "$1" "$2"; else bad "$1" "missing ($2)" "${3:-need}"; fi; }
introspect() { gdbus introspect --session --dest "$1" --object-path "$2" 2>/dev/null; }

[[ ${XDG_SESSION_TYPE:-} == wayland && ${XDG_CURRENT_DESKTOP:-} == *GNOME* ]] \
    && ok "session" "GNOME Wayland ($(gnome-shell --version 2>/dev/null))" \
    || bad "session" "not GNOME on Wayland (${XDG_CURRENT_DESKTOP:-?}/${XDG_SESSION_TYPE:-?})" need
introspect org.gnome.Mutter.RemoteDesktop /org/gnome/Mutter/RemoteDesktop | grep -q CreateSession \
    && ok "Mutter RemoteDesktop" "input without root" || bad "Mutter RemoteDesktop" "missing" need
introspect org.gnome.Mutter.ScreenCast /org/gnome/Mutter/ScreenCast | grep -q CreateSession \
    && ok "Mutter ScreenCast" "recording, fallback stills" || bad "Mutter ScreenCast" "missing" need
if ldconfig -p 2>/dev/null | grep -q 'libei.so.1 ' || [[ -e /usr/lib64/libei.so.1 || -e /usr/lib/libei.so.1 || -e /usr/lib/x86_64-linux-gnu/libei.so.1 ]]; then
    ok "libei.so.1" "input"; else bad "libei.so.1" "missing (package libei / libei1)" need; fi
[[ -x /usr/bin/python3 ]] && ok "/usr/bin/python3" "runs the scripts" || bad "/usr/bin/python3" "missing" need
/usr/bin/python3 -s -c 'import gi; gi.require_version("Gio","2.0"); gi.require_version("GdkPixbuf","2.0"); from gi.repository import Gio, GdkPixbuf' 2>/dev/null \
    && ok "python3 gi (Gio, GdkPixbuf)" "scripts" || bad "python3 gi (Gio, GdkPixbuf)" "missing (python3-gobject, gdk-pixbuf2)" need
introspect org.gnome.Shell /org/lcu/ComputerUse | grep -q org.lcu.ComputerUse \
    && ok "Computer Use Bridge extension" "windows, fast screenshots" \
    || bad "Computer Use Bridge extension" "not running: lcu setup, then log in again or scripts/gnome/load-extension-live.py" need
check_cmd gst-launch-1.0 "screenshot fallback, recording"
if have gst-inspect-1.0; then
    for el in pipewiresrc pngenc vp8enc webmmux videoconvert videorate; do
        gst-inspect-1.0 "$el" >/dev/null 2>&1 && ok "gstreamer: $el" "recording" || bad "gstreamer: $el" "missing" need
    done
fi
check_cmd ffmpeg "low-fps recording (frames)" opt
check_cmd ffprobe "recording checks" opt
/usr/bin/python3 -s -c 'import gi; gi.require_version("Atspi","2.0"); from gi.repository import Atspi' 2>/dev/null \
    && ok "python3 gi Atspi" "find/press controls by name" || bad "python3 gi Atspi" "missing (at-spi2-core)" opt
a11y=$(gsettings get org.gnome.desktop.interface toolkit-accessibility 2>/dev/null)
[[ $a11y == true ]] && ok "toolkit accessibility" "on (GTK3/Qt/Electron)" || bad "toolkit accessibility" "off: GTK4 still works; lcu setup turns it on" opt
check_cmd tesseract "OCR" opt
have tesseract && { tesseract --list-langs 2>/dev/null | grep -qx eng && ok "tesseract eng data" "OCR" || bad "tesseract eng data" "missing" opt; }
/usr/bin/python3 -s -c 'import gi; gi.require_version("Gtk","4.0"); from gi.repository import Gtk' 2>/dev/null \
    && ok "python3 gi Gtk 4" "input test probe" || bad "python3 gi Gtk 4" "missing (gtk4)" opt
check_cmd jq "tests" opt
check_cmd wl-copy "paste (any text), clipboard restore" opt
check_cmd gtk-launch "starting apps" opt
[[ $(gsettings get org.gnome.shell development-tools 2>/dev/null) == true ]] \
    && ok "Looking Glass (development-tools)" "live extension (re)load" || bad "Looking Glass (development-tools)" "off: load-extension-live.py needs --allow-devtools" opt
exit $missing
