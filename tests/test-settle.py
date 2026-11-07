#!/usr/bin/python3 -s
"""Offline check of `capture shot --settle` logic (scripts/settle.py): no desktop, fake clock and frames.
  /usr/bin/python3 -s tests/test-settle.py     Expected: every line `ok`, exit 0."""
import sys
import tempfile
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import settle  # noqa: E402

fails = 0


def check(name, cond, detail=""):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    fails += not cond


def picture(path, color, w=200, h=200, box=None):
    """Solid colour, optionally with box=(x, y, bw, bh, colour) drawn on top."""
    rows = bytearray(bytes(color) * w * h)
    if box:
        x, y, bw, bh, c = box
        for yy in range(y, y + bh):
            for xx in range(x, x + bw):
                rows[(yy * w + xx) * 3:(yy * w + xx) * 3 + 3] = bytes(c)
    GdkPixbuf.Pixbuf.new_from_data(bytes(rows), GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3).savev(str(path), "png", [], [])


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def nap(self, s):
        self.t += s


def run(script, grab_s=0.1, **kw):
    """script(t) -> picture args at time t; each grab costs grab_s."""
    c = Clock()

    def grab(path):
        c.t += grab_s
        picture(path, *script(c.t))
        return "r"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.png"
        if kw.get("since_color"):
            picture(Path(td) / "prev.png", kw.pop("since_color"))
            kw["since"] = str(Path(td) / "prev.png")
        _, info = settle.wait(grab, out, clock=c, nap=c.nap, **kw)
        return info, settle.load(out)[4][:3]


RED, GREEN, BLUE = (200, 0, 0), (0, 200, 0), (0, 0, 200)
a = settle.load
with tempfile.TemporaryDirectory() as td:
    p, q = Path(td) / "p.png", Path(td) / "q.png"
    picture(p, RED)
    picture(q, RED)
    check("equal frames have no changed box", settle.changed_box(a(p), a(q)) is None)
    picture(q, RED, box=(150, 20, 10, 5, BLUE))
    check("changed box is exact", settle.changed_box(a(p), a(q)) == (150, 20, 160, 25), settle.changed_box(a(p), a(q)))
    picture(q, RED, w=100)
    check("a size change counts as a change", settle.moved(a(p), a(q)))
    picture(q, RED, box=(10, 10, 2, 18, BLUE))
    check("a caret-sized change is not movement", not settle.moved(a(p), a(q)))
    picture(q, RED, box=(10, 10, 32, 32, BLUE))
    check("a spinner-sized change is movement", settle.moved(a(p), a(q)))
    check("the size limit is in logical px", not settle.moved(a(p), a(q), px_per_logical=2))

i, px = run(lambda t: (GREEN,))
check("a still picture settles after the quiet time", i["settled"] and 0.4 <= i["waited_s"] <= 0.8, i)
check("still picture: no changed field without --since", "changed" not in i)

i, px = run(lambda t: (BLUE if int(t * 20) % 2 else RED,) if t < 2 else (GREEN,))
check("waits out an animation and keeps the final frame", i["settled"] and i["waited_s"] >= 2.4 and tuple(px) == GREEN, (i, px))

i, px = run(lambda t: (BLUE if int(t * 20) % 2 else RED,), timeout=1.5)
check("never still: times out, settled false", not i["settled"] and 1.5 <= i["waited_s"] <= 1.8, i)

i, px = run(lambda t: (RED,) if t < 1.0 else (GREEN,), since_color=RED)
check("--since waits for a late change", i["settled"] and i["changed"] and tuple(px) == GREEN and i["waited_s"] >= 1.3, (i, px))

i, px = run(lambda t: (RED,) if t < 1.0 else (GREEN,))
check("without --since a late change is missed (documented limit)", i["settled"] and tuple(px) == RED, (i, px))

i, px = run(lambda t: (RED,), since_color=RED, timeout=1.0)
check("--since with no change: times out, changed false", not i["settled"] and i["changed"] is False, i)

i, px = run(lambda t: (RED, 200, 200, (10, 10, 2, 18, BLUE if int(t * 4) % 2 else RED)))
check("a blinking caret does not block settling", i["settled"], i)

i, px = run(lambda t: (GREEN,), quiet=0.0)
check("quiet 0 still compares two frames", i["settled"] and i["frames"] == 2, i)

print("self-check:", "all passed" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
