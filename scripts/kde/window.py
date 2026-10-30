#!/usr/bin/python3
"""List and control windows on KDE Plasma 6 Wayland through a temporary KWin script.

KWin scripts cannot print back to us, so this process owns a private D-Bus name
(org.lcu.KWinBridge.p<PID>) and the script reports with callDBus().
Nothing is saved to KWin's settings; the script is unloaded at exit.

Usage:
  lcu window list [--all]                    # JSON, one object per window, topmost first
  lcu window active                          # the focused window
  lcu window pointer                         # pointer position and output, and KWin's active output
  lcu window at X Y                          # KWin's hit test, including resize borders
  lcu window drag-resize MATCH W H [--edge EDGE] [--step PX] [--no-raise]
  lcu window drag-move MATCH X Y --grab GX GY [--no-raise]
                       # target frame origin; grab is a visually verified header point, relative to frame
  lcu window ACTION MATCH [ARGS]
  lcu window launch [--on OUTPUT] [--maximize|--fullscreen] [--match MATCH] -- CMD [ARGS]
MATCH: id:{uuid} | class:PREFIX (Wayland app_id / desktop file name / X11 WM_CLASS,
       case-insensitive) | title:SUBSTRING (case-insensitive) | pid:N.  ACTION applies
       to every match unless --first is given (then the topmost one).
ACTIONS:
  info                print the matched windows
  wait-stable         wait until it exists and its geometry is unchanged for 0.4 s
  activate            raise + focus (unminimizes)
  raise               raise without taking focus
  minimize | unminimize
  maximize | unmaximize
  fullscreen | unfullscreen
  keep-above | no-keep-above
  close               ask the window to close (like the title-bar X; the app may
                      prompt to save). Never use on the user's apps without asking.
  move-to OUTPUT      e.g. DP-1, eDP-1 (keeps size, centres)
  geometry X Y W H    logical pixels (frame)
--all also lists panels, popups and other non-normal windows.

launch starts CMD detached, waits (20 s) for its new window and prints it. New
windows open on KWin's active output, which is not always the one you want, so --on
moves the window to OUTPUT if it opened elsewhere; --maximize/--fullscreen apply after
it appears. --match picks the window when the app opens more than one (default: the
first new window). Only a window id that did not exist before counts: when a running
single-instance app answers in a window that already existed (it gains focus or a new
title, e.g. a new tab), launch exits 1 after ~3 s saying so and changes nothing.
"""
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import warnings

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS = f"org.lcu.KWinBridge.p{os.getpid()}"
IFACE = "org.lcu.KWinBridge"
NODE = Gio.DBusNodeInfo.new_for_xml(
    f'<node><interface name="{IFACE}"><method name="result"><arg type="s" direction="in"/></method></interface></node>')

JS = r"""
const BUS = %(bus)s, ACTION = %(action)s, MATCH = %(match)s, ARGS = %(args)s, FIRST = %(first)s, ALL = %(all)s;
function maximized(w) {
    if (w.maximizeMode !== undefined) return w.maximizeMode === 3;
    const a = workspace.clientArea(KWin.MaximizeArea, w), g = w.frameGeometry;
    return g.x === a.x && g.y === a.y && g.width === a.width && g.height === a.height;
}
function rect(r) { return {x: r.x, y: r.y, width: r.width, height: r.height}; }
function info(w) {
    const g = w.frameGeometry;
    return {id: w.internalId.toString(), class: String(w.resourceClass), name: String(w.resourceName),
            desktop_file: String(w.desktopFileName || ""), title: String(w.caption), pid: w.pid,
            x: g.x, y: g.y, width: g.width, height: g.height,
            client: rect(w.clientGeometry), buffer: rect(w.bufferGeometry),
            output: w.output ? w.output.name : null, active: w === workspace.activeWindow,
            minimized: w.minimized, maximized: maximized(w), fullscreen: w.fullScreen, keepAbove: w.keepAbove,
            normal: w.normalWindow, dock: !!w.dock, desktop: !!w.desktopWindow, workspace: w.desktops.map(d => d.name),
            decorated: w.frameGeometry.width !== w.clientGeometry.width || w.frameGeometry.height !== w.clientGeometry.height, resizing: !!w.resize, moving: !!w.move,
            min_size: {width: w.minSize.width, height: w.minSize.height},
            screen: w.output ? rect(w.output.geometry) : null,
            area: rect(workspace.clientArea(KWin.MaximizeArea, w))};
}
function shown(w) {  // drawn on the current workspace (desktops == [] means all workspaces)
    return !w.minimized && !w.deleted && (w.desktops.length === 0 || w.desktops.includes(workspace.currentDesktop));
}
function matches(w) {
    const [k, ...rest] = MATCH.split(":"); const v = rest.join(":").toLowerCase();
    if (k === "id") return w.internalId.toString().toLowerCase() === v;
    if (k === "class") return String(w.resourceClass).toLowerCase().startsWith(v) || String(w.desktopFileName).toLowerCase().startsWith(v);
    if (k === "title") return String(w.caption).toLowerCase().includes(v);
    if (k === "pid") return String(w.pid) === v;
    return false;
}
let out = {ok: true, windows: []};
try {
    // stackingOrder is bottom..top; reverse so the topmost comes first
    let wins = workspace.stackingOrder.slice().reverse().filter(w => ALL || w.normalWindow || w.dialog);
    if (ACTION === "list") {
        out.windows = wins.map(info);
    } else if (ACTION === "active") {
        out.windows = workspace.activeWindow ? [info(workspace.activeWindow)] : [];
    } else if (ACTION === "pointer") {
        const p = workspace.cursorPos, o = workspace.screens.find(s => {
            const g = s.geometry; return p.x >= g.x && p.x < g.x + g.width && p.y >= g.y && p.y < g.y + g.height; });
        out.pointer = {x: p.x, y: p.y, output: o ? o.name : null,
                       active_output: workspace.activeScreen ? workspace.activeScreen.name : null};
    } else if (ACTION === "at") {
        // KWin includes decoration resize zones outside frameGeometry. Frame rectangles
        // alone would identify the window behind a thin resize border instead.
        const x = +ARGS[0], y = +ARGS[1];
        out.windows = Array.from(workspace.windowAt({x, y})).filter(shown).map(info);
    } else if (ACTION === "areas") {
        out.outputs = workspace.screens.map(s => ({name: s.name,
            area: rect(workspace.clientArea(KWin.MaximizeArea, s, workspace.currentDesktop))}));
    } else {
        let hit = wins.filter(matches);
        if (FIRST) hit = hit.slice(0, 1);
        if (!hit.length) { out.ok = false; out.error = "no window matches " + MATCH; }
        for (const w of hit) {
            switch (ACTION) {
            case "activate": w.minimized = false; workspace.activeWindow = w; workspace.raiseWindow(w); break;
            case "raise": workspace.raiseWindow(w); break;
            case "minimize": w.minimized = true; break;
            case "unminimize": w.minimized = false; break;
            case "maximize": w.setMaximize(true, true); break;
            case "unmaximize": w.setMaximize(false, false); break;
            case "fullscreen": w.fullScreen = true; break;
            case "unfullscreen": w.fullScreen = false; break;
            case "keep-above": w.keepAbove = true; break;
            case "no-keep-above": w.keepAbove = false; break;
            case "close": w.closeWindow(); break;
            case "move-to": {
                const o = workspace.screens.find(s => s.name === ARGS[0]);
                if (!o) { out.ok = false; out.error = "no output " + ARGS[0]; break; }
                workspace.sendClientToScreen(w, o);
                const a = o.geometry, f = w.frameGeometry;
                const width = Math.min(f.width, a.width), height = Math.min(f.height, a.height);
                w.frameGeometry = {x: a.x + Math.round((a.width - width) / 2), y: a.y + Math.round((a.height - height) / 2), width, height};
                break;
            }
            case "geometry": w.frameGeometry = {x: +ARGS[0], y: +ARGS[1], width: +ARGS[2], height: +ARGS[3]}; break;
            case "info": break;
            default: out.ok = false; out.error = "unknown action " + ACTION;
            }
        }
        out.windows = hit.map(info);
    }
} catch (e) { out.ok = false; out.error = String(e); }
callDBus(BUS, "/", "org.lcu.KWinBridge", "result", JSON.stringify(out));
"""


def _call(bus, path, iface, method, args=None, rtype=None):
    r = bus.call_sync("org.kde.KWin", path, iface, method, args, GLib.VariantType(rtype) if rtype else None,
                      Gio.DBusCallFlags.NONE, 10000, None)
    return r.unpack() if r is not None else ()


def run(action, match="", args=(), first=False, all_windows=False, timeout=3.0):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    got = []

    def on_call(_conn, _sender, _path, _iface, _method, params, invocation):
        got.append(params.unpack()[0])
        invocation.return_value(None)
    with warnings.catch_warnings():  # the closure-based variant needs PyGObject 3.52+
        warnings.simplefilter("ignore", DeprecationWarning)
        reg = bus.register_object("/", NODE.interfaces[0], on_call, None, None)
    bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "RequestName",
                  GLib.Variant("(su)", (BUS, 4)), GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 5000, None)
    js = JS % {k: json.dumps(v) for k, v in dict(bus=BUS, action=action, match=match, args=list(args),
                                                     first=first, all=all_windows).items()}
    fd, path = tempfile.mkstemp(suffix=".js", prefix="lcu-kwin-")
    name = f"lcu-window-{os.getpid()}"
    with os.fdopen(fd, "w") as f:
        f.write(js)
    try:
        sid = _call(bus, "/Scripting", "org.kde.kwin.Scripting", "loadScript", GLib.Variant("(ss)", (path, name)), "(i)")[0]
        if sid < 0:
            sys.exit("KWin refused to load the script")
        _call(bus, f"/Scripting/Script{sid}", "org.kde.kwin.Script", "run")
        ctx, end = GLib.MainContext.default(), time.monotonic() + timeout
        while not got and time.monotonic() < end:
            ctx.iteration(False) or time.sleep(0.005)
        if not got:
            sys.exit("timed out waiting for KWin script result")
        return json.loads(got[0])
    finally:
        try:
            _call(bus, "/Scripting", "org.kde.kwin.Scripting", "unloadScript", GLib.Variant("(s)", (name,)), "(b)")
        finally:
            os.unlink(path)
            bus.unregister_object(reg)


def wait_stable(match, timeout=10):
    """-> the window list once MATCH exists and its geometry is unchanged for 0.4 s, else None."""
    last, since, end = None, time.monotonic(), time.monotonic() + timeout
    while time.monotonic() < end:
        res = run("info", match, first=True)
        geo = [(w["x"], w["y"], w["width"], w["height"]) for w in res["windows"]] if res["ok"] else None
        if geo != last:
            last, since = geo, time.monotonic()
        elif geo and time.monotonic() - since >= 0.4:
            return res["windows"]
        time.sleep(0.1)
    return None


def launch(argv):
    opts, cmd = (argv[:argv.index("--")], argv[argv.index("--") + 1:]) if "--" in argv else (argv, [])
    if not cmd:
        sys.exit("launch needs -- CMD [ARGS]")
    on = opts[opts.index("--on") + 1] if "--on" in opts else None
    match = opts[opts.index("--match") + 1] if "--match" in opts else None
    seen = {w["id"]: w for w in run("list", all_windows=True)["windows"]}
    before = set(seen)
    was_active = next((w["id"] for w in seen.values() if w["active"]), None)
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    win, reused, end = None, None, time.monotonic() + 20
    while not win and time.monotonic() < end:
        time.sleep(0.2)
        now = run("list")["windows"]
        fresh = [w for w in now if w["id"] not in before]
        if match:
            ids = {w["id"] for w in run("info", match)["windows"]}
            fresh = [w for w in fresh if w["id"] in ids]
        win = fresh[0] if fresh else None
        # A running single-instance app (Kate, Dolphin in some setups, unique GTK apps) may
        # answer in a window that already existed: it gets focus or a new title. Report that
        # after 3 s instead of treating that window as the launched one.
        # Without --match only a focus move counts: other windows retitle themselves all the time.
        for w in now:
            old_w = seen.get(w["id"])
            focused = w["active"] and w["id"] != was_active
            if old_w and not fresh and (focused or (match and w["title"] != old_w["title"])):
                if not match or w["id"] in ids:
                    reused = reused or (w, time.monotonic())
        if not win and reused and time.monotonic() - reused[1] > 3:
            w = reused[0]
            sys.exit(f"{' '.join(cmd)} opened no new window; the running app answered in its existing window "
                     f"id:{w['id']} ({w['title']!r}). Nothing was moved or resized. That window may be the "
                     "user's: restore what changed in it (window info) and ask before using it.")
    if not win:
        sys.exit(f"no new window appeared within 20 s for {' '.join(cmd)}")
    m = f"id:{win['id']}"
    wait_stable(m)
    if on and run("info", m)["windows"][0]["output"] != on:
        r = run("move-to", m, [on])
        if not r["ok"]:
            sys.exit(r["error"])
    for flag in ("--maximize", "--fullscreen"):
        if flag in opts:
            run(flag[2:], m)
    time.sleep(0.3)
    print(json.dumps(wait_stable(m) or run("info", m)["windows"], indent=1))
    return 0


EDGES = ("left", "right", "top", "bottom", "top-left", "top-right", "bottom-left", "bottom-right")


def _fail(msg, **state):
    print(json.dumps({"ok": False, "error": msg, **state}, indent=1))
    sys.exit(1)


def _grab_offsets(w, side):
    """Distances in px from the frame edge `side` to try a press at, best first; negative = outside.
    KWin's own decoration is resizable in its border, or just outside it when the border is
    thinner than ~3 px (Breeze extends the resize zone outward). A client-decorated window
    resizes in a 2-5 px band inside its edge (libcosmic, Qt CSD), or in its shadow margin
    just outside (GTK), which `buffer` covers."""
    g, c, b = w, w["client"], w["buffer"]
    if side in ("left", "right"):
        lo, hi = (g["x"], c["x"], b["x"]), (g["x"] + g["width"], c["x"] + c["width"], b["x"] + b["width"])
    else:
        lo, hi = (g["y"], c["y"], b["y"]), (g["y"] + g["height"], c["y"] + c["height"], b["y"] + b["height"])
    border, shadow = (lo[1] - lo[0], lo[0] - lo[2]) if side in ("left", "top") else (hi[0] - hi[1], hi[2] - hi[0])
    if w["decorated"]:
        if side == "top":
            return [-1, -2, -3, 0.5, 2]  # above the title bar, then its top rim
        return [round(border / 2, 1)] if border >= 3 else [-1, -2, -3, 0.5, 2]
    return ([-min(4, shadow / 2)] if shadow >= 4 else []) + [4, 3, 2]


def drag_resize(argv):
    """window drag-resize MATCH W H [--edge E] [--step PX] [--no-raise]: resize like a user, by
    dragging the window's edge or corner with the pointer, and verify every step."""
    pos, opts, step, edge = [], set(), 8.0, None
    it = iter(argv)
    for a in it:
        if a in ("--step", "--edge"):
            value = next(it, None)
            if value is None:
                _fail(f"{a} needs a value")
            if a == "--step":
                try:
                    step = float(value)
                except ValueError:
                    _fail("--step needs a number")
            else:
                edge = value
        elif a.startswith("--"):
            if a not in ("--no-raise", "--left", "--top"):
                _fail(f"unknown option {a}")
            opts.add(a)
        else:
            pos.append(a)
    if len(pos) != 3:
        sys.exit("drag-resize needs MATCH W H")
    if edge and edge not in EDGES:
        _fail(f"--edge must be one of {', '.join(EDGES)}")
    try:
        match, tw, th = pos[0], float(pos[1]), float(pos[2])
    except ValueError:
        _fail("W and H must be numbers")
    if not all(math.isfinite(v) and v > 0 for v in (tw, th, step)):
        _fail("W, H and --step must be finite positive numbers")
    if step > 8:
        _fail("--step must be at most 8 px")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from input import Input

    def win():
        r = run("info", m)
        if not r["ok"]:
            _fail(f"{m} is gone", target={"width": tw, "height": th})
        return r["windows"][0]

    r = run("info", match)
    if not r["ok"]:
        _fail(r["error"])
    if len(r["windows"]) != 1:
        _fail("drag-resize needs exactly one window; use its id")
    w0 = r["windows"][0]
    m = f"id:{w0['id']}"
    if w0["maximized"] or w0["fullscreen"] or w0["minimized"]:
        _fail("drag-resize needs a normal window: unmaximize/unfullscreen/unminimize it first", window=w0)
    a = w0["area"]
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    dw, dh = abs(tw - w0["width"]) >= 1, abs(th - w0["height"]) >= 1
    if edge:  # the user picked the handle: the other edges stay put
        hside = next((s for s in ("left", "right") if s in edge), None)
        vside = next((s for s in ("top", "bottom") if s in edge), None)
        if (dw and not hside) or (dh and not vside):
            _fail(f"the {edge} edge cannot change the {'width' if dw and not hside else 'height'}; "
                  "pick a corner or leave --edge out", window=w0)
        hside, vside = (hside if dw else None), (vside if dh else None)
    else:  # right/bottom unless --left/--top, that edge is off the usable area, or only the other way fits
        hside = None if not dw else "left" if ("--left" in opts or w0["x"] + tw > ax2
                                               or w0["x"] + w0["width"] > ax2 - 2) else "right"
        vside = None if not dh else "top" if ("--top" in opts or w0["y"] + th > ay2
                                              or w0["y"] + w0["height"] > ay2 - 2) else "bottom"
    edge_pos = {"left": w0["x"], "right": w0["x"] + w0["width"], "top": w0["y"], "bottom": w0["y"] + w0["height"]}
    for side in filter(None, (hside, vside)):
        lo, hi = (a["x"], ax2) if side in ("left", "right") else (a["y"], ay2)
        if not lo + 2 <= edge_pos[side] <= hi - 2:
            _fail(f"the {side} edge is off the usable area of {w0['output']}; move the window first "
                  "(window move-to / geometry) or use another --edge", window=w0)
    if hside == "right" and w0["x"] + tw > ax2 or hside == "left" and w0["x"] + w0["width"] - tw < a["x"]:
        _fail(f"width {tw:g} does not fit in the usable area of {w0['output']} with the {hside} edge moving", window=w0)
    if vside == "bottom" and w0["y"] + th > ay2 or vside == "top" and w0["y"] + w0["height"] - th < a["y"]:
        _fail(f"height {th:g} does not fit in the usable area of {w0['output']} with the {vside} edge moving", window=w0)
    if not hside and not vside:
        print(json.dumps({"ok": True, "changed": False, "window": w0}, indent=1))
        return 0
    if w0["output"] is None:
        _fail("the window is on no output", window=w0)

    if "--no-raise" not in opts:  # pressing its edge raises it anyway (KWin click-to-raise)
        run("raise", m)
        time.sleep(0.15)
    inp = Input()
    home = run("pointer")["pointer"]
    log = []

    def edge_point(w, side, off):
        """(x, y) at `off` px from edge `side` (inside if > 0), at its middle."""
        cx, cy = w["x"] + w["width"] / 2, w["y"] + w["height"] / 2
        return {"left": (w["x"] + off, cy), "right": (w["x"] + w["width"] - off, cy),
                "top": (cx, w["y"] + off), "bottom": (cx, w["y"] + w["height"] - off)}[side]

    def safe_to_press(w, x, y):
        """None if a press at x,y can only reach the target; else why not."""
        hits = run("at", args=[x, y])["windows"]
        top = hits[0] if hits else None
        if top and top["id"] == w["id"]:
            return None
        inside = w["x"] <= x < w["x"] + w["width"] and w["y"] <= y < w["y"] + w["height"]
        if inside:
            return f"{x:g},{y:g} is covered or no visible target frame was found"
        if not top or top.get("desktop"):
            return None  # outside, over the desktop: a missed press only reaches the wallpaper
        if top.get("dock"):
            return "panel"  # the panel window, transparent margin included: a press there reaches the panel
        return f"{x:g},{y:g} is outside the target over {top['class']} {top['title']!r}; refusing a speculative press"

    def glide(x1, y1, x2, y2):
        n = max(1, int(-(-max(abs(x2 - x1), abs(y2 - y1)) // step)))
        for i in range(1, n + 1):
            inp.move(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n)
            time.sleep(0.025)

    def one_drag(sides, dx, dy):
        """Press on the edge/corner made of `sides`, drag by dx,dy. -> None if it resized, else why not."""
        w = win()
        offs = [_grab_offsets(w, s) for s in sides]
        tries = list(zip(*[o + [o[-1]] * (max(map(len, offs)) - len(o)) for o in offs]))
        for off in tries:
            if len(sides) == 1:
                gx, gy = edge_point(w, sides[0], off[0])
            else:  # corner: x from the horizontal side, y from the vertical one
                gx, gy = edge_point(w, sides[0], off[0])[0], edge_point(w, sides[1], off[1])[1]
            why = safe_to_press(w, gx, gy)
            if why == "panel":
                # The resize zone just outside this edge is under a panel. The presses left to
                # try are inside the window, which a GTK window (zone in its shadow) ignores.
                log.append({"press": [gx, gy], "skipped": "on a panel"})
                if min(off) < 0:
                    return (f"the {'-'.join(sides)} edge's resize zone is under a panel; move the window "
                            "away from the panel first or use another --edge")
                continue
            if why:
                log.append({"press": [gx, gy], "skipped": why})
                continue
            # approach from 12 px inside: CSD toolkits pick the resize edge from motion over them
            ix = gx + (12 if "left" in sides else -12 if "right" in sides else 0)
            iy = gy + (12 if "top" in sides else -12 if "bottom" in sides else 0)
            inner = run("at", args=[ix, iy])["windows"]
            if inner and inner[0]["id"] == w["id"]:
                inp.move(ix, iy)
                time.sleep(0.1)
                glide(ix, iy, gx, gy)
            else:
                inp.move(gx, gy)
            time.sleep(0.2)
            inp.button("left", True)
            time.sleep(0.3)
            sx, sy = (1 if dx > 0 else -1 if dx < 0 else 0), (1 if dy > 0 else -1 if dy < 0 else 0)
            initial_steps = math.ceil(16 / min(2, step))
            for k in range(1, initial_steps + 1):  # cross KWin's drag threshold before checking resize state
                inp.move(gx + 16 * k / initial_steps * sx, gy + 16 * k / initial_steps * sy)
                time.sleep(0.04)
            if not win()["resizing"]:
                inp.move(gx, gy)  # back to the press point: the miss is a click, not a drag
                time.sleep(0.05)
                inp.button("left", False)
                log.append({"press": [gx, gy], "resize_started": False})
                time.sleep(0.2)
                continue
            glide(gx + 16 * sx, gy + 16 * sy, gx + dx, gy + dy)
            time.sleep(0.3)
            inp.button("left", False)
            log.append({"press": [gx, gy], "resize_started": True, "to": [gx + dx, gy + dy]})
            return None
        return f"no press on the {'-'.join(sides)} edge started a resize; inspect the returned window state"

    try:
        passes, stopped = 0, set()
        while passes < 3:
            w = wait_stable(m) or [win()]
            w = w[0]
            ddx = (tw - w["width"]) if hside and "w" not in stopped else 0
            ddy = (th - w["height"]) if vside and "h" not in stopped else 0
            ddx, ddy = (ddx if abs(ddx) >= 1 else 0), (ddy if abs(ddy) >= 1 else 0)
            if not ddx and not ddy:
                break
            passes += 1
            sx = -ddx if hside == "left" else ddx
            sy = -ddy if vside == "top" else ddy
            s = w["screen"]
            at_screen_edge = any(e < 2 for e in (w["x"] - s["x"], s["x"] + s["width"] - w["x"] - w["width"],
                                                      w["y"] - s["y"], s["y"] + s["height"] - w["y"] - w["height"]))
            if ddx and ddy and not at_screen_edge:
                jobs = [((hside, vside), sx, sy)]
            else:  # one side at a time: a corner on the screen edge reads as that side alone
                jobs = ([((hside,), sx, 0)] if ddx else []) + ([((vside,), 0, sy)] if ddy else [])
            for sides, dx, dy in jobs:
                before = win()
                why = one_drag(sides, dx, dy)
                if why:
                    _fail(why, window=before, attempts=log)
                after = (wait_stable(m) or [win()])[0]
                if dx and abs(after["width"] - before["width"]) < 1:
                    stopped.add("w")
                if dy and abs(after["height"] - before["height"]) < 1:
                    stopped.add("h")
    finally:
        try:
            inp.button("left", False)
            inp.move(home["x"], home["y"])
        finally:
            inp.close()
    w = (wait_stable(m) or [win()])[0]
    short = {k: v for k, v in (("width", tw - w["width"]), ("height", th - w["height"])) if abs(v) >= 1}
    note = None
    if short:
        note = (f"stopped {', '.join(f'{v:+g} px short in {k}' for k, v in short.items())}: target not reached; "
                f"possible app size limits (min {w['min_size']['width']}x{w['min_size']['height']} client px), "
                "size increments or desktop snapping")
    print(json.dumps({"ok": not short, "changed": (w["width"], w["height"]) != (w0["width"], w0["height"]),
                      "from": [w0["width"], w0["height"]], "to": [w["width"], w["height"]], "target": [tw, th],
                      "note": note, "attempts": log, "window": w}, indent=1))
    return 0 if not short else 3


def drag_move(argv):
    """drag-move MATCH X Y --grab GX GY [--no-raise]

    Drag a visually verified, non-interactive header point to reposition one window.
    X/Y are the target frame origin; GX/GY are relative to the current frame.
    Keep the destination at least 16 px inside one output's usable area.
    Exit 0: position reached and size preserved; 3: constrained target; 1: refused.
    """
    if argv == ["--help"]:
        print(drag_move.__doc__)
        return 0
    pos, grab, no_raise = [], None, False
    it = iter(argv)
    for arg in it:
        if arg == "--grab":
            grab = [next(it, None), next(it, None)]
        elif arg == "--no-raise":
            no_raise = True
        elif arg.startswith("--"):
            _fail(f"unknown option {arg}")
        else:
            pos.append(arg)
    if len(pos) != 3 or grab is None or None in grab:
        _fail("drag-move needs MATCH X Y --grab GX GY; inspect the header before choosing the grab point")
    try:
        tx, ty, gx, gy = map(float, [*pos[1:], *grab])
    except ValueError:
        _fail("X, Y, GX and GY must be finite numbers")
    if not all(math.isfinite(v) for v in (tx, ty, gx, gy)):
        _fail("X, Y, GX and GY must be finite numbers")
    res = run("info", pos[0])
    if not res["ok"]:
        _fail(res["error"])
    if len(res["windows"]) != 1:
        _fail("drag-move needs exactly one window; use its id")
    original = res["windows"][0]
    match = f"id:{original['id']}"
    if not original["normal"] or any(original[k] for k in ("maximized", "minimized", "fullscreen")):
        _fail("drag-move needs a normal, visible, unmaximized window", window=original)
    header_height = original["client"]["y"] - original["y"] if original["decorated"] else 64
    if not (6 <= gx <= original["width"] - 6 and 6 <= gy < header_height - 2):
        _fail("--grab must be inside the header, away from borders; verify a blank point visually", window=original)
    areas = run("areas")
    if not areas["ok"]:
        _fail(areas["error"])
    def fits_position(x, y):
        return any(x >= o["area"]["x"] + 16 and y >= o["area"]["y"] + 16 and
                   x + original["width"] <= o["area"]["x"] + o["area"]["width"] - 16 and
                   y + original["height"] <= o["area"]["y"] + o["area"]["height"] - 16
                   for o in areas["outputs"])

    if not fits_position(tx, ty):
        _fail("destination must fit at least 16 px inside one output's usable area", window=original)
    if max(abs(tx-original["x"]), abs(ty-original["y"])) < 1:
        print(json.dumps({"ok": True, "changed": False, "window": original}, indent=1))
        return 0

    def current():
        state = run("info", match)
        if not state["ok"]:
            _fail("target window disappeared")
        return state["windows"][0]

    def size_same(w):
        return all(abs(w[k]-original[k]) < 1 for k in ("width", "height"))

    if not no_raise:
        raised = run("raise", match)
        if not raised["ok"]:
            _fail(raised["error"])
        time.sleep(0.15)
    w = current()
    if any(abs(w[k]-original[k]) >= 1 for k in ("x", "y", "width", "height")):
        _fail("window geometry changed before the drag; inspect it again", window=w)
    dx, dy = tx-w["x"], ty-w["y"]
    distance = max(abs(dx), abs(dy))
    initial = (16*dx/distance, 16*dy/distance)
    if not fits_position(w["x"]+initial[0], w["y"]+initial[1]):
        # A tiny drag near a screen edge must not overshoot into edge tiling.
        initial = next(((x, y) for x, y in ((16,0),(-16,0),(0,16),(0,-16),
                                            (16,16),(-16,16),(16,-16),(-16,-16))
                        if fits_position(w["x"]+x, w["y"]+y)), None)
        if initial is None:
            _fail("no safe initial drag fits inside a usable area; move the window away from screen edges first", window=w)
    px, py = w["x"] + gx, w["y"] + gy
    pointer = run("pointer")["pointer"]
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from input import Input
    inp = Input()
    started = False
    try:
        inp.move(px, py)
        time.sleep(0.2)
        hit = run("at", args=[px, py])
        if not hit["ok"] or not hit["windows"] or hit["windows"][0]["id"] != original["id"]:
            _fail("grab point does not hit the target; no button was pressed", window=current())
        before_press = current()
        actual_pointer = run("pointer")["pointer"]
        if (any(abs(before_press[k]-w[k]) >= 1 for k in ("x", "y", "width", "height")) or
                max(abs(actual_pointer["x"]-px), abs(actual_pointer["y"]-py)) >= 1):
            _fail("window or pointer moved before the press; inspect again", window=before_press)
        inp.button("left", True)
        time.sleep(0.2)
        # Cross the drag threshold before trusting the compositor's moving flag.
        for i in range(1, 9):
            cx, cy = px + initial[0]*i/8, py + initial[1]*i/8
            inp.move(cx, cy)
            time.sleep(0.04)
        state = current()
        started = state["moving"]
        if not started or state["resizing"] or not size_same(state):
            _fail("header grab did not start a move with unchanged size; no retry was made", window=state)
        # Measure actual motion while held. CSD and SSD can use different grab offsets.
        for _ in range(3):
            state = current()
            if not size_same(state) or state["resizing"]:
                _fail("window size changed during the move", window=state)
            dx, dy = tx-state["x"], ty-state["y"]
            if max(abs(dx), abs(dy)) < 1:
                break
            ex, ey = cx + dx, cy + dy
            count = max(1, math.ceil(max(abs(dx), abs(dy))/8))
            for i in range(1, count+1):
                inp.move(cx+(ex-cx)*i/count, cy+(ey-cy)*i/count)
                time.sleep(0.025)
            cx, cy = ex, ey
            time.sleep(0.2)
    finally:
        try:
            inp.button("left", False)
            inp.move(pointer["x"], pointer["y"])
        finally:
            inp.close()
    final = (wait_stable(match) or [current()])[0]
    reached = max(abs(final["x"]-tx), abs(final["y"]-ty)) < 1
    preserved = size_same(final)
    ok = reached and preserved and not final["maximized"] and not final["fullscreen"]
    print(json.dumps({"ok": ok, "changed": any(abs(final[k]-original[k]) >= 1 for k in ("x", "y")),
                      "from": [original["x"], original["y"]], "to": [final["x"], final["y"]],
                      "target": [tx, ty], "grab": [gx, gy], "move_started": started,
                      "size_preserved": preserved, "window": final,
                      "note": None if ok else "target not reached or size/state changed; inspect actual geometry (snapping may apply)"}, indent=1))
    return 0 if ok else 3


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "launch":  # before flag stripping: CMD may contain --first/--all
        return launch(argv[1:])
    if argv[0] == "drag-resize":
        return drag_resize(argv[1:])
    if argv[0] == "drag-move":
        return drag_move(argv[1:])
    first = "--first" in argv
    all_w = "--all" in argv
    argv = [a for a in argv if a not in ("--first", "--all")]
    action = argv[0]
    if action == "wait-stable":
        # New windows are often resized/re-centred just after they appear; wait until the
        # geometry has not changed for 0.4 s (timeout 10 s) before reading positions.
        if len(argv) < 2:
            sys.exit("wait-stable needs a MATCH")
        wins = wait_stable(argv[1])
        if not wins:
            sys.exit(f"{argv[1]} did not appear or settle within 10 s")
        print(json.dumps(wins, indent=1))
        return 0
    if action == "pointer":
        print(json.dumps(run("pointer")["pointer"]))
        return 0
    if action in ("list", "active"):
        res = run(action, all_windows=all_w)
    elif action == "at":
        if len(argv) != 3:
            sys.exit("at needs X Y")
        try:
            point = [float(v) for v in argv[1:]]
        except ValueError:
            _fail("at needs finite numeric X Y")
        if not all(math.isfinite(v) for v in point):
            _fail("at needs finite numeric X Y")
        res = run("at", args=point)
    else:
        if len(argv) < 2:
            sys.exit("need a MATCH, see --help")
        res = run(action, argv[1], argv[2:], first=first, all_windows=all_w)
    print(json.dumps(res["windows"] if res["ok"] else res, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
