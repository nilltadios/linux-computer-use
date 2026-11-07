#!/usr/bin/python3
"""Screenshots and screen recordings on COSMIC (cosmic-comp), with no dialog.

  lcu capture screens                              # monitor layout (logical px), scale
  lcu capture shot OUT.png                         # whole desktop
  lcu capture shot OUT.png --screen DP-1           # one monitor, native pixels
  lcu capture shot OUT.png --area X Y W H          # logical desktop pixels
  lcu capture shot OUT.png --window class:com.system76.CosmicFiles [--no-raise]
  lcu capture shot OUT.png --window MATCH --own    # the window's own pixels, even if covered
  lcu capture shot OUT.png --pointer ...           # include the cursor

  lcu capture record OUT.webm [--seconds 10] [--fps 30] [--screen DP-1 | --area X Y W H | --window MATCH]
      Real-time video: frames from ext-image-copy-capture piped into ffmpeg. --window
      records the window's own pixels (follows it, not hidden by windows on top). Default:
      the monitor of the active window. Stops after --seconds or on SIGINT/SIGTERM.
  lcu capture frames OUT.mp4 --seconds 10 ...     # the same at 2 fps (evidence, small files)
  lcu capture record-setup                        # nothing to grant on COSMIC; checks recording

Everything goes through the ext-image-copy-capture-v1 Wayland protocol, which cosmic-comp
offers to every ordinary client: no portal, no dialog, no extension. A monitor is captured
at its own resolution (sharp); --area inside one monitor is cropped from it; the whole
desktop, or an area across monitors, is assembled at the largest monitor scale, so
lower-scale monitors in it are upscaled and soft. --window raises the window, crops it
from its monitor at native resolution and gives focus back; --own captures the window
surface itself (works when covered, but cosmic-comp renders it at 1 px per logical px).
While the screen is locked cosmic-comp does not deliver frames: the call times out.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

sys.path.insert(1, str(Path(__file__).resolve().parent.parent))
import settle  # noqa: E402
from ccu_common import SHM_ORDER, CaptureSession, Desktop, pixbuf  # noqa: E402


def grab_output(desk, out, pointer):
    s = CaptureSession(desk, output=out, pointer=pointer)
    try:
        raw = s.frame()
        if raw is None:
            sys.exit("no frame within 5 s (is the screen locked?)")
        if s.transform:
            print(f"warning: output {out.name} has transform {s.transform}; image is not rotated back",
                  file=sys.stderr)
        return pixbuf(raw, s.size, SHM_ORDER[s.fmt])
    finally:
        s.close()


def grab_window_own(desk, w, pointer):
    s = CaptureSession(desk, window=w, pointer=pointer)
    try:
        raw = s.frame()
        if raw is None:
            sys.exit("no frame within 5 s (window not mapped, or the screen is locked)")
        return pixbuf(raw, s.size, SHM_ORDER[s.fmt])
    finally:
        s.close()


def crop_from(pb, out, region):
    """Cut logical `region` out of output `out`'s native-resolution image."""
    f = pb.get_width() / out.width
    x, y, w, h = region
    x0, y0 = max(0, round((x - out.x) * f)), max(0, round((y - out.y) * f))
    x1 = min(pb.get_width(), round((x - out.x + w) * f))
    y1 = min(pb.get_height(), round((y - out.y + h) * f))
    if x1 <= x0 or y1 <= y0:
        sys.exit(f"area {region} is outside {out.name}")
    return pb.new_subpixbuf(x0, y0, x1 - x0, y1 - y0).copy(), f


def assemble(desk, region, pointer):
    """Region across monitors (None = whole desktop) at the largest scale."""
    region = region or desk.bounds()
    rx, ry, rw, rh = region
    outs = [o for o in desk.outputs if o.x < rx + rw and rx < o.x + o.width and o.y < ry + rh and ry < o.y + o.height]
    if not outs:
        sys.exit(f"area {region} is outside the desktop {desk.bounds()}")
    f = max(o.scale for o in outs)
    dst = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, round(rw * f), round(rh * f))
    dst.fill(0x000000ff)
    for o in outs:
        pb = grab_output(desk, o, pointer)
        k = f * o.width / pb.get_width()  # source px -> destination px
        ox, oy = (o.x - rx) * f, (o.y - ry) * f
        # clip the output's rectangle to the destination
        dx0, dy0 = max(0, round(ox)), max(0, round(oy))
        dx1 = min(dst.get_width(), round(ox + o.width * f))
        dy1 = min(dst.get_height(), round(oy + o.height * f))
        if dx1 > dx0 and dy1 > dy0:
            pb.scale(dst, dx0, dy0, dx1 - dx0, dy1 - dy0, ox, oy, k, k, GdkPixbuf.InterpType.BILINEAR)
    return dst, f, list(region)


def still(desk, args):
    """-> (pixbuf, pixels_per_logical, logical_region, extra info)."""
    extra = {}
    if args.screen:
        o = desk.output(args.screen)
        pb = grab_output(desk, o, args.pointer)
        return pb, pb.get_width() / o.width, list(o.geometry()), extra
    if args.window:
        w = desk.find_one(args.window)
        extra = {"window": w["id"], "title": w["title"]}
        if args.own:
            pb = grab_window_own(desk, w, args.pointer)
            return pb, pb.get_width() / w["width"] if w["width"] else 1, \
                [w["x"], w["y"], w["width"], w["height"]], extra
        prev = desk.active()
        raised = False
        if not args.no_raise and not w["active"]:
            desk.act(w, "activate")
            raised = True
            time.sleep(0.35)  # let the compositor draw the raised window
            desk = Desktop()
            w = desk.find_one(f"id:{w['id']}")
        if w["x"] is None:
            sys.exit("the compositor reported no geometry for this window (minimized?)")
        region = (w["x"], w["y"], w["width"], w["height"])
        try:
            o = desk.output_containing(region)
            if o:
                pb = grab_output(desk, o, args.pointer)
                pb, f = crop_from(pb, o, region)
                return pb, f, list(region), extra
            pb, f, region = assemble(desk, region, args.pointer)
            return pb, f, region, extra
        finally:
            if raised and prev:
                d2 = Desktop()
                back = d2.find(f"id:{prev[0]['id']}")
                if back:
                    d2.act(back[0], "activate")
    if args.area:
        region = tuple(args.area)
        o = desk.output_containing(region)
        if o:
            pb, f = crop_from(grab_output(desk, o, args.pointer), o, region)
            return pb, f, list(region), extra
        return assemble(desk, region, args.pointer) + (extra,)
    return assemble(desk, None, args.pointer) + (extra,)


def cmd_screens(args):
    desk = Desktop(windows=False)
    print(json.dumps([o.as_dict() for o in sorted(desk.outputs, key=lambda o: (o.x, o.y))], indent=1))


def cmd_shot(args):
    desk = Desktop()
    if settle.wanted(args):
        # Raise once, not per frame: still() would otherwise flip focus back and forth on every grab.
        prev, raised = desk.active(), False
        if args.window and not args.no_raise and not args.own:
            w = desk.find_one(args.window)
            if not w["active"]:
                desk.act(w, "activate")
                raised = True
                time.sleep(0.35)
            args.no_raise = True

        def one(path):
            res = still(Desktop(), args)
            res[0].savev(str(path), "png", [], [])
            return res
        try:
            (pb, f, region, extra), info = settle.wait(one, args.out, args.settle_quiet, args.settle_timeout, args.since,
                                                       scale=lambda r: r[1])
        finally:
            if raised and prev:
                d2 = Desktop()
                back = d2.find(f"id:{prev[0]['id']}")
                if back:
                    d2.act(back[0], "activate")
        extra = {**extra, "settle": info}
    else:
        pb, f, region, extra = still(desk, args)
        pb.savev(args.out, "png", [], [])
    print(json.dumps({"file": str(Path(args.out).resolve()), "size": [pb.get_width(), pb.get_height()],
                      "logical_region": region, "pixels_per_logical": round(f, 4), **extra}))


# --- recording ---------------------------------------------------------------------
def encoder(out):
    ext = Path(out).suffix.lower()
    if ext == ".webm":
        return ["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "6M"]
    return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"]  # .mp4 / .mkv


def cmd_record(args, fps=None):
    fps = fps or args.fps
    desk = Desktop()
    target = {}
    if args.window:
        w = desk.find_one(args.window)
        sess = CaptureSession(desk, window=w, pointer=args.pointer)
        target, crop = {"window": w["id"], "title": w["title"]}, None
    else:
        if args.screen:
            o = desk.output(args.screen)
        elif args.area:
            o = desk.output_containing(tuple(args.area))
            if not o:
                sys.exit("--area must lie inside one monitor for recording")
        else:
            act = desk.active()
            o = desk.output(act[0]["output"]) if act and act[0]["output"] else desk.outputs[0]
        sess = CaptureSession(desk, output=o, pointer=args.pointer)
        target = {"screen": o.name}
        crop = None
        if args.area:
            f = sess.size[0] / o.width
            x, y, w_, h_ = args.area
            crop = [round(w_ * f) // 2 * 2, round(h_ * f) // 2 * 2, round((x - o.x) * f), round((y - o.y) * f)]
            target = {"area": args.area, "screen": o.name}
    w, h = sess.size
    order = SHM_ORDER[sess.fmt]
    pix = {"RGBA": "rgba", "RGBX": "rgb0", "BGRA": "bgra", "BGRX": "bgr0"}[order]
    vf = f"crop={crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}," if crop else ""
    vf += "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", pix, "-s", f"{w}x{h}",
                           "-framerate", str(fps), "-i", "-", "-vf", vf, *encoder(args.out), "-pix_fmt", "yuv420p",
                           args.out], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    stop = []
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    print(json.dumps({"recording": str(Path(args.out).resolve()), "pid": os.getpid()}), flush=True)
    # constant frame rate: at each tick write the newest completed frame and ask for the next
    # one (repeating the last frame when none completed, e.g. nothing on screen changed)
    period, t0, n, last, frames_new = 1 / fps, time.monotonic(), 0, None, 0
    frame_obj, state = None, {}

    def request():
        nonlocal frame_obj
        state.clear()
        frame_obj = sess.session.create_frame()
        frame_obj.on("ready", lambda: state.__setitem__("ok", 1))
        frame_obj.on("failed", lambda r: state.__setitem__("fail", r))
        frame_obj.attach_buffer(sess.buffer)
        frame_obj.damage_buffer(0, 0, w, h)
        frame_obj.capture()
    request()
    try:
        while not stop and time.monotonic() - t0 < args.seconds:
            due = t0 + n * period
            while time.monotonic() < due:
                sess.c.dispatch(max(0, min(due - time.monotonic(), 0.01)))
            if state.get("fail") is not None:
                if state["fail"] == 2 or args.window:
                    break  # source gone (window closed)
                frame_obj.destroy()
                request()
            elif state.get("ok"):
                last = sess.map[:]
                frames_new += 1
                frame_obj.destroy()
                request()
            if last is not None:
                # if we fell behind (slow encoder), repeat the frame so video time stays wall time
                for _ in range(max(1, int((time.monotonic() - t0) / period) + 1 - n)):
                    ff.stdin.write(last)
                    n += 1
            elif time.monotonic() - t0 > 5:
                sys.exit("no frame within 5 s (is the screen locked?)")
            else:
                sess.c.dispatch(0.01)
    except BrokenPipeError:
        pass
    finally:
        try:
            ff.stdin.close()
        except BrokenPipeError:
            pass
        ff.wait(timeout=60)
        sess.close()
    if ff.returncode or not Path(args.out).exists():
        sys.exit(f"ffmpeg failed: {ff.stderr.read().decode()[-800:]}")
    print(json.dumps({"file": str(Path(args.out).resolve()), **target, "size": [w, h], "fps": fps,
                      "frames": n, "distinct_frames": frames_new, "seconds": round(n / fps, 2)}))


def cmd_record_setup(args):
    print("COSMIC needs no screen-share grant: recording uses ext-image-copy-capture directly. Testing 1 s...")
    out = Path(os.environ.get("TMPDIR", "/tmp")) / f"ccu-record-test-{os.getpid()}.mp4"
    r = subprocess.run([sys.executable, __file__, "record", str(out), "--seconds", "1"], capture_output=True, text=True)
    ok = r.returncode == 0 and out.exists()
    out.unlink(missing_ok=True)
    print("ok" if ok else f"failed: {r.stderr.strip()}")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("shot", "frames", "record"):
        p = sub.add_parser(name)
        p.add_argument("out")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--screen")
        g.add_argument("--area", type=float, nargs=4, metavar=("X", "Y", "W", "H"))
        g.add_argument("--window", metavar="MATCH", help="see `lcu window --help` for MATCH syntax")
        if name == "shot":
            p.add_argument("--no-raise", action="store_true", help="crop where the window is without raising it")
            p.add_argument("--own", action="store_true", help="the window's own surface (works when covered, 1x)")
            settle.add_args(p)
        p.add_argument("--pointer", action="store_true")
        if name != "shot":
            p.add_argument("--seconds", type=float, default=10)
        if name == "record":
            p.add_argument("--fps", type=int, default=30)
    sub.add_parser("record-setup", help="checks recording; no grant is needed on COSMIC")
    sub.add_parser("screens", help="monitor layout in logical px")
    args = ap.parse_args()
    if args.cmd in ("record", "frames") and not shutil.which("ffmpeg"):
        sys.exit("recording needs ffmpeg")
    if args.cmd == "frames":
        return cmd_record(args, fps=2)
    {"shot": cmd_shot, "record": cmd_record, "record-setup": cmd_record_setup, "screens": cmd_screens}[args.cmd](args)


if __name__ == "__main__":
    main()
