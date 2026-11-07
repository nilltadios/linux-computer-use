"""`capture shot --settle`: wait until the picture stops changing, instead of a fixed sleep.

Shared by the desktop backends. grab(path) writes one still and returns the backend's own
result. Frames are compared to each other, so this needs no help from the app.

  settled   the last frames matched for --settle-quiet seconds
  changed   with --since PREV.png: whether the picture ever differed from PREV.png

A change smaller than TINY_LOGICAL_PX (a blinking caret) does not count as movement.
Without --since, an app that starts changing only after the quiet time looks settled.
"""
import shutil
import sys
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

TINY_LOGICAL_PX = 400  # 20x20 logical: covers a caret, not a spinner


def add_args(p):
    p.add_argument("--settle", action="store_true", help="wait until the picture stops changing, then keep that frame")
    p.add_argument("--since", metavar="PREV.png", help="also wait until the picture differs from PREV.png (same region); implies --settle")
    p.add_argument("--settle-quiet", type=float, default=0.4, metavar="S", help="how long it must stay unchanged (default 0.4)")
    p.add_argument("--settle-timeout", type=float, default=10, metavar="S", help="give up after this long and keep the last frame (default 10)")


def wanted(args):
    return bool(getattr(args, "settle", False) or getattr(args, "since", None))


def load(path):
    pb = GdkPixbuf.Pixbuf.new_from_file(str(path))
    return pb.get_width(), pb.get_height(), pb.get_rowstride(), pb.get_n_channels(), pb.get_pixels()


def changed_box(a, b):
    """Bounding box (x0, y0, x1, y1) of the pixels that differ; None if equal; whole frame if the sizes differ."""
    if a[:2] != b[:2] or a[3] != b[3]:
        return (0, 0, max(a[0], b[0]), max(a[1], b[1]))
    if a[4] == b[4]:
        return None
    w, h, stride, nch = a[:4]
    rows = [y for y in range(h) if a[4][y * stride:y * stride + w * nch] != b[4][y * stride:y * stride + w * nch]]
    if not rows:  # only the padding at the row ends differs
        return None
    x0, x1 = w, 0
    for y in rows:
        ra, rb = a[4][y * stride:y * stride + w * nch], b[4][y * stride:y * stride + w * nch]
        if ra == rb:
            continue
        xor = int.from_bytes(ra, "little") ^ int.from_bytes(rb, "little")
        x0 = min(x0, (((xor & -xor).bit_length() - 1) // 8) // nch)
        x1 = max(x1, ((xor.bit_length() - 1) // 8) // nch + 1)
    return x0, rows[0], x1, rows[-1] + 1


def moved(a, b, px_per_logical=1.0):
    box = changed_box(a, b)
    if box is None:
        return False
    area = (box[2] - box[0]) * (box[3] - box[1]) / (px_per_logical ** 2 or 1)
    return area > TINY_LOGICAL_PX


def wait(grab, out, quiet=0.4, timeout=10.0, since=None, scale=None, clock=time.monotonic, nap=time.sleep):
    """Grab until settled; the last frame ends up in out. -> (grab's last result, info dict).

    scale(result) -> pixels per logical px of that frame (default 1)."""
    prev_img = None
    if since:
        try:
            prev_img = load(since)
        except Exception as e:  # GLib errors, missing file: refuse before spending the timeout
            sys.exit(f"--since {since}: cannot read it: {e}")
    t0 = clock()
    changed = False if since else None
    last, result, quiet_from, frames, settled = None, None, None, 0, False
    with tempfile.TemporaryDirectory(prefix="lcu-settle-") as td:
        kept = Path(td) / "frame.png"
        while True:
            cur = Path(td) / f"f{frames}.png"
            taken = clock()
            result = grab(cur)
            frame, frames = load(cur), frames + 1
            shutil.move(cur, kept)
            f = scale(result) if scale else 1.0
            if since and not changed:
                changed = moved(prev_img, frame, f)
            if last is None or moved(last, frame, f):
                quiet_from = taken
            last = frame
            now = clock()
            if (changed is not False) and frames > 1 and now - quiet_from >= quiet:
                settled = True
                break
            if now - t0 >= timeout:
                break
            nap(0.05)
        shutil.copyfile(kept, out)
    info = {"settled": settled, "waited_s": round(clock() - t0, 2), "frames": frames}
    if since:
        info["changed"] = changed
    if not settled:
        why = "it never differed from " + str(since) if since and not changed else "it was still changing"
        print(f"lcu capture: not settled after {info['waited_s']} s ({why}); the image is the last frame", file=sys.stderr)
    return result, info
