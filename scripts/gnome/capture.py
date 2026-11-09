#!/usr/bin/python3
"""Screenshots and screen recordings on GNOME Wayland, with no dialog.

  lcu capture screens                               # monitor layout (logical px), primary
  lcu capture shot OUT.png                          # whole desktop
  lcu capture shot OUT.png --screen DP-1            # one monitor
  lcu capture shot OUT.png --area X Y W H           # logical desktop pixels
  lcu capture shot OUT.png --window class:org.gnome.Nautilus [--no-raise]
  lcu capture shot OUT.png --pointer ...            # include the cursor
  lcu capture shot OUT.png --screencast ...         # force the ScreenCast path

  lcu capture record OUT.webm [--seconds 10] [--screen DP-1 | --area X Y W H | --window MATCH | --all]
      Real-time video from Mutter's ScreenCast API (PipeWire -> GStreamer). No portal,
      no grant: --screen records that monitor, --area exactly that area, --window that
      window's own contents (follows it when moved, even if covered), --all every monitor
      in one video placed like the desktop (black where no monitor is), scaled to fit
      3840x2160. Default: the monitor of the active window. .webm is VP8; .mp4 is H.264
      (libx264 or OpenH264, converted after recording). Stops after --seconds or on SIGINT/SIGTERM.

  lcu capture frames OUT.mp4 --seconds 10 [--screen|--area|--window ...]
      Repeated stills (a few fps) joined with ffmpeg. For "what happened" evidence.

  lcu capture record-setup    # nothing to set up on GNOME; checks recording works

Stills come from the Computer Use Bridge extension (rendered inside the shell: fast, no
indicator). A region within one monitor is rendered at that monitor's own scale, so it
matches the screen pixel for pixel; the whole desktop (or an area across monitors) is
one image at the largest monitor scale, so lower-scale monitors in it are upscaled and
soft. Without the extension, `shot` falls back to one frame of a Mutter ScreenCast
(about 1 s; GNOME's screen-sharing indicator flashes) and --window is not available.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

sys.path.insert(1, str(Path(__file__).resolve().parent.parent))
import settle  # noqa: E402
from gcu_common import (BRIDGE, BRIDGE_HELP, ScreenCast, bridge, bridge_ok, desktop_bounds,  # noqa: E402
                        get_prop, native_scale, outputs, primary_output, windows)


# --- geometry -----------------------------------------------------------------
def window_geometry(match, activate):
    if not bridge_ok():
        sys.exit(BRIDGE_HELP)
    prev = windows("active")["windows"]
    if activate:
        windows("activate", match, first=True)
        time.sleep(0.35)  # let the shell repaint the raised window
    r = windows("info", match, first=True)
    if not r["ok"]:
        sys.exit(r["error"])
    return r["windows"][0], (prev[0]["id"] if prev else None)


def restore_focus(win_id):
    if win_id:
        windows("activate", f"id:{win_id}")


def region_for(args):
    """-> (x, y, w, h) logical or None for the whole desktop, a cleanup callable, the window."""
    if args.screen:
        outs = outputs()
        if args.screen not in outs:
            sys.exit(f"no output {args.screen}; have {', '.join(outs)}")
        return outs[args.screen], lambda: None, None
    if args.area:
        return tuple(args.area), lambda: None, None
    if args.window:
        w, prev = window_geometry(args.window, not args.no_raise)
        return ((w["x"], w["y"], w["width"], w["height"]),
                (lambda: restore_focus(prev)) if not args.no_raise else (lambda: None), w)
    return None, lambda: None, None


# --- stills -------------------------------------------------------------------
def grab_bridge(path, pointer=False):
    r = bridge("Screenshot", str(path), pointer, sig="(sb)", timeout=30000)
    if not r.get("ok") or not Path(path).exists():
        sys.exit(f"screenshot failed: {r.get('error')}")


def grab_area(path, region, scale, pointer=False):
    """Render one logical area at `scale` inside the shell (bridge version 3+)."""
    x, y, w, h = (round(v) for v in region)
    r = bridge("ScreenshotArea", str(path), x, y, w, h, float(scale), pointer, sig="(siiiidb)", timeout=30000)
    if not r.get("ok") or not Path(path).exists():
        sys.exit(f"area screenshot failed: {r.get('error')}")
    return (x, y, w, h)


def grab_screencast(path, region, pointer=False):
    """One frame of a Mutter ScreenCast of `region` (logical; None = whole desktop)."""
    sc = ScreenCast()
    x, y, w, h = region or desktop_bounds()
    sc.area(x, y, w, h, pointer)
    node = sc.start()
    try:
        r = subprocess.run(["gst-launch-1.0", "-q", "pipewiresrc", f"path={node}", "num-buffers=1", "always-copy=true",
                            "!", "videoconvert", "!", "pngenc", "!", "filesink", f"location={path}"],
                           capture_output=True, text=True, timeout=20)
    finally:
        sc.stop()
    if r.returncode or not Path(path).exists() or not Path(path).stat().st_size:
        sys.exit(f"screencast frame failed: {r.stderr.strip()[-400:]}")


def crop(src, dst, region, full_region):
    """Crop `region` out of an image that shows `full_region` (both logical)."""
    im = GdkPixbuf.Pixbuf.new_from_file(str(src))
    fx, fy, fw, fh = full_region
    f = im.get_width() / fw
    if region and tuple(region) != tuple(full_region):
        x, y, w, h = region
        x0, y0 = max(0, round((x - fx) * f)), max(0, round((y - fy) * f))
        x1, y1 = min(im.get_width(), round((x - fx + w) * f)), min(im.get_height(), round((y - fy + h) * f))
        if x1 <= x0 or y1 <= y0:
            sys.exit(f"area {region} is outside the desktop {full_region}")
        im = im.new_subpixbuf(x0, y0, x1 - x0, y1 - y0)
    im.savev(str(dst), "png", [], [])
    return [im.get_width(), im.get_height()], f


def still(path, region, pointer=False, screencast=False):
    """Grab `region` into path; -> (pixel size, pixels_per_logical).

    A region on one monitor is rendered at that monitor's own scale (sharp, 1:1 with its
    pixels). The whole desktop, or an area across monitors, comes out at the largest
    monitor scale, so the lower-scale monitors in it are upscaled and look soft."""
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "full.png"
        if not screencast and bridge_ok():
            scale = native_scale(region) if region else None
            if scale and get_prop(*BRIDGE, "Version") >= 3:
                return crop(raw, path, None, grab_area(raw, region, scale, pointer))
            grab_bridge(raw, pointer)
            return crop(raw, path, region, desktop_bounds())
        grab_screencast(raw, region, pointer)
        return crop(raw, path, None, region or desktop_bounds())


def cmd_screens(args):
    prim = primary_output()
    print(json.dumps([{"name": n, "x": g[0], "y": g[1], "width": g[2], "height": g[3], "primary": n == prim}
                      for n, g in outputs().items()], indent=1))


def cmd_shot(args):
    region, cleanup, _ = region_for(args)
    extra = {}
    one = lambda path: still(path, region, args.pointer, args.screencast)
    try:
        if settle.wanted(args):
            (size, f), info = settle.wait(one, args.out, args.settle_quiet, args.settle_timeout, args.since,
                                          scale=lambda r: r[1])
            extra = {"settle": info}
        else:
            size, f = one(args.out)
    finally:
        cleanup()  # hand focus back only after the grab, so the raised window is in the picture
    print(json.dumps({"file": str(Path(args.out).resolve()), "size": size, "logical_region": region,
                      "pixels_per_logical": round(f, 4), **extra}))


# --- low-fps recording ------------------------------------------------------------
def cmd_frames(args):
    region, cleanup, _ = region_for(args)
    td = Path(tempfile.mkdtemp(prefix="lcu-frames-"))
    try:
        end, n, t0, f = time.monotonic() + args.seconds, 0, time.monotonic(), 1
        while time.monotonic() < end:
            _, f = still(td / f"f{n:05d}.png", region, args.pointer)
            n += 1
        fps = max(n / (time.monotonic() - t0), 0.1)
        cleanup()
        vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2"  # frames are already cropped
        codec = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-row-mt", "1"] if args.out.endswith(".webm") \
            else ["-c:v", "libopenh264", "-b:v", "6M"]
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", f"{fps:.3f}", "-i", str(td / "f%05d.png"),
                        "-vf", vf, *codec, "-pix_fmt", "yuv420p", "-r", "10", args.out], check=True)
        print(json.dumps({"file": str(Path(args.out).resolve()), "frames": n, "fps": round(fps, 2),
                          "pixels_per_logical": round(f, 4)}))
    finally:
        shutil.rmtree(td, ignore_errors=True)


# --- real-time recording -----------------------------------------------------------
def h264_args():
    """libx264 when ffmpeg has it, else OpenH264 (on EL/Fedora the noopenh264 stub cannot encode)."""
    enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if " libx264 " in enc:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    return ["-c:v", "libopenh264", "-b:v", "12M"]


def cmd_record(args):
    sc = ScreenCast(recording=True)
    target, size = {}, None
    mp4 = args.out.lower().endswith(".mp4")
    td = Path(tempfile.mkdtemp(prefix="lcu-record-")) if mp4 else None
    raw = str(td / "raw.webm") if mp4 else args.out  # gst writes WebM; .mp4 is converted afterwards
    if args.screen:
        if args.screen not in outputs():
            sys.exit(f"no output {args.screen}; have {', '.join(outputs())}")
        sc.monitor(args.screen, args.pointer)
        target = {"screen": args.screen}
    elif args.area:
        sc.area(*args.area, pointer=args.pointer)
        target = {"area": args.area}
    elif args.all:
        bx, by, bw, bh = desktop_bounds()
        native = max(o[4] for o in outputs(with_scale=True).values())
        # one scale for the canvas: no upscaling past the sharpest monitor, and at most
        # 3840x2160 (OpenH264 refuses wider frames; same rule as KDE's --all)
        f = min(native, 3840 / bw, 2160 / bh)
        size = (max(2, int(round(bw * f)) // 2 * 2), max(2, int(round(bh * f)) // 2 * 2))
        sc.area(bx, by, bw, bh, pointer=args.pointer)
        lay = outputs()
        target = {"monitors": [{"name": n, "position": v[:2], "size": v[2:]} for n, v in lay.items()],
                  "pixels_per_logical": round(f, 4), "logical_region": [bx, by, bw, bh]}
    elif args.window:
        w, _ = window_geometry(args.window, activate=False)
        sc.window(w["id"], args.pointer)
        target = {"window": w["id"], "title": w["title"]}
    else:
        act = windows("active")["windows"] if bridge_ok() else []
        mon = (act[0]["output"] if act else None) or primary_output()
        sc.monitor(mon, args.pointer)
        target = {"screen": mon}
    node = sc.start()
    pipe = ["gst-launch-1.0", "-e", "pipewiresrc", f"path={node}", "do-timestamp=true", "keepalive-time=1000",
            "always-copy=true", "!", "videorate", "!", "video/x-raw,framerate=30/1", "!", "videoconvert", "!",
            *(["videoscale", "!", f"video/x-raw,width={size[0]},height={size[1]}", "!"] if size else []), "queue",
            "!", "vp8enc", "deadline=1", "cpu-used=8", f"target-bitrate={12000000 if size else 6000000}", "!", "webmmux",
            "!", "filesink", f"location={raw}"]
    gst = subprocess.Popen(pipe, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    stop = lambda *_: gst.poll() is None and gst.send_signal(signal.SIGINT)  # -e: EOS, file is finalised
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print(json.dumps({"recording": str(Path(args.out).resolve()), "pid": os.getpid()}), flush=True)
    try:
        gst.wait(timeout=args.seconds)
    except subprocess.TimeoutExpired:
        stop()
    gst.wait(timeout=30)
    params = sc.params()
    sc.stop()
    if not Path(raw).exists() or Path(raw).stat().st_size == 0:
        sys.exit(f"gst-launch produced no video: {gst.stderr.read()[-800:]}")
    if mp4:
        try:  # even sizes and at most 3840x2160 for OpenH264
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-vf",
                            "scale='min(iw,3840)':'min(ih,2160)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                            *h264_args(), "-pix_fmt", "yuv420p", args.out], check=True)
        finally:
            shutil.rmtree(td, ignore_errors=True)
    print(json.dumps({"file": str(Path(args.out).resolve()), **target,
                      "stream": {k: list(v) if isinstance(v, tuple) else v for k, v in params.items()}},
                     default=list))


def cmd_record_setup(args):
    print("GNOME needs no screen-share grant: recording uses Mutter's ScreenCast API directly. Testing 1 s...")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "t.webm"
        r = subprocess.run([sys.executable, __file__, "record", str(out), "--seconds", "1", "--screen",
                            primary_output()], capture_output=True, text=True)
        print("ok" if r.returncode == 0 and out.exists() else f"failed: {r.stderr.strip()}")
        sys.exit(r.returncode)


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
        if name == "record":
            g.add_argument("--all", action="store_true", help="every monitor in one video, placed like the desktop")
        if name != "record":
            p.add_argument("--no-raise", action="store_true", help="crop where the window is without raising it")
        if name == "shot":
            p.add_argument("--screencast", action="store_true", help="grab through Mutter ScreenCast, not the extension")
            settle.add_args(p)
        p.add_argument("--pointer", action="store_true")
        if name != "shot":
            p.add_argument("--seconds", type=float, default=10)
    sub.add_parser("record-setup", help="checks recording; no grant is needed on GNOME")
    sub.add_parser("screens", help="monitor layout in logical px")
    args = ap.parse_args()
    if args.cmd == "frames":
        args.screencast = False
    {"shot": cmd_shot, "frames": cmd_frames, "record": cmd_record, "record-setup": cmd_record_setup,
     "screens": cmd_screens}[args.cmd](args)


if __name__ == "__main__":
    main()
