#!/usr/bin/python3
"""Screenshots and screen recordings on KDE Plasma 6 Wayland.

  lcu capture screens                                # monitor layout (logical px), scale, active output
  lcu capture shot OUT.png                           # whole desktop
  lcu capture shot OUT.png --screen DP-1             # one monitor
  lcu capture shot OUT.png --area X Y W H            # logical desktop pixels
  lcu capture shot OUT.png --window class:org.kde.dolphin [--no-raise]
  lcu capture shot OUT.png --pointer ...             # include the cursor
  lcu capture shot OUT.png --settle ...              # wait until the picture stops changing
  lcu capture shot OUT.png --since PREV.png ...      # first wait until it differs from PREV.png, then settle

  lcu capture record-setup
      ONE-TIME, needs the person: KDE's share dialog opens once; they select ALL
      monitors and keep "allow restoring" ticked. The grant is saved as a restore
      token (~/.local/state/linux-computer-use) and every later `record` reuses it
      with no dialog. Rerun only if a recording reports the grant is gone.

  lcu capture record OUT.webm [--seconds 10] [--screen DP-1 | --area X Y W H | --window MATCH]
      Real-time video through the xdg ScreenCast portal (PipeWire -> GStreamer VP8).
      Records the monitor that holds the target and crops to it with ffmpeg, so
      --window/--area need no picker (window geometry is read at start; a window
      moved during the recording is not followed). Default: the monitor of the
      active window. Stops after --seconds or on SIGINT/SIGTERM (clean file).
      Without a saved grant it exits with code 3 instead of showing a dialog.

  lcu capture frames OUT.mp4 --seconds 10 [--screen|--area|--window ...]
      No dialog: repeated Spectacle stills (~1.5 fps) joined with ffmpeg. Use for
      "what happened on screen" evidence, not for smooth video.

Sharpness: Spectacle's whole-desktop grab (-f) is rendered at one uniform scale (2x
logical here), so every monitor with a lower scale is upscaled and soft, and images are
large. A --window shot raises the window and uses Spectacle's active-window grab (-a):
the window's own pixels at its monitor's scale, nothing that covers it. A --screen shot,
or an --area inside one monitor, uses the current-monitor grab (-m) at that monitor's
native scale when it is KWin's active output (the one holding the focused window; not
the pointer's); otherwise it is cut from the whole-desktop grab. To get a sharp shot of
the other monitor, activate a window there first, or shoot a --window.
The JSON says which ("source") and gives pixels_per_logical for converting coordinates.
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
from lcu_env import run_json, tool  # noqa: E402
import settle  # noqa: E402


# --- geometry -----------------------------------------------------------------
def outputs(with_scale=False):
    j = json.loads(subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, check=True).stdout)
    res = {}
    for o in j["outputs"]:
        if not o.get("enabled", True) or not o.get("connected", True):
            continue
        sc = o.get("scale", 1)
        size = o["size"]
        if o.get("rotation", 1) in (2, 8):
            size = {"width": size["height"], "height": size["width"]}
        res[o["name"]] = (o["pos"]["x"], o["pos"]["y"], round(size["width"] / sc), round(size["height"] / sc)) \
            + ((sc, o.get("priority", 0) == 1) if with_scale else ())
    return res


def bounds():
    outs = outputs().values()
    minx, miny = min(o[0] for o in outs), min(o[1] for o in outs)
    return minx, miny, max(o[0] + o[2] for o in outs) - minx, max(o[1] + o[3] for o in outs) - miny


def output_holding(region):
    """Name of the monitor that wholly contains region (x, y, w, h), else None."""
    x, y, w, h = region
    for name, (ox, oy, ow, oh) in outputs().items():
        if ox <= x and oy <= y and x + w <= ox + ow + 0.5 and y + h <= oy + oh + 0.5:
            return name
    return None


def window_geometry(match, activate):
    prev = run_json("window", "active")
    if activate:
        run_json("window", "activate", match, "--first")
        time.sleep(0.35)  # let KWin repaint the raised window
    code, w = run_json("window", "info", match, "--first", check=False)
    if code:
        sys.exit(w if isinstance(w, str) else w.get("error", w))
    return w[0], (prev[0]["id"] if prev else None)


def restore_focus(win_id):
    if win_id:
        subprocess.run(tool("window", "activate", f"id:{win_id}"), capture_output=True)


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
        raise_it = not getattr(args, "no_raise", False)
        w, prev = window_geometry(args.window, raise_it)
        return (w["x"], w["y"], w["width"], w["height"]), (lambda: restore_focus(prev)) if raise_it else (lambda: None), w
    return None, lambda: None, None


# --- stills -------------------------------------------------------------------
def spectacle(path, mode="-f", pointer=False):
    cmd = ["spectacle", "-b", "-n", mode, "-o", str(path)] + (["-p"] if pointer else []) + (["-S"] if mode == "-a" else [])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode or not Path(path).exists():
        sys.exit(f"spectacle failed ({r.returncode}): {r.stderr.strip()}")


def save_crop(src, dst, origin, region):
    """Crop src (an image of the logical rectangle origin = (x, y, w, h)) to region; -> size, px per logical."""
    im = GdkPixbuf.Pixbuf.new_from_file(str(src))
    f = im.get_width() / origin[2]
    if region and tuple(region) != tuple(origin):
        x, y, w, h = region
        x0, y0 = max(0, round((x - origin[0]) * f)), max(0, round((y - origin[1]) * f))
        x1, y1 = min(im.get_width(), round((x - origin[0] + w) * f)), min(im.get_height(), round((y - origin[1] + h) * f))
        im = im.new_subpixbuf(x0, y0, x1 - x0, y1 - y0)
    im.savev(str(dst), "png", [], [])
    return [im.get_width(), im.get_height()], f


def grab(dst, region, pointer=False, window=None):
    """One still of region (None = whole desktop) -> (size, pixels_per_logical, source)."""
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw.png"
        if window is not None:
            active = run_json("window", "active")
            if active and active[0]["id"] == window["id"]:
                spectacle(raw, "-a", pointer)
                im = GdkPixbuf.Pixbuf.new_from_file(str(raw))
                f = im.get_width() / window["width"]
                if abs(im.get_height() / f - window["height"]) <= 2:  # no shadow or popup around it
                    size, f = save_crop(raw, dst, region, None)
                    return size, f, "spectacle -a (window's own pixels)"
        mon = output_holding(region) if region else None
        if mon and run_json("window", "pointer")["active_output"] == mon:
            spectacle(raw, "-m", pointer)
            size, f = save_crop(raw, dst, outputs()[mon], region)
            return size, f, f"spectacle -m ({mon} at native scale)"
        spectacle(raw, "-f", pointer)
        size, f = save_crop(raw, dst, bounds(), region)
        return size, f, "spectacle -f (whole desktop at one scale" + (", cropped)" if region else ")")


def cmd_screens(args):
    p = run_json("window", "pointer")
    print(json.dumps([{"name": n, "x": x, "y": y, "width": w, "height": h, "scale": s, "primary": prim,
                       "active": p["active_output"] == n, "pointer": p["output"] == n}
                      for n, (x, y, w, h, s, prim) in outputs(with_scale=True).items()], indent=1))


def cmd_shot(args):
    region, cleanup, win = region_for(args)
    extra = {}
    one = lambda path: grab(path, region, args.pointer, win if not args.no_raise else None)
    try:
        if settle.wanted(args):
            (size, f, source), info = settle.wait(one, args.out, args.settle_quiet, args.settle_timeout, args.since,
                                                  scale=lambda r: r[1])
            extra = {"settle": info}
        else:
            size, f, source = one(args.out)
    finally:
        cleanup()  # hand focus back only after the grab, so the raised window is in the picture
    print(json.dumps({"file": str(Path(args.out).resolve()), "size": size, "logical_region": region or bounds(),
                      "pixels_per_logical": round(f, 4), "source": source, **extra}))


# --- low-fps recording without a dialog -------------------------------------------
def cmd_frames(args):
    region, cleanup, _ = region_for(args)
    td = Path(tempfile.mkdtemp(prefix="lcu-frames-"))
    try:
        end, n, t0 = time.monotonic() + args.seconds, 0, time.monotonic()
        while time.monotonic() < end:
            spectacle(td / f"f{n:05d}.png", "-f", args.pointer)
            n += 1
        fps = max(n / (time.monotonic() - t0), 0.1)
        cleanup()
        # crop once in ffmpeg (cheaper than per frame); Fedora's ffmpeg has no libx264
        vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
        if region:
            minx, miny, bw, _ = bounds()
            f = GdkPixbuf.Pixbuf.get_file_info(str(td / "f00000.png"))[1] / bw
            x, y, w, h = region
            vf = f"crop={round(w*f)//2*2}:{round(h*f)//2*2}:{round((x-minx)*f)}:{round((y-miny)*f)}," + vf
        codec = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-row-mt", "1"] if args.out.endswith(".webm") \
            else ["-c:v", "libopenh264", "-b:v", "6M"]
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", f"{fps:.3f}", "-i", str(td / "f%05d.png"),
                        "-vf", vf, *codec, "-pix_fmt", "yuv420p", "-r", "10", args.out], check=True)
        print(json.dumps({"file": str(Path(args.out).resolve()), "frames": n, "fps": round(fps, 2)}))
    finally:
        shutil.rmtree(td, ignore_errors=True)


# --- portal screencast ---------------------------------------------------------
def cmd_record_setup(args):
    from portal import ScreenCast
    p = ScreenCast()
    p.forget()
    print("KDE's share dialog is opening: select ALL monitors, keep 'allow restoring' ticked, press Share.", flush=True)
    streams = p.start(interactive=True)
    p.close()
    print(json.dumps({"grant_saved": p.TOKEN.exists(), "monitors": [s[1] for s in streams]}, default=list))
    if len(streams) < len(outputs()):
        print("note: fewer monitors were shared than are connected; recordings on the others will fail", file=sys.stderr)


def cmd_record(args):
    from portal import ScreenCast
    region, restore_top = None, (lambda: None)
    if args.screen:
        region = outputs().get(args.screen) or sys.exit(f"no output {args.screen}")
    elif args.area:
        region = tuple(args.area)
    elif args.window:
        w, _prev = window_geometry(args.window, activate=False)
        region = (w["x"], w["y"], w["width"], w["height"])
        # The recording is a crop of the monitor, so whatever covers the window would be
        # filmed. Raise it (no focus change) and put the old topmost window back afterwards.
        stack = run_json("window", "list")
        above = next((s for s in stack if s["output"] == w["output"] and not s["minimized"]), None)
        subprocess.run(tool("window", "raise", f"id:{w['id']}"), capture_output=True)
        if above and above["id"] != w["id"]:
            restore_top = lambda: subprocess.run(tool("window", "raise", f"id:{above['id']}"), capture_output=True)
    else:
        act = run_json("window", "active")
        if not act:
            sys.exit("no active window; pass --screen")
        region = outputs()[act[0]["output"]]
    p = ScreenCast()
    streams = p.start(interactive=False, pointer=args.pointer)
    cx, cy = region[0] + region[2] / 2, region[1] + region[3] / 2

    def holds(props):
        (x, y), (w, h) = props.get("position", (0, 0)), props.get("size", (0, 0))
        return x <= cx < x + w and y <= cy < y + h
    pick = [s for s in streams if holds(s[1])]
    if not pick:
        p.close()
        sys.exit(f"no shared monitor contains {region}; shared: {[s[1] for s in streams]} (rerun record-setup with all monitors)")
    node, props = pick[0]
    fd = p.pipewire_fd()

    whole = tuple(props.get("position", (0, 0))) + tuple(props.get("size", (0, 0))) == tuple(round(v) for v in region)
    raw = str(Path(tempfile.mkdtemp(prefix="lcu-rec-")) / "raw.webm")
    pipe = ["gst-launch-1.0", "-e", "pipewiresrc", f"fd={fd}", f"path={node}", "do-timestamp=true", "keepalive-time=1000",
            "!", "videorate", "!", "video/x-raw,framerate=30/1", "!", "videoconvert", "!", "queue",
            "!", "vp8enc", "deadline=1", "cpu-used=8", "target-bitrate=6000000", "!", "webmmux", "!", "filesink", f"location={raw}"]
    gst = subprocess.Popen(pipe, pass_fds=(fd,), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    stop = lambda *_: gst.poll() is None and gst.send_signal(signal.SIGINT)  # -e: EOS, file is finalised
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print(json.dumps({"recording": str(Path(args.out).resolve()), "pid": os.getpid()}), flush=True)
    t0 = time.monotonic()
    try:
        gst.wait(timeout=args.seconds)
    except subprocess.TimeoutExpired:
        stop()
    wall = time.monotonic() - t0
    gst.wait(timeout=30)
    p.close()
    restore_top()
    if not Path(raw).exists() or Path(raw).stat().st_size == 0:
        sys.exit(f"gst-launch produced no video: {gst.stderr.read()[-800:]}")
    # KWin sends frames only when the picture changes, so a still screen gives a video that
    # ends at its last change (0.6 s for a 3 s take of a static window). Repeat the last
    # frame up to the wall-clock length, like the COSMIC recorder does; crop if needed.
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=width:format=duration", "-of", "json", raw],
                                      capture_output=True, text=True).stdout)
    filters = []
    if not whole:
        px, py = props.get("position", (0, 0))
        lw = props.get("size", (0, 0))[0]
        f = probe["streams"][0]["width"] / lw if lw else 1
        x, y, w, h = region
        filters.append(f"crop={round(w*f)//2*2}:{round(h*f)//2*2}:{max(0, round((x-px)*f))}:{max(0, round((y-py)*f))}")
    short = wall - float(probe.get("format", {}).get("duration") or 0)
    if short > 0.15:
        filters.append(f"tpad=stop_mode=clone:stop_duration={short:.3f}")
    if filters:
        codec = ["-c:v", "libopenh264", "-b:v", "6M", "-pix_fmt", "yuv420p"] if args.out.endswith(".mp4") \
            else ["-c:v", "libvpx", "-b:v", "4M", "-deadline", "realtime", "-cpu-used", "8"]
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-vf", ",".join(filters), "-t", f"{wall:.3f}",
                        *codec, args.out], check=True)
    elif args.out.endswith(".webm"):
        shutil.move(raw, args.out)
    else:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-c:v", "libopenh264", "-b:v", "6M",
                        "-pix_fmt", "yuv420p", args.out], check=True)
    shutil.rmtree(Path(raw).parent, ignore_errors=True)
    print(json.dumps({"file": str(Path(args.out).resolve()), "monitor": props, "logical_region": region}, default=list))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("screens", help="monitor layout in logical px")
    for name in ("shot", "frames", "record"):
        p = sub.add_parser(name)
        p.add_argument("out")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--screen")
        g.add_argument("--area", type=float, nargs=4, metavar=("X", "Y", "W", "H"))
        g.add_argument("--window", metavar="MATCH", help="see `lcu window --help` for MATCH syntax")
        if name != "record":
            p.add_argument("--no-raise", action="store_true", help="crop where the window is without raising it")
        p.add_argument("--pointer", action="store_true")
        if name != "shot":
            p.add_argument("--seconds", type=float, default=10)
        else:
            settle.add_args(p)
    sub.add_parser("record-setup", help="one-time screen-share grant (needs the person)")
    args = ap.parse_args()
    {"screens": cmd_screens, "shot": cmd_shot, "frames": cmd_frames, "record": cmd_record,
     "record-setup": cmd_record_setup}[args.cmd](args)


if __name__ == "__main__":
    main()
