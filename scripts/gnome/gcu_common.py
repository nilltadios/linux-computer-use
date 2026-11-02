"""Shared helpers for the gnome-computer-use scripts (system python3 + PyGObject only).

- outputs():   monitor layout from Mutter's DisplayConfig, in logical px
- bridge():    calls into the Computer Use Bridge shell extension (windows, screenshots)
- ScreenCast:  Mutter's private ScreenCast API (no dialog) -> PipeWire node ids
"""
import json
import os
import sys
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BRIDGE = ("org.gnome.Shell", "/org/lcu/ComputerUse", "org.lcu.ComputerUse")
UUID = "computer-use@lcu.local"
_bus = None


def bus():
    global _bus
    if _bus is None:
        _bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    return _bus


def call(dest, path, iface, method, args=None, rtype=None, timeout=10000, fds=None):
    """-> (unpacked tuple, Gio.UnixFDList or None)."""
    r, fdl = bus().call_with_unix_fd_list_sync(dest, path, iface, method, args,
                                               GLib.VariantType(rtype) if rtype else None,
                                               Gio.DBusCallFlags.NONE, timeout, fds)
    return (r.unpack() if r is not None else ()), fdl


def get_prop(dest, path, iface, name):
    return call(dest, path, "org.freedesktop.DBus.Properties", "Get", GLib.Variant("(ss)", (iface, name)), "(v)")[0][0]


# --- monitors -------------------------------------------------------------------
def outputs(with_scale=False):
    """{connector: (x, y, w, h)} in logical px, like kscreen-doctor geometry on KDE.
    with_scale=True: {connector: (x, y, w, h, scale)}."""
    serial, monitors, logical, props = call("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
                                            "org.gnome.Mutter.DisplayConfig", "GetCurrentState")[0]
    physical = props.get("layout-mode", 1) == 2  # 2 = physical layout: sizes not divided by scale
    modes = {}
    for (conn, *_), mlist, _mprops in monitors:
        cur = [m for m in mlist if m[6].get("is-current")]
        if cur:
            modes[conn] = (cur[0][1], cur[0][2])
    res = {}
    for x, y, scale, transform, _primary, mons, _p in logical:
        for conn, *_ in mons:
            if conn not in modes:
                continue
            w, h = modes[conn]
            if transform in (1, 3, 5, 7):  # 90/270 degrees
                w, h = h, w
            s = 1 if physical else scale
            res[conn] = (x, y, round(w / s), round(h / s)) + ((scale,) if with_scale else ())
    return res


def primary_output():
    logical = call("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
                   "org.gnome.Mutter.DisplayConfig", "GetCurrentState")[0][2]
    for *_, primary, mons, _p in logical:
        if primary:
            return mons[0][0]
    return None


def desktop_bounds():
    outs = outputs().values()
    minx, miny = min(o[0] for o in outs), min(o[1] for o in outs)
    return minx, miny, max(o[0] + o[2] for o in outs) - minx, max(o[1] + o[3] for o in outs) - miny


def native_scale(region):
    """The scale of the monitor that wholly contains `region` (logical x, y, w, h), else None."""
    x, y, w, h = region
    for ox, oy, ow, oh, scale in outputs(with_scale=True).values():
        if ox <= x and oy <= y and x + w <= ox + ow and y + h <= oy + oh:
            return scale
    return None


def output_at(x, y):
    for name, (ox, oy, ow, oh) in outputs().items():
        if ox <= x < ox + ow and oy <= y < oy + oh:
            return name
    return None


# --- the shell extension ---------------------------------------------------------
BRIDGE_HELP = (f"the Computer Use Bridge shell extension is not running. Install/enable it with "
               f"scripts/setup.sh, then log out and back in once (GNOME on Wayland only loads new "
               f"extensions at login). Check: gnome-extensions info {UUID}")


def bridge_ok():
    try:
        get_prop(*BRIDGE, "Version")
        return True
    except GLib.Error:
        return False


def bridge(method, *args, sig="(s)", timeout=10000):
    try:
        return json.loads(call(*BRIDGE, method, GLib.Variant(sig, args), "(s)", timeout)[0][0])
    except GLib.Error as e:
        if "UnknownMethod" in str(e) or "No such interface" in str(e) or "UnknownObject" in str(e):
            sys.exit(BRIDGE_HELP)
        raise


def windows(action, match="", args=(), first=False, all_windows=False):
    res = bridge("Windows", json.dumps({"action": action, "match": match, "args": list(args),
                                        "first": first, "all": all_windows}))
    outs = outputs()
    for w in res.get("windows", []):  # monitor geometry -> connector name, like KWin's output.name
        m = w.get("monitor")
        w["output"] = next((n for n, g in outs.items() if m and g == (m["x"], m["y"], m["width"], m["height"])), None)
    return res


# --- Mutter ScreenCast (no portal, no dialog) ----------------------------------------
class ScreenCast:
    """One Mutter ScreenCast session with one stream. Mutter shows its screen-sharing
    (or, with recording=True, screen-recording) indicator while the session lives."""
    SC = "org.gnome.Mutter.ScreenCast"

    def __init__(self, recording=False):
        self.path = call(self.SC, "/org/gnome/Mutter/ScreenCast", self.SC, "CreateSession",
                         GLib.Variant("(a{sv})", ({"is-recording": GLib.Variant("b", recording)},)), "(o)")[0][0]
        self.stream = None

    def _opts(self, pointer):
        return {"cursor-mode": GLib.Variant("u", 1 if pointer else 0)}  # 0 hidden, 1 embedded

    def monitor(self, connector, pointer=False):
        self.stream = call(self.SC, self.path, self.SC + ".Session", "RecordMonitor",
                           GLib.Variant("(sa{sv})", (connector, self._opts(pointer))), "(o)")[0][0]

    def area(self, x, y, w, h, pointer=False):
        self.stream = call(self.SC, self.path, self.SC + ".Session", "RecordArea",
                           GLib.Variant("(iiiia{sv})", (int(x), int(y), int(w), int(h), self._opts(pointer))), "(o)")[0][0]

    def window(self, win_id, pointer=False):
        opts = {**self._opts(pointer), "window-id": GLib.Variant("t", int(win_id))}
        self.stream = call(self.SC, self.path, self.SC + ".Session", "RecordWindow",
                           GLib.Variant("(a{sv})", (opts,)), "(o)")[0][0]

    def start(self, timeout=5):
        """-> PipeWire node id of the stream (on the user's default PipeWire daemon)."""
        node = []
        sub = bus().signal_subscribe(self.SC, self.SC + ".Stream", "PipeWireStreamAdded", self.stream, None,
                                     Gio.DBusSignalFlags.NONE, lambda *a: node.append(a[5].unpack()[0]))
        call(self.SC, self.path, self.SC + ".Session", "Start")
        ctx, end = GLib.MainContext.default(), time.monotonic() + timeout
        while not node and time.monotonic() < end:
            ctx.iteration(False) or time.sleep(0.01)
        bus().signal_unsubscribe(sub)
        if not node:
            self.stop()
            sys.exit("Mutter did not start the screencast stream")
        return node[0]

    def params(self):
        try:
            return get_prop(self.SC, self.stream, self.SC + ".Stream", "Parameters")
        except GLib.Error:
            return {}

    def stop(self):
        try:
            call(self.SC, self.path, self.SC + ".Session", "Stop")
        except GLib.Error:
            pass


def here():
    return os.path.dirname(os.path.abspath(__file__))
