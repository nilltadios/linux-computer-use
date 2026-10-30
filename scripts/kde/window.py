#!/usr/bin/python3
"""List and control windows on KDE Plasma 6 Wayland through a temporary KWin script.

KWin scripts cannot print back to us, so this process owns a private D-Bus name
(org.claude.KWinBridge.p<PID>) and the script reports with callDBus().
Nothing is saved to KWin's settings; the script is unloaded at exit.

Usage:
  lcu window list [--all]                    # JSON, one object per window, topmost first
  lcu window active                          # the focused window
  lcu window pointer                         # pointer position and output, and KWin's active output
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
first new window). A single-instance app that is already running opens its window
in the old process; launch compares window ids, so that is handled.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import warnings

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS = f"org.claude.KWinBridge.p{os.getpid()}"
IFACE = "org.claude.KWinBridge"
NODE = Gio.DBusNodeInfo.new_for_xml(
    f'<node><interface name="{IFACE}"><method name="result"><arg type="s" direction="in"/></method></interface></node>')

JS = r"""
const BUS = %(bus)s, ACTION = %(action)s, MATCH = %(match)s, ARGS = %(args)s, FIRST = %(first)s, ALL = %(all)s;
function maximized(w) {
    if (w.maximizeMode !== undefined) return w.maximizeMode === 3;
    const a = workspace.clientArea(KWin.MaximizeArea, w), g = w.frameGeometry;
    return g.x === a.x && g.y === a.y && g.width === a.width && g.height === a.height;
}
function info(w) {
    const g = w.frameGeometry, c = w.clientGeometry;
    return {id: w.internalId.toString(), class: String(w.resourceClass), name: String(w.resourceName),
            desktop_file: String(w.desktopFileName || ""), title: String(w.caption), pid: w.pid,
            x: g.x, y: g.y, width: g.width, height: g.height,
            client: {x: c.x, y: c.y, width: c.width, height: c.height},
            output: w.output ? w.output.name : null, active: w === workspace.activeWindow,
            minimized: w.minimized, maximized: maximized(w), fullscreen: w.fullScreen, keepAbove: w.keepAbove,
            normal: w.normalWindow, workspace: w.desktops.map(d => d.name)};
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
callDBus(BUS, "/", "org.claude.KWinBridge", "result", JSON.stringify(out));
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
    fd, path = tempfile.mkstemp(suffix=".js", prefix="claude-kwin-")
    name = f"claude-lcu-window-{os.getpid()}"
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
    before = {w["id"] for w in run("list", all_windows=True)["windows"]}
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    win, end = None, time.monotonic() + 20
    while not win and time.monotonic() < end:
        time.sleep(0.2)
        fresh = [w for w in run("list")["windows"] if w["id"] not in before]
        if match:
            ids = {w["id"] for w in run("info", match)["windows"]}
            fresh = [w for w in fresh if w["id"] in ids]
        win = fresh[0] if fresh else None
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


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "launch":  # before flag stripping: CMD may contain --first/--all
        return launch(argv[1:])
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
    else:
        if len(argv) < 2:
            sys.exit("need a MATCH, see --help")
        res = run(action, argv[1], argv[2:], first=first, all_windows=all_w)
    print(json.dumps(res["windows"] if res["ok"] else res, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
