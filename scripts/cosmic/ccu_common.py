"""Shared helpers for the cosmic-computer-use scripts (system python3; PyGObject only for PNGs/D-Bus).

- Desktop():  one Wayland connection with outputs, windows (toplevels) and workspaces
- capture():  one frame of an output or a window through ext-image-copy-capture (no dialog)
- match():    MATCH syntax shared by every script (id:, class:, title:, active)

Coordinates are cosmic-comp **logical** pixels: outputs sit at their global logical
position (`screens`), window geometry is reported relative to its output and converted
here to global logical coordinates, which is also what EIS absolute input takes.
"""
import mmap
import os
import sys
import time

from ccu_wayland import INTERFACES, Client, WaylandError

STATE = INTERFACES["zcosmic_toplevel_handle_v1"].enums["state"]
STATE_NAMES = {v: k for k, v in STATE.items()}
WS_STATE = INTERFACES["ext_workspace_handle_v1"].enums["state"]
SIMPLE = {"maximize": "set_maximized", "unmaximize": "unset_maximized", "minimize": "set_minimized",
          "unminimize": "unset_minimized", "unfullscreen": "unset_fullscreen", "sticky": "set_sticky",
          "unsticky": "unset_sticky"}


def here():
    return os.path.dirname(os.path.abspath(__file__))


class Output:
    def __init__(self, proxy):
        self.proxy, self.name, self.description = proxy, None, ""
        self.x = self.y = self.width = self.height = 0  # logical
        self.mode = (0, 0)  # physical pixels of the current mode
        self.int_scale = 1
        self.transform = 0

    @property
    def scale(self):
        """Real (fractional) scale: mode pixels per logical pixel."""
        mw, mh = self.mode
        if self.transform in (1, 3, 5, 7):
            mw, mh = mh, mw
        return round(mw / self.width, 4) if self.width else float(self.int_scale)

    def geometry(self):
        return (self.x, self.y, self.width, self.height)

    def as_dict(self):
        return {"name": self.name, "x": self.x, "y": self.y, "width": self.width, "height": self.height,
                "scale": self.scale, "pixels": list(self.mode), "description": self.description}


class Desktop:
    """One connection to cosmic-comp with outputs, toplevels and workspaces read."""

    def __init__(self, windows=True, geometry_timeout=0.6):
        try:
            self.c = Client()
        except (OSError, KeyError) as e:
            sys.exit(f"cannot connect to the Wayland compositor: {e}")
        c = self.c
        self.outputs = []
        xdg = c.bind("zxdg_output_manager_v1", 3)
        for p in c.bind_all("wl_output", 4):
            o = Output(p)
            self.outputs.append(o)
            p.on("name", lambda n, o=o: setattr(o, "name", n))
            p.on("description", lambda d, o=o: setattr(o, "description", d))
            p.on("scale", lambda s, o=o: setattr(o, "int_scale", s))
            p.on("mode", lambda fl, w, h, r, o=o: setattr(o, "mode", (w, h)) if fl & 1 else None)
            p.on("geometry", lambda x, y, pw, ph, sub, mk, md, tr, o=o: setattr(o, "transform", tr))
            xo = xdg.get_xdg_output(p)
            xo.on("logical_position", lambda x, y, o=o: (setattr(o, "x", x), setattr(o, "y", y)))
            xo.on("logical_size", lambda w, h, o=o: (setattr(o, "width", w), setattr(o, "height", h)))
        self.by_proxy = {o.proxy.id: o for o in self.outputs}
        self.windows, self.groups, self.workspaces = [], [], []
        if windows:
            self._read_windows(geometry_timeout)
        else:
            c.roundtrip()

    # --- outputs -----------------------------------------------------------------
    def output(self, name):
        for o in self.outputs:
            if o.name == name:
                return o
        sys.exit(f"no output {name}; have {', '.join(o.name for o in self.outputs)}")

    def output_at(self, x, y):
        for o in self.outputs:
            if o.x <= x < o.x + o.width and o.y <= y < o.y + o.height:
                return o
        return None

    def output_containing(self, region):
        x, y, w, h = region
        for o in self.outputs:
            if o.x <= x and o.y <= y and x + w <= o.x + o.width and y + h <= o.y + o.height:
                return o
        return None

    def bounds(self):
        x0 = min(o.x for o in self.outputs)
        y0 = min(o.y for o in self.outputs)
        return (x0, y0, max(o.x + o.width for o in self.outputs) - x0, max(o.y + o.height for o in self.outputs) - y0)

    # --- windows -----------------------------------------------------------------
    def _read_windows(self, geometry_timeout):
        c = self.c
        if c.has("ext_workspace_manager_v1"):
            wm = c.bind("ext_workspace_manager_v1")
            self.ws_manager = wm

            def group(g):
                g.data.update(outputs=[], workspaces=[])
                g.on("output_enter", lambda o, g=g: g.data["outputs"].append(o))
                g.on("workspace_enter", lambda w, g=g: g.data["workspaces"].append(w))
                self.groups.append(g)

            def ws(w):
                w.data.update(name=None, state=0, coordinates=[])
                w.on("name", lambda n, w=w: w.data.__setitem__("name", n))
                w.on("state", lambda s, w=w: w.data.__setitem__("state", s))
                w.on("coordinates", lambda a, w=w: w.data.__setitem__(
                    "coordinates", [int.from_bytes(a[i:i + 4], "little") for i in range(0, len(a), 4)]))
                self.workspaces.append(w)
            wm.on("workspace_group", group).on("workspace", ws)
        lst = c.bind("ext_foreign_toplevel_list_v1")
        info = c.bind("zcosmic_toplevel_info_v1", 3)
        self.manager = c.bind("zcosmic_toplevel_manager_v1", 4)
        self.seat = c.bind("wl_seat", 1)
        handles = []

        def toplevel(h):
            h.data.update(title="", app_id="", identifier=None)
            h.on("title", lambda t, h=h: h.data.__setitem__("title", t))
            h.on("app_id", lambda a, h=h: h.data.__setitem__("app_id", a))
            h.on("identifier", lambda i, h=h: h.data.__setitem__("identifier", i))
            h.on("closed", lambda h=h: h.data.__setitem__("closed", True))
            handles.append(h)
        lst.on("toplevel", toplevel)
        c.roundtrip()
        while todo := [h for h in handles if "cosmic" not in h.data]:  # windows may appear meanwhile
            for h in todo:
                self._cosmic(info, h)
            c.roundtrip()
        # cosmic-comp sends geometry from its render path: on an idle desktop it can lag a frame
        # (a new list: the toplevel callback keeps appending late windows to `handles`)
        ready = [h for h in handles if "cosmic" in h.data and not h.data.get("closed")]
        visible = lambda h: STATE["minimized"] not in h.data["cosmic"].data["states"]
        c.wait(lambda: all(h.data["cosmic"].data["geometry"] for h in ready if visible(h)), geometry_timeout)
        self.windows = [self._window(h) for h in ready if not h.data.get("closed")]
        # no stacking order in any protocol: active first, then hidden last
        self.windows.sort(key=lambda w: (not w["active"], w["minimized"]))

    def _cosmic(self, info, h):
        ch = info.get_cosmic_toplevel(h)
        ch.data.update(states=[], outputs=[], geometry=None, workspaces=[])
        ch.on("state", lambda a, ch=ch: ch.data.__setitem__(
            "states", [int.from_bytes(a[i:i + 4], "little") for i in range(0, len(a), 4)]))
        ch.on("geometry", lambda o, x, y, w, hh, ch=ch: ch.data.__setitem__("geometry", (o, x, y, w, hh)))
        ch.on("output_enter", lambda o, ch=ch: ch.data["outputs"].append(o))
        ch.on("output_leave", lambda o, ch=ch: o in ch.data["outputs"] and ch.data["outputs"].remove(o))
        ch.on("ext_workspace_enter", lambda w, ch=ch: ch.data["workspaces"].append(w))
        ch.on("ext_workspace_leave", lambda w, ch=ch: w in ch.data["workspaces"] and ch.data["workspaces"].remove(w))
        h.data["cosmic"] = ch

    def _window(self, h):
        ch = h.data["cosmic"].data
        g = ch["geometry"]
        out = self.by_proxy.get(g[0].id) if g and g[0] else None
        if out is None and ch["outputs"]:
            out = self.by_proxy.get(ch["outputs"][0].id)
        w = {"id": h.data["identifier"], "app_id": h.data["app_id"], "title": h.data["title"],
             "output": out.name if out else None}
        if g:
            ox, oy = (out.x, out.y) if out else (0, 0)
            w.update(x=ox + g[1], y=oy + g[2], width=g[3], height=g[4])
        else:
            w.update(x=None, y=None, width=None, height=None)
        st = ch["states"]
        w.update(active=STATE["activated"] in st, minimized=STATE["minimized"] in st,
                 maximized=STATE["maximized"] in st, fullscreen=STATE["fullscreen"] in st,
                 sticky=STATE["sticky"] in st)
        w["workspace"] = [self._ws_name(ws) for ws in ch["workspaces"]]
        w["_handle"], w["_cosmic"] = h, h.data["cosmic"]
        return w

    def _ws_name(self, ws):
        g = next((g for g in self.groups if ws in g.data["workspaces"]), None)
        outs = [self.by_proxy[o.id].name for o in g.data["outputs"] if o.id in self.by_proxy] if g else []
        return {"name": ws.data["name"], "output": ",".join(outs) or None,
                "active": bool(ws.data["state"] & WS_STATE["active"])}

    def find(self, match, first=False):
        hits = [w for w in self.windows if matches(w, match)]
        return hits[:1] if first else hits

    def find_one(self, match):
        hits = self.find(match)
        if not hits:
            sys.exit(f"no window matches {match!r}; see `lcu window list`")
        return hits[0]

    def active(self):
        return [w for w in self.windows if w["active"]]

    # --- actions -----------------------------------------------------------------
    def act(self, w, action, arg=None):
        m, ch = self.manager, w["_cosmic"]
        if action == "activate":
            m.activate(ch, self.seat)
        elif action == "close":
            m.close(ch)
        elif action in SIMPLE:
            getattr(m, SIMPLE[action])(ch)
        elif action == "fullscreen":
            m.set_fullscreen(ch, self.output(arg).proxy if arg else None)
        elif action == "move-to":
            out = self.output(arg)
            g = next((g for g in self.groups if any(o.id == out.proxy.id for o in g.data["outputs"])), None)
            ws = next((ws for ws in (g.data["workspaces"] if g else []) if ws.data["state"] & WS_STATE["active"]), None)
            if ws is None:
                sys.exit(f"no active workspace found on {arg}")
            m.move_to_ext_workspace(ch, ws, out.proxy)
        else:
            raise ValueError(action)
        self.c.roundtrip()

    def close(self):
        self.c.close()


def matches(w, match):
    if match in ("active", "focused"):
        return w["active"]
    kind, _, val = match.partition(":")
    v = val.lower()
    if kind == "id":
        return w["id"] == val
    if kind in ("class", "app", "app_id"):
        a = (w["app_id"] or "").lower()
        return a == v or a.startswith(v) or a.rsplit(".", 1)[-1] == v
    if kind == "title":
        return v in (w["title"] or "").lower()
    sys.exit(f"bad MATCH {match!r}: use id:ID, class:APP_ID, title:TEXT or active")


def public(w):
    d = {k: v for k, v in w.items() if not k.startswith("_")}
    d.setdefault("class", d.get("app_id"))  # same key as the KDE and GNOME backends
    d.setdefault("pid", None)  # cosmic-comp does not tell
    return d


# --- capture -----------------------------------------------------------------------
# wl_shm formats we can turn into RGB: memory byte order on little-endian
SHM_ORDER = {0: "BGRA", 1: "BGRX", 0x34324241: "RGBA", 0x34324258: "RGBX"}  # argb/xrgb8888, abgr/xbgr8888


class CaptureSession:
    """An ext-image-copy-capture session on an output or a toplevel; frames on demand."""

    def __init__(self, desk, output=None, window=None, pointer=False):
        c = self.c = desk.c
        self.desk = desk
        mgr = c.bind("ext_image_copy_capture_manager_v1")
        if window is not None:
            src = c.bind("ext_foreign_toplevel_image_capture_source_manager_v1").create_source(window["_handle"])
        else:
            src = c.bind("ext_output_image_capture_source_manager_v1").create_source(output.proxy)
        self.session = mgr.create_session(src, 1 if pointer else 0)
        self.size, self.formats, self.done, self.stopped = None, [], False, False
        self.session.on("buffer_size", lambda w, h: setattr(self, "size", (w, h)))
        self.session.on("shm_format", lambda f: self.formats.append(f))
        self.session.on("done", lambda: setattr(self, "done", True))
        self.session.on("stopped", lambda: setattr(self, "stopped", True))
        if not c.wait(lambda: self.done or self.stopped, 5):
            sys.exit("the compositor did not describe the capture buffer (is the screen locked?)")
        if self.stopped:
            sys.exit("the compositor stopped the capture session (window closed or capture refused)")
        self.fmt = next((f for f in self.formats if f in SHM_ORDER), None)
        if self.fmt is None:
            sys.exit(f"no usable shm format among {self.formats}")
        w, h = self.size
        self.stride, self.bytes = w * 4, w * h * 4
        fd = os.memfd_create("ccu-capture", os.MFD_CLOEXEC)
        os.ftruncate(fd, self.bytes)
        self.map = mmap.mmap(fd, self.bytes)
        pool = c.bind("wl_shm").create_pool(fd, self.bytes)
        self.buffer = pool.create_buffer(0, w, h, self.stride, self.fmt)
        c.flush()
        os.close(fd)
        self.transform = 0

    def frame(self, timeout=5.0):
        """Capture one frame; -> raw bytes in SHM_ORDER[self.fmt] order, or exit on failure."""
        st = {}
        f = self.session.create_frame()
        f.on("ready", lambda: st.__setitem__("ok", True))
        f.on("failed", lambda r: st.__setitem__("fail", r))
        f.on("transform", lambda t: setattr(self, "transform", t))
        f.attach_buffer(self.buffer)
        w, h = self.size
        f.damage_buffer(0, 0, w, h)
        f.capture()
        if not self.c.wait(lambda: st, timeout):
            f.destroy()
            return None
        f.destroy()
        if "fail" in st:
            reason = {0: "unknown", 1: "buffer constraints changed", 2: "stopped"}.get(st["fail"], st["fail"])
            sys.exit(f"capture failed: {reason}")
        return self.map[:]

    def close(self):
        try:
            self.session.destroy()
            self.buffer.destroy()
            self.c.flush()
        except WaylandError:
            pass
        self.map.close()


def to_rgb(raw, order):
    """-> (bytes, has_alpha) in RGB / RGBA order for GdkPixbuf."""
    if order in ("RGBA", "RGBX"):
        if order == "RGBX":
            b = bytearray(raw)
            b[3::4] = b"\xff" * (len(b) // 4)
            return bytes(b), True
        return raw, True
    b = bytearray(len(raw))
    b[0::4], b[1::4], b[2::4] = raw[2::4], raw[1::4], raw[0::4]
    b[3::4] = raw[3::4] if order == "BGRA" else b"\xff" * (len(raw) // 4)
    return bytes(b), True


def pixbuf(raw, size, order):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib
    data, alpha = to_rgb(raw, order)
    w, h = size
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB, alpha, 8, w, h, w * 4)


def wait_for(fn, timeout, step=0.1):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None
