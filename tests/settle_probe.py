"""GTK4 window for timing `capture shot --settle`: each click, after DELAY s, flickers for ANIM s, then shows a solid colour.
  /usr/bin/python3 -s tests/settle_probe.py SECONDS DELAY ANIM
The final colour alternates: odd clicks green, even clicks blue. Pressing 1/2/3 sets DELAY to 0.1/1/3 s."""
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

life, delay, anim = (float(v) for v in sys.argv[1:4])
css = Gtk.CssProvider()
css.load_from_string(".r{background:#c80000}.g{background:#00c800}.b{background:#0000c8}.y{background:#c8c800}.m{background:#c800c8}")


def activate(app):
    win = Gtk.ApplicationWindow(application=app, title="lcu settle probe")
    win.set_default_size(500, 300)
    box = Gtk.Box()
    box.set_hexpand(True)
    box.set_vexpand(True)
    win.set_child(box)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    box.set_css_classes(["r"])
    st = {"n": 0, "delay": delay}

    def start():
        end = GLib.get_monotonic_time() + int(anim * 1e6)
        flip = {"v": False}

        def tick():
            if GLib.get_monotonic_time() >= end:
                box.set_css_classes(["g" if st["n"] % 2 else "b"])
                return False
            flip["v"] = not flip["v"]
            box.set_css_classes(["y" if flip["v"] else "m"])
            return True
        GLib.timeout_add(60, tick)
        return False

    def click(*_):
        st["n"] += 1
        GLib.timeout_add(int(st["delay"] * 1000), start)
    g = Gtk.GestureClick()
    g.connect("pressed", click)
    win.add_controller(g)

    def key(c, kv, code, state):
        name = Gdk.keyval_name(kv)
        if name in ("1", "2", "3"):
            st["delay"] = {"1": 0.1, "2": 1.0, "3": 3.0}[name]
        return False
    k = Gtk.EventControllerKey()
    k.connect("key-pressed", key)
    win.add_controller(k)
    win.present()
    GLib.timeout_add(int(life * 1000), app.quit)


app = Gtk.Application(application_id="org.lcu.SettleProbe", flags=Gio.ApplicationFlags.NON_UNIQUE)
app.connect("activate", activate)
app.run([])
