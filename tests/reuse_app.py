"""A single-instance GTK4 app for tests/test-window.sh: a second launch does not open a window,
it retitles and presents the first one (like an app opening a file in a new tab).
  /usr/bin/python3 reuse_app.py [SECONDS]
"""
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

life = float(sys.argv[1]) if len(sys.argv) > 1 else 30
n = [0]


def activate(app):
    n[0] += 1
    wins = app.get_windows()
    if wins:  # the second launch lands here, in the first process
        wins[0].set_title(f"lcu reuse probe (request {n[0]})")
        wins[0].present()
        return
    w = Gtk.ApplicationWindow(application=app, title="lcu reuse probe (request 1)")
    w.set_default_size(500, 300)
    w.present()
    GLib.timeout_add(int(life * 1000), app.quit)


app = Gtk.Application(application_id="org.lcu.ReuseProbe", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
app.connect("activate", activate)
app.run([])
