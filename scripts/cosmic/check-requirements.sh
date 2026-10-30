#!/usr/bin/env bash
# Check everything linux-computer-use needs on COSMIC, without changing anything.
# Usage: lcu check      Exit 0 = all required parts present.
# "need" lines are required for the named feature; "opt" lines only for that feature.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; PY=/usr/bin/python3
missing=0
ok()   { printf 'ok    %-36s %s\n' "$1" "$2"; }
bad()  { printf '%-5s %-36s %s\n' "$3" "$1" "$2"; [[ $3 == need ]] && missing=1; }
have() { command -v "$1" >/dev/null 2>&1; }
check_cmd() { if have "$1"; then ok "$1" "$2"; else bad "$1" "missing ($2)" "${3:-need}"; fi; }

[[ ${XDG_SESSION_TYPE:-} == wayland && ${XDG_CURRENT_DESKTOP:-} == *COSMIC* ]] \
    && ok "session" "COSMIC Wayland (${COSMIC_VERSION:-?})" \
    || bad "session" "not COSMIC on Wayland (${XDG_CURRENT_DESKTOP:-?}/${XDG_SESSION_TYPE:-?})" need
[[ -x $PY ]] && ok "$PY" "runs the scripts" || bad "$PY" "missing" need
$PY -s -c 'import gi; gi.require_version("Gio","2.0"); gi.require_version("GdkPixbuf","2.0"); from gi.repository import Gio, GdkPixbuf' 2>/dev/null \
    && ok "python gi (Gio, GdkPixbuf)" "scripts" || bad "python gi (Gio, GdkPixbuf)" "missing (python-gobject, gdk-pixbuf2)" need
globals=$($PY -s -c "import sys; sys.path.insert(0, '$here'); from ccu_wayland import Client; print(' '.join(i for i, _ in Client().globals.values()))" 2>/dev/null)
for g in ext_foreign_toplevel_list_v1 zcosmic_toplevel_info_v1 zcosmic_toplevel_manager_v1 zxdg_output_manager_v1 ext_workspace_manager_v1; do
    [[ " $globals " == *" $g "* ]] && ok "wayland: $g" "windows" || bad "wayland: $g" "not offered by the compositor" need
done
for g in ext_image_copy_capture_manager_v1 ext_output_image_capture_source_manager_v1 ext_foreign_toplevel_image_capture_source_manager_v1; do
    [[ " $globals " == *" $g "* ]] && ok "wayland: $g" "screenshots, recording" || bad "wayland: $g" "not offered by the compositor" need
done
if ldconfig -p 2>/dev/null | grep -q 'libei.so.1 ' || [[ -e /usr/lib/libei.so.1 || -e /usr/lib64/libei.so.1 || -e /usr/lib/x86_64-linux-gnu/libei.so.1 ]]; then
    ok "libei.so.1" "input"; else bad "libei.so.1" "missing (package libei / libei1)" need; fi
ver=$(gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop \
      --method org.freedesktop.DBus.Properties.Get org.freedesktop.portal.RemoteDesktop version 2>/dev/null | sed -n 's/.*uint32 \([0-9]*\).*/\1/p')
[[ ${ver:-0} -ge 2 ]] && ok "RemoteDesktop portal v$ver" "input (ConnectToEIS)" || bad "RemoteDesktop portal" "missing or < v2 (xdg-desktop-portal-cosmic)" need
st="${XDG_STATE_HOME:-$HOME/.local/state}"
[[ -s $st/linux-computer-use/remote-desktop.token || -s $st/cosmic-computer-use/remote-desktop.token ]] \
    && ok "input grant" "restore token saved" || bad "input grant" "not yet: lcu setup shows the dialog once" opt
check_cmd ffmpeg "recording" opt
check_cmd ffprobe "recording tests" opt
$PY -s -c 'import gi; gi.require_version("Atspi","2.0"); from gi.repository import Atspi' 2>/dev/null \
    && ok "python gi Atspi" "find/press controls by name" || bad "python gi Atspi" "missing (at-spi2-core)" opt
[[ $(gsettings get org.gnome.desktop.interface toolkit-accessibility 2>/dev/null) == true ]] \
    && ok "toolkit accessibility" "on (GTK3/Qt/Electron)" || bad "toolkit accessibility" "off: GTK4 still works; GTK3/Qt/Electron need it" opt
check_cmd tesseract "OCR" opt
have tesseract && { tesseract --list-langs 2>/dev/null | grep -qx eng && ok "tesseract eng data" "OCR" || bad "tesseract eng data" "missing" opt; }
$PY -s -c 'import gi; gi.require_version("Gtk","4.0"); from gi.repository import Gtk' 2>/dev/null \
    && ok "python gi Gtk 4" "test probe and dialogs" || bad "python gi Gtk 4" "missing (gtk4)" opt
check_cmd jq "tests" opt
check_cmd wl-copy "paste (any text), clipboard restore" opt
check_cmd gtk-launch "starting apps" opt
exit $missing
