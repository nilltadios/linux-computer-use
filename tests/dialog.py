"""GTK4 Yes/No dialog for the accessibility tests (no zenity needed): exit 0 = Yes, 1 = No, 2 = closed.
  /usr/bin/python3 dialog.py TITLE TEXT [SECONDS]
"""
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

title, text = sys.argv[1], sys.argv[2]
life = float(sys.argv[3]) if len(sys.argv) > 3 else 60
rc = [2]


def activate(app):
    win = Gtk.ApplicationWindow(application=app, title=title)
    win.set_default_size(420, 160)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=24, margin_bottom=24,
                  margin_start=24, margin_end=24)
    box.append(Gtk.Label(label=text, vexpand=True))
    row = Gtk.Box(spacing=12, halign=Gtk.Align.END)
    for label, code in (("No", 1), ("Yes", 0)):
        b = Gtk.Button(label=label)
        b.connect("clicked", lambda _b, code=code: (rc.__setitem__(0, code), app.quit()))
        row.append(b)
    box.append(row)
    win.set_child(box)
    win.present()
    GLib.timeout_add(int(life * 1000), app.quit)


# NON_UNIQUE: every run is its own process and window (a unique app would just re-activate)
app = Gtk.Application(application_id="org.lcu.TestDialog", flags=Gio.ApplicationFlags.NON_UNIQUE)
app.connect("activate", activate)
app.run([])
sys.exit(rc[0])
