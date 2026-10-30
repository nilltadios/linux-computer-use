"""GTK4 window that logs every pointer/key/wheel event as JSON lines.

Used to verify `lcu input` (tests/test-input.sh): run it on a monitor, drive input at it, read the log.
  python3 input_probe.py LOGFILE [SECONDS] [--windowed]
Events use the same names and fields as the KDE skill's Tk probe (button num 1/2/3,
wheel delta -120 per detent down, keysym, mods).
"""
import json
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

log = open(sys.argv[1], "w", buffering=1)
life = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 30
MODS = ((Gdk.ModifierType.SHIFT_MASK, "shift"), (Gdk.ModifierType.CONTROL_MASK, "ctrl"), (Gdk.ModifierType.ALT_MASK, "alt"))


def rec(kind, ctl=None, x=0, y=0, **kw):
    state = ctl.get_current_event_state() if ctl else 0
    d = {"t": round(time.time(), 3), "ev": kind, "x": round(x), "y": round(y),
         "mods": [n for m, n in MODS if state & m], **kw}
    log.write(json.dumps(d) + "\n")


def activate(app):
    win = Gtk.ApplicationWindow(application=app, title="Claude input probe")
    win.set_default_size(800, 500)
    lbl = Gtk.Label(label="Claude input probe - events are logged")
    lbl.set_vexpand(True)
    win.set_child(lbl)

    click = Gtk.GestureClick(button=0)
    click.connect("pressed", lambda c, n, x, y: rec("button-press", c, x, y, num=c.get_current_button(), n=n))
    click.connect("released", lambda c, n, x, y: rec("button-release", c, x, y, num=c.get_current_button()))
    win.add_controller(click)

    motion = Gtk.EventControllerMotion()
    motion.connect("enter", lambda c, x, y: rec("enter", c, x, y))
    motion.connect("motion", lambda c, x, y: rec("drag-motion" if c.get_current_event_state() & Gdk.ModifierType.BUTTON1_MASK
                                                 else "motion", c, x, y))
    win.add_controller(motion)

    scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES | Gtk.EventControllerScrollFlags.DISCRETE)
    # Tk convention: one detent down = delta -120
    scroll.connect("scroll", lambda c, dx, dy: rec("wheel", c, delta=round(-120 * dy), hdelta=round(120 * dx)) or True)
    win.add_controller(scroll)

    keys = Gtk.EventControllerKey()
    keys.connect("key-pressed", lambda c, kv, code, st: rec("key-press", c, keysym=Gdk.keyval_name(kv), code=code) or False)
    win.add_controller(keys)

    focus = Gtk.EventControllerFocus()
    focus.connect("enter", lambda c: rec("focus-in"))
    focus.connect("leave", lambda c: rec("focus-out"))
    win.add_controller(focus)

    if "--windowed" not in sys.argv:
        win.fullscreen()
    win.present()
    GLib.timeout_add(int(life * 1000), app.quit)


# NON_UNIQUE: two probes can run at once (a unique app would just re-activate the first)
app = Gtk.Application(application_id="com.claude.InputProbe", flags=Gio.ApplicationFlags.NON_UNIQUE)
app.connect("activate", activate)
app.run([])
