"""Pointer drags on window frames for COSMIC: drag-move by the header, drag-resize by an edge.

cosmic-comp has no protocol request to move or resize a window, no input hit test, and no
moving/resizing state: while a window is held it sends no geometry at all (a new connection
sees none, an open one gets nothing until the release). So, unlike KDE, nothing can be
checked or corrected during a drag. These commands raise the window, refuse presses that
could reach a panel or leave the outputs, and verify the result after the release.
"""
import json
import math
import os
import re
import sys
import time
from pathlib import Path

from ccu_common import Desktop, public

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EDGES = ("left", "right", "top", "bottom", "top-left", "top-right", "bottom-left", "bottom-right")
# Press-to-release duration of a window drag (s), the same as on KDE
DRAG_SPEEDS = {"--fast": 0.1, "--normal": 0.4, "--slow": 1.0}
# Logical thickness of a COSMIC panel by its `size`. Only M is measured (56 px at scales 1.25
# and 1.5, 2026-11-02); other sizes get a band at least as thick as they can be.
PANEL_BAND = {"M": 56}
PANEL_BAND_UNKNOWN = 96
# cosmic-comp's resize zone reaches outside every floating window (SSD, GTK and libcosmic
# CSD alike): a press 3 px outside the frame resized all eight handles of each.
RESIZE_OUTSIDE = 3


def _fail(msg, **state):
    print(json.dumps({"ok": False, "error": msg, **state}, indent=1))
    sys.exit(1)


def _ron(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def panels():
    """[(anchor, output or None for all, band px)] for the panels and docks cosmic-panel shows."""
    roots = [Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "cosmic", Path("/usr/share/cosmic")]
    def read(name, key):
        return next((v for v in (_ron(r / name / "v1" / key) for r in roots) if v is not None), None)
    names = re.findall(r'"([^"]+)"', read("com.system76.CosmicPanel", "entries") or "")
    res = []
    for n in names:
        d = f"com.system76.CosmicPanel.{n}"
        anchor = (read(d, "anchor") or "Bottom").lower()
        out = re.search(r'Name\("([^"]+)"\)', read(d, "output") or "")
        size = (read(d, "size") or "").strip()
        margin = int(m.group()) if (m := re.search(r"\d+", read(d, "margin") or "")) else 0
        res.append((anchor, out.group(1) if out else None, PANEL_BAND.get(size, PANEL_BAND_UNKNOWN) + margin))
    return res


def usable(o, bands):
    """(x, y, w, h) of output o minus the panels anchored on it."""
    x, y, w, h = o.x, o.y, o.width, o.height
    for anchor, out, band in bands:
        if out not in (None, o.name):
            continue
        if anchor == "bottom":
            h -= band
        elif anchor == "top":
            y, h = y + band, h - band
        elif anchor == "left":
            x, w = x + band, w - band
        elif anchor == "right":
            w -= band
    return x, y, w, h


def _one(match):
    d = Desktop()
    hits = d.find(match)
    if len(hits) != 1:
        d.close()
        _fail("needs exactly one window; use its id" if hits else f"no window matches {match!r}")
    w = public(hits[0])
    bands = panels()
    areas = [(o, usable(o, bands)) for o in d.outputs]
    d.close()
    if w["minimized"] or w["maximized"] or w["fullscreen"]:
        _fail("needs a normal, visible, unmaximized window: unmaximize/unfullscreen/unminimize it first", window=w)
    if w["x"] is None:
        _fail("the window reports no geometry (another drag may still be holding it)", window=w)
    return w, areas


def _current(wid):
    d = Desktop()
    hits = d.find(f"id:{wid}")
    d.close()
    if not hits:
        _fail("target window disappeared")
    return public(hits[0])


def _settled(wid, timeout=3):
    """The window once its geometry is reported and unchanged for 0.3 s."""
    last, since, end = None, time.monotonic(), time.monotonic() + timeout
    while True:
        w = _current(wid)
        geo = (w["x"], w["y"], w["width"], w["height"])
        if geo != last:
            last, since = geo, time.monotonic()
        elif w["x"] is not None and time.monotonic() - since >= 0.3 or time.monotonic() > end:
            return w
        time.sleep(0.05)


def _pressable(x, y, areas):
    """None if a press at x,y lands on the usable part of an output; else why not."""
    for o, (ux, uy, uw, uh) in areas:
        if o.x <= x < o.x + o.width and o.y <= y < o.y + o.height:
            if ux <= x < ux + uw and uy <= y < uy + uh:
                return None
            return f"{x:g},{y:g} is on a panel of {o.name}"
    return f"{x:g},{y:g} is on no output"


def _raise(wid):
    d = Desktop()
    hits = d.find(f"id:{wid}")
    if hits:
        d.act(hits[0], "activate")
    d.close()
    time.sleep(0.25)


def _size_kept(before, after):
    """Logical size is whole physical pixels over the monitor scale: crossing onto a monitor
    with another scale can change it by about a pixel without a resize."""
    tolerance = 1 if after.get("output") == before.get("output") else 2
    return all(abs(after[k] - before[k]) < tolerance for k in ("width", "height"))


def drag_move(argv):
    """drag-move MATCH X Y --grab GX GY [--fast|--slow|--duration MS]"""
    pos, grab, duration = [], None, DRAG_SPEEDS["--normal"]
    it = iter(argv)
    for arg in it:
        if arg == "--grab":
            grab = (next(it, None), next(it, None))
        elif arg in DRAG_SPEEDS:
            duration = DRAG_SPEEDS[arg]
        elif arg == "--duration":
            try:
                duration = float(next(it, "")) / 1000
            except ValueError:
                _fail("--duration needs a number of milliseconds")
            if not math.isfinite(duration) or duration < 0.05:
                _fail("--duration must be at least 50 ms")
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
    original, areas = _one(pos[0])
    wid = original["id"]
    # no client/frame split on COSMIC: a header is at most ~64 px tall in every toolkit
    if not (6 <= gx <= original["width"] - 6 and 6 <= gy <= min(64, original["height"] - 6)):
        _fail("--grab must be in the header (6..64 px from the top), away from borders; verify a blank point "
              "visually", window=original)

    def fits(x, y):
        return any(x >= ux + 16 and y >= uy + 16 and x + original["width"] <= ux + uw - 16 and
                   y + original["height"] <= uy + uh - 16 for _, (ux, uy, uw, uh) in areas)

    if not fits(tx, ty):
        _fail("destination must fit at least 16 px inside one output's usable area (closer, cosmic-comp may "
              "tile or snap it)", window=original)
    if max(abs(tx - original["x"]), abs(ty - original["y"])) < 1:
        print(json.dumps({"ok": True, "changed": False, "window": original}, indent=1))
        return 0
    _raise(wid)
    w = _current(wid)
    if w["x"] is None or any(abs(w[k] - original[k]) >= 1 for k in ("x", "y", "width", "height")):
        _fail("window geometry changed before the drag; inspect it again", window=w)
    px, py = w["x"] + gx, w["y"] + gy
    if why := _pressable(px, py, areas):
        _fail(f"grab point not pressable: {why}", window=w)
    dx, dy = tx - w["x"], ty - w["y"]
    dist = max(abs(dx), abs(dy))
    initial = (16 * dx / dist, 16 * dy / dist)
    from input import Input
    inp = Input()
    try:
        inp.move(px, py, settle=True)
        time.sleep(0.15)
        inp.button("left", True)
        t0 = time.monotonic()
        time.sleep(0.01)
        for i in range(1, 5):  # cross the drag threshold in small moves, as a hand does
            cx, cy = px + initial[0] * i / 4, py + initial[1] * i / 4
            inp.move(cx, cy)
            time.sleep(0.005)
        # The window follows the pointer without lag on COSMIC, and nothing reports where it is
        # until the release: glide straight to the target, paced by the clock.
        ex, ey = tx + gx, ty + gy
        sx, sy, s0 = cx, cy, time.monotonic()
        span = max(0.0, t0 + duration - 0.03 - s0)
        f = 0.0
        while f < 1:  # each move goes where the pointer should be now, so slow moves cannot add up
            time.sleep(0.004)
            f = min(1.0, (time.monotonic() - s0) / span) if span else 1.0
            inp.move(sx + (ex - sx) * f, sy + (ey - sy) * f)
        time.sleep(max(0.0, t0 + duration - time.monotonic()))
    finally:
        try:
            released = time.monotonic()
            inp.button("left", False)
        finally:
            inp.close()
    final = _settled(wid)
    reached = final["x"] is not None and max(abs(final["x"] - tx), abs(final["y"] - ty)) < 1
    preserved = final["x"] is not None and _size_kept(original, final)
    ok = reached and preserved and not final["maximized"] and not final["fullscreen"]
    print(json.dumps({"ok": ok, "changed": final["x"] is not None and (final["x"], final["y"]) != (original["x"], original["y"]),
                      "from": [original["x"], original["y"]], "to": [final["x"], final["y"]], "target": [tx, ty],
                      "grab": [gx, gy], "size_preserved": preserved, "drag_seconds": round(released - t0, 3),
                      "window": final,
                      "note": None if ok else "target not reached or size/state changed: the grab may have missed the "
                      "header, or cosmic-comp tiled/snapped it; inspect the window"}, indent=1))
    return 0 if ok else 3


def drag_resize(argv):
    """drag-resize MATCH W H [--edge E] [--left] [--top] [--step PX]"""
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
        elif a in ("--left", "--top"):
            opts.add(a)
        elif a.startswith("--"):
            _fail(f"unknown option {a}")
        else:
            pos.append(a)
    if len(pos) != 3:
        _fail("drag-resize needs MATCH W H")
    if edge and edge not in EDGES:
        _fail(f"--edge must be one of {', '.join(EDGES)}")
    try:
        tw, th = float(pos[1]), float(pos[2])
    except ValueError:
        _fail("W and H must be numbers")
    if not all(math.isfinite(v) and v > 0 for v in (tw, th, step)):
        _fail("W, H and --step must be finite positive numbers")
    if step > 8:
        _fail("--step must be at most 8 px")
    w0, areas = _one(pos[0])
    wid = w0["id"]
    _, (ax, ay, aw, ah) = next(((o, a) for o, a in areas if o.name == w0["output"]), (None, (None,) * 4))
    if ax is None:
        _fail("the window is on no output", window=w0)
    ax2, ay2 = ax + aw, ay + ah
    dw, dh = abs(tw - w0["width"]) >= 1, abs(th - w0["height"]) >= 1
    if edge:  # the caller picked the handle: the other edges stay put
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
    if hside == "right" and w0["x"] + tw > ax2 or hside == "left" and w0["x"] + w0["width"] - tw < ax:
        _fail(f"width {tw:g} does not fit in the usable area of {w0['output']} with the {hside} edge moving", window=w0)
    if vside == "bottom" and w0["y"] + th > ay2 or vside == "top" and w0["y"] + w0["height"] - th < ay:
        _fail(f"height {th:g} does not fit in the usable area of {w0['output']} with the {vside} edge moving", window=w0)
    if not hside and not vside:
        print(json.dumps({"ok": True, "changed": False, "window": w0}, indent=1))
        return 0
    from input import Input
    log = []

    def press_point(w, sides):
        x, y = w["x"] + w["width"] / 2, w["y"] + w["height"] / 2
        if "left" in sides:
            x = w["x"] - RESIZE_OUTSIDE
        if "right" in sides:
            x = w["x"] + w["width"] - 1 + RESIZE_OUTSIDE
        if "top" in sides:
            y = w["y"] - RESIZE_OUTSIDE
        if "bottom" in sides:
            y = w["y"] + w["height"] - 1 + RESIZE_OUTSIDE
        return x, y

    def one_drag(inp, sides, dx, dy):
        w = _current(wid)
        gx, gy = press_point(w, sides)
        if why := _pressable(gx, gy, areas):
            return (f"the {'-'.join(sides)} edge's resize zone is not pressable ({why}); move the window first "
                    "or use another --edge")
        # approach from 12 px inside: client-decorated toolkits pick the edge from motion over them
        ix = gx + (12 if "left" in sides else -12 if "right" in sides else 0)
        iy = gy + (12 if "top" in sides else -12 if "bottom" in sides else 0)
        inp.move(ix, iy, settle=True)
        time.sleep(0.1)
        inp.move(gx, gy, settle=True)
        time.sleep(0.2)
        inp.button("left", True)
        time.sleep(0.25)
        n = max(1, math.ceil(max(abs(dx), abs(dy)) / step))
        for i in range(1, n + 1):
            inp.move(gx + dx * i / n, gy + dy * i / n)
            time.sleep(0.025)
        time.sleep(0.3)
        inp.button("left", False)
        log.append({"press": [gx, gy], "to": [gx + dx, gy + dy]})
        return None

    _raise(wid)
    inp = Input()
    try:
        passes, stopped = 0, set()
        while passes < 3:
            w = _settled(wid)
            ddx = (tw - w["width"]) if hside and "w" not in stopped else 0
            ddy = (th - w["height"]) if vside and "h" not in stopped else 0
            ddx, ddy = (ddx if abs(ddx) >= 1 else 0), (ddy if abs(ddy) >= 1 else 0)
            if not ddx and not ddy:
                break
            passes += 1
            sides = tuple(s for s, d in ((hside, ddx), (vside, ddy)) if d)
            why = one_drag(inp, sides, -ddx if hside == "left" else ddx, -ddy if vside == "top" else ddy)
            if why:
                _fail(why, window=w, attempts=log)
            after = _settled(wid)
            if ddx and abs(after["width"] - w["width"]) < 1:
                stopped.add("w")
            if ddy and abs(after["height"] - w["height"]) < 1:
                stopped.add("h")
            if after["width"] == w["width"] and after["height"] == w["height"]:
                break  # nothing resized: do not press again where nothing happened
    finally:
        try:
            inp.button("left", False)
        finally:
            inp.close()
    w = _settled(wid)
    short = {k: v for k, v in (("width", tw - w["width"]), ("height", th - w["height"])) if abs(v) >= 1}
    note = None
    if short:
        note = (f"stopped {', '.join(f'{v:+g} px short in {k}' for k, v in short.items())}: target not reached; "
                "the press may have missed the resize zone, or the app's size limits, size increments or "
                "cosmic-comp snapping stopped it")
    print(json.dumps({"ok": not short, "changed": (w["width"], w["height"]) != (w0["width"], w0["height"]),
                      "from": [w0["width"], w0["height"]], "to": [w["width"], w["height"]], "target": [tw, th],
                      "note": note, "attempts": log, "window": w}, indent=1))
    return 0 if not short else 3
