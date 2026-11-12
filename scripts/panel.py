#!/usr/bin/python3
"""Record what the monitors REALLY show (the kernel's scanout buffer), on any desktop.

  lcu panel status                     # is the helper installed and granted? which monitors?
  lcu panel setup                      # ONE-TIME, needs the person's sudo password (see below)
  lcu panel record OUT.mkv --screen DP-1 [--seconds 10] [--fps 60] [--scale 0.5]
  lcu panel record OUT.mkv --all       # every monitor side by side, left to right

Why this exists: `lcu capture record` and every screenshot get frames the compositor renders
for the capture. Those are complete even when the panel is not: a compositor repaints only
the regions an app reports as damaged, so an app that under-reports damage shows stale or
alternating frames on the real screen while its recording looks perfect (seen on KWin 6.8,
2026-11-09). Use `panel record` whenever the question is "is this animation right on screen".

How: the kernel gives the buffer a monitor is scanning out only to a process with
CAP_SYS_ADMIN. `lcu panel setup` installs one small helper, /usr/local/libexec/lcu-panel-grab,
owned by root with that single file capability. The helper only hands the buffer (a dma-buf)
to its caller; it runs no other program (source: panel/lcu-panel-grab.rs). This script imports the buffer into the GPU (EGL,
no window), which undoes the driver's tiling and compression, reads it back as 8-bit RGB and
pipes it to ffmpeg. The grant survives reboots and updates; this script can change without
a new setup. After setup any program of this user can read the screen through the helper
with no share dialog: tell the person before they run it. Undo: `lcu panel setup --remove`.

Output by extension: .mkv = Ut Video, lossless RGB (use it for frame-by-frame analysis); .mp4
= H.264 (OpenH264, at most 3840 wide); .webm = VP9. Frames are the monitor's own pixels times
--scale (default 0.5, scaled on the GPU): what matters for motion is that every tick is
sampled on time, and full-size lossless video at 60 fps is more than the encoder can take
(2560x1440: nearly every tick late). Use --scale 1 for pixel-exact frames, with a lower --fps.
Not in the video: the mouse pointer and anything else the compositor puts on a separate
hardware plane. A buffer is read once per flip: while the compositor keeps showing the same
buffer, the previous frame is repeated. The JSON reports `flips` per monitor (how many times
the monitor was given a different buffer) and `late` (ticks that started behind schedule).
Exit 3 = not set up, or the installed helper is older than this script. JSON on stdout.
"""
import argparse
import ctypes
import json
import math
import os
import socket
import struct
import subprocess
import sys
import queue
import tempfile
import threading
import time
from ctypes import POINTER, byref, c_char_p, c_int, c_ssize_t, c_uint, c_void_p
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lcu_env  # noqa: E402

HELPER = Path("/usr/local/libexec/lcu-panel-grab")
PROTOCOL = 2
REPLY = struct.Struct("6I4I4IQ")  # status fb_id width height fourcc planes, pitches[4], offsets[4], modifier
ENCODERS = {
    ".mkv": ["-c:v", "utvideo", "-pix_fmt", "gbrp"],  # lossless and fast enough to keep up; FFV1 is not
    ".mp4": ["-c:v", "libopenh264", "-b:v", "16M", "-pix_fmt", "yuv420p"],
    ".webm": ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "8M"],
}
FFMPEG = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]

EGL_NONE = 0x3038
VERTEX = b"""#version 300 es
out vec2 uv;
void main() {
    vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
    uv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}"""
FRAGMENT = b"""#version 300 es
#extension GL_OES_EGL_image_external_essl3 : require
precision highp float;
uniform samplerExternalOES tex;
in vec2 uv;
out vec4 colour;
void main() { colour = vec4(texture(tex, uv).rgb, 1.0); }"""


class Gpu:
    """A window-less GLES 3 context that turns a scanout dma-buf into RGBA bytes."""

    def __init__(self):
        self.egl = egl = ctypes.CDLL("libEGL.so.1")
        self.gl = gl = ctypes.CDLL("libGLESv2.so.2")
        egl.eglGetPlatformDisplay.restype = c_void_p
        egl.eglGetPlatformDisplay.argtypes = [c_uint, c_void_p, c_void_p]
        egl.eglInitialize.argtypes = [c_void_p, c_void_p, c_void_p]
        egl.eglCreateContext.restype = c_void_p
        egl.eglCreateContext.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p]
        egl.eglMakeCurrent.argtypes = [c_void_p] * 4
        egl.eglCreateImage.restype = c_void_p
        egl.eglCreateImage.argtypes = [c_void_p, c_void_p, c_uint, c_void_p, POINTER(c_ssize_t)]
        egl.eglDestroyImage.argtypes = [c_void_p, c_void_p]
        egl.eglGetProcAddress.restype = c_void_p
        egl.eglGetProcAddress.argtypes = [c_char_p]
        self.dpy = egl.eglGetPlatformDisplay(0x31DD, None, None)  # EGL_PLATFORM_SURFACELESS_MESA
        if not self.dpy or not egl.eglInitialize(self.dpy, None, None):
            raise RuntimeError("EGL: no window-less display (needs Mesa's surfaceless platform)")
        egl.eglBindAPI(0x30A0)  # EGL_OPENGL_ES_API
        attrs = (c_int * 3)(0x3098, 3, EGL_NONE)  # EGL_CONTEXT_MAJOR_VERSION
        ctx = egl.eglCreateContext(self.dpy, None, None, attrs)
        if not ctx or not egl.eglMakeCurrent(self.dpy, None, None, ctx):
            raise RuntimeError(f"EGL: no GLES 3 context (error {egl.eglGetError():#x})")
        target = egl.eglGetProcAddress(b"glEGLImageTargetTexture2DOES")
        if not target:
            raise RuntimeError("GL: glEGLImageTargetTexture2DOES is missing")
        self.image_target = ctypes.CFUNCTYPE(None, c_uint, c_void_p)(target)
        gl.glShaderSource.argtypes = [c_uint, c_int, POINTER(c_char_p), c_void_p]
        gl.glGetShaderInfoLog.argtypes = [c_uint, c_int, c_void_p, c_char_p]
        gl.glTexImage2D.argtypes = [c_uint, c_int, c_int, c_int, c_int, c_int, c_uint, c_uint, c_void_p]
        gl.glReadPixels.argtypes = [c_int, c_int, c_int, c_int, c_uint, c_uint, c_void_p]
        prog = gl.glCreateProgram()
        for kind, src in ((0x8B31, VERTEX), (0x8B30, FRAGMENT)):  # GL_VERTEX_SHADER, GL_FRAGMENT_SHADER
            sh = gl.glCreateShader(kind)
            gl.glShaderSource(sh, 1, byref(c_char_p(src)), None)
            gl.glCompileShader(sh)
            ok = c_int()
            gl.glGetShaderiv(sh, 0x8B81, byref(ok))  # GL_COMPILE_STATUS
            if not ok.value:
                log = ctypes.create_string_buffer(2000)
                gl.glGetShaderInfoLog(sh, 2000, None, log)
                raise RuntimeError("GL: shader: " + log.value.decode(errors="replace"))
            gl.glAttachShader(prog, sh)
        gl.glLinkProgram(prog)
        gl.glUseProgram(prog)
        vao = c_uint()
        gl.glGenVertexArrays(1, byref(vao))
        gl.glBindVertexArray(vao)
        gl.glPixelStorei(0x0D05, 1)  # GL_PACK_ALIGNMENT
        self.size = None

    def target(self, w, h):
        """An RGBA8 texture of the monitor's size to draw into and read back from."""
        if self.size == (w, h):
            return
        gl = self.gl
        tex, fbo = c_uint(), c_uint()
        gl.glGenTextures(1, byref(tex))
        gl.glBindTexture(0x0DE1, tex)  # GL_TEXTURE_2D
        gl.glTexImage2D(0x0DE1, 0, 0x8058, w, h, 0, 0x1908, 0x1401, None)  # GL_RGBA8, GL_RGBA, GL_UNSIGNED_BYTE
        gl.glGenFramebuffers(1, byref(fbo))
        gl.glBindFramebuffer(0x8D40, fbo)  # GL_FRAMEBUFFER
        gl.glFramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, tex, 0)  # GL_COLOR_ATTACHMENT0
        if gl.glCheckFramebufferStatus(0x8D40) != 0x8CD5:  # GL_FRAMEBUFFER_COMPLETE
            raise RuntimeError("GL: cannot create the read-back target")
        gl.glViewport(0, 0, w, h)
        self.size = (w, h)
        self.pixels = ctypes.create_string_buffer(w * h * 4)

    def read(self, r, fds, out_w, out_h):
        """r = unpacked REPLY, fds = its dma-buf descriptors -> RGBA rows of out_w x out_h, top row first."""
        _, _, w, h, fourcc, planes = r[:6]
        pitches, offsets, modifier = r[6:10], r[10:14], r[14]
        a = [0x3057, w, 0x3056, h, 0x3271, fourcc]  # EGL_WIDTH, EGL_HEIGHT, EGL_LINUX_DRM_FOURCC_EXT
        fd_attr = (0x3272, 0x3275, 0x3278, 0x3440)  # EGL_DMA_BUF_PLANEn_FD_EXT; OFFSET = +1, PITCH = +2
        mod_attr = (0x3443, 0x3445, 0x3447, 0x3449)  # EGL_DMA_BUF_PLANEn_MODIFIER_LO_EXT; HI = +1
        for i in range(planes):
            a += [fd_attr[i], fds[i], fd_attr[i] + 1, offsets[i], fd_attr[i] + 2, pitches[i]]
            if modifier != 0x00FFFFFFFFFFFFFF:  # DRM_FORMAT_MOD_INVALID: the driver's implicit layout
                a += [mod_attr[i], modifier & 0xFFFFFFFF, mod_attr[i] + 1, modifier >> 32]
        a.append(EGL_NONE)
        image = self.egl.eglCreateImage(self.dpy, None, 0x3270, None, (c_ssize_t * len(a))(*a))  # EGL_LINUX_DMA_BUF_EXT
        if not image:
            name = struct.pack("I", fourcc).decode(errors="replace")
            raise RuntimeError(f"EGL: the GPU driver refused the scanout buffer (format {name}, modifier "
                               f"{modifier:#x}, EGL error {self.egl.eglGetError():#x})")
        self.target(out_w, out_h)
        gl = self.gl
        tex = c_uint()
        gl.glGenTextures(1, byref(tex))
        gl.glBindTexture(0x8D65, tex)  # GL_TEXTURE_EXTERNAL_OES
        smooth = 0x2600 if (out_w, out_h) == (w, h) else 0x2601  # NEAREST when 1:1, else LINEAR
        gl.glTexParameteri(0x8D65, 0x2801, smooth)  # MIN_FILTER
        gl.glTexParameteri(0x8D65, 0x2800, smooth)  # MAG_FILTER
        gl.glTexParameteri(0x8D65, 0x2802, 0x812F)  # WRAP_S = CLAMP_TO_EDGE
        gl.glTexParameteri(0x8D65, 0x2803, 0x812F)  # WRAP_T
        self.image_target(0x8D65, image)
        gl.glDrawArrays(0x0004, 0, 3)  # one triangle covering the target
        gl.glReadPixels(0, 0, out_w, out_h, 0x1908, 0x1401, self.pixels)
        err = gl.glGetError()
        gl.glDeleteTextures(1, byref(tex))
        self.egl.eglDestroyImage(self.dpy, image)
        if err:
            raise RuntimeError(f"GL: reading the scanout buffer failed (error {err:#x})")
        return self.pixels


def helper_state():
    """-> (installed, granted, protocol version or None)"""
    if not HELPER.exists():
        return False, False, None
    caps = subprocess.run(["getcap", str(HELPER)], capture_output=True, text=True).stdout
    ver = subprocess.run([str(HELPER), "version"], capture_output=True, text=True)
    return True, "cap_sys_admin" in caps, int(ver.stdout) if ver.returncode == 0 and ver.stdout.strip().isdigit() else None


def need_setup():
    installed, granted, version = helper_state()
    if installed and granted and version == PROTOCOL:
        return
    why = ("not set up" if not (installed and granted) else
           f"the installed helper speaks protocol {version or 1}, this script needs {PROTOCOL}")
    print(f"lcu panel: {why}. With the person present, run `lcu panel setup` once "
          "(it asks for their sudo password).", file=sys.stderr)
    raise SystemExit(3)


def monitors():
    """[{name, card, crtc, width, height}] of connected monitors, from the helper (no privilege needed)."""
    out = subprocess.run([str(HELPER), "list"], capture_output=True, text=True).stdout
    res = []
    for line in out.splitlines():
        name, card, crtc, w, h = line.split()
        res.append({"name": name, "card": int(card), "crtc": int(crtc), "width": int(w), "height": int(h)})
    return res


def left_to_right(mons):
    """Order by desktop position when the desktop backend can tell; else keep the kernel's order."""
    try:
        out = subprocess.run(lcu_env.tool("capture", "screens"), capture_output=True, text=True, timeout=15).stdout
        xs = {s["name"]: s.get("x", 0) for s in json.loads(out) if isinstance(s, dict) and "name" in s}
        return sorted(mons, key=lambda m: xs.get(m["name"], 1e9))
    except Exception:  # noqa: BLE001 - ordering is a nicety
        return mons


class Source:
    """The helper serving one graphics card's scanout buffers."""

    def __init__(self, card):
        self.sock, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.proc = subprocess.Popen([str(HELPER), "serve", str(card), str(theirs.fileno())], pass_fds=(theirs.fileno(),))
        theirs.close()

    def scanout(self, crtc):
        self.sock.send(struct.pack("I", crtc))
        data, fds, _, _ = socket.recv_fds(self.sock, REPLY.size, 4)
        if len(data) != REPLY.size:
            sys.exit("lcu panel: the helper stopped answering")
        r = REPLY.unpack(data)
        if r[0]:
            sys.exit(f"lcu panel: no scanout buffer for CRTC {crtc}: {os.strerror(r[0])}"
                     + (" (the helper has lost its capability: run `lcu panel setup`)" if r[0] == 1 else ""))
        return r, fds

    def close(self):
        self.sock.close()
        self.proc.wait()


def feed(enc, frames):
    """Writer thread: keeps a slow moment in the encoder from delaying the next sample."""
    try:
        while (frame := frames.get()) is not None:
            enc.stdin.write(frame)
    except (BrokenPipeError, ValueError):
        while frames.get() is not None:  # keep draining so the sampler never blocks on a dead encoder
            pass


def record(chosen, files, fps, seconds, scale, encoder_args):
    """Sample every chosen monitor `fps` times a second into its own file. -> per-monitor stats"""
    gpu = Gpu()
    sources = {}
    state = []
    for m, f in zip(chosen, files):
        sources.setdefault(m["card"], Source(m["card"]))
        m["video_width"], m["video_height"] = (max(2, round(m[k] * scale / 2) * 2) for k in ("width", "height"))
        enc = subprocess.Popen([*FFMPEG, "-f", "rawvideo", "-pix_fmt", "rgba", "-video_size",
                                f"{m['video_width']}x{m['video_height']}", "-framerate", str(fps), "-i", "pipe:0",
                                *encoder_args, str(f)], stdin=subprocess.PIPE)
        frames = queue.Queue(maxsize=fps)  # up to a second of slack
        writer = threading.Thread(target=feed, args=(enc, frames), daemon=True)
        writer.start()
        state.append({"mon": m, "enc": enc, "frames": frames, "writer": writer, "fb": None, "frame": None,
                      "flips": 0, "buffers": set()})
    late = 0
    start = time.monotonic()
    try:
        for tick in range(seconds * fps):
            due = start + tick / fps
            now = time.monotonic()
            if now < due:
                time.sleep(due - now)
            elif now - due > 1 / fps:
                late += 1
            for s in state:
                r, fds = sources[s["mon"]["card"]].scanout(s["mon"]["crtc"])
                try:
                    if r[1] != s["fb"]:  # the monitor was given another buffer: read it
                        if (r[2], r[3]) != (s["mon"]["width"], s["mon"]["height"]):
                            sys.exit(f"lcu panel: {s['mon']['name']} changed size during the recording")
                        s["frame"] = bytes(gpu.read(r, fds, s["mon"]["video_width"], s["mon"]["video_height"]))
                        s["flips"] += s["fb"] is not None
                        s["fb"] = r[1]
                        s["buffers"].add(r[1])
                finally:
                    for fd in fds:
                        os.close(fd)
                s["frames"].put(s["frame"])
    finally:
        for s in state:
            s["frames"].put(None)
            s["writer"].join()
            try:
                s["enc"].stdin.close()
            except OSError:
                pass
            s["enc"].wait()
        for src in sources.values():
            src.close()
    for s in state:
        if s["enc"].returncode:
            sys.exit(f"lcu panel: encoding {s['mon']['name']} failed")
    return [{**s["mon"], "flips": s["flips"], "buffers": len(s["buffers"])} for s in state], late


def cmd_status(_):
    installed, granted, version = helper_state()
    ok = installed and granted and version == PROTOCOL
    print(json.dumps({"helper": str(HELPER), "installed": installed, "granted": granted, "protocol": version,
                      "needs": PROTOCOL, "ready": ok, "monitors": monitors() if installed else []}, indent=1))
    return 0 if ok else 3


def cmd_setup(args):
    os.execv("/bin/bash", ["bash", str(HERE / "panel" / "setup.sh"), *args.rest])


def cmd_record(args):
    need_setup()
    out = Path(args.out).resolve()
    if out.suffix not in ENCODERS:
        sys.exit(f"lcu panel: OUT must end in one of {', '.join(ENCODERS)}")
    mons = monitors()
    if args.all:
        chosen = left_to_right(mons)
    else:
        chosen = [m for m in mons if m["name"] == (args.screen or mons[0]["name"])]
        if not chosen:
            sys.exit(f"lcu panel: no connected monitor {args.screen!r}; have: {', '.join(m['name'] for m in mons)}")
    seconds = max(1, math.ceil(args.seconds))
    enc = ENCODERS[out.suffix]
    narrow = out.suffix == ".mp4"  # OpenH264 refuses frames wider than 3840
    if len(chosen) == 1:
        scale = ["-vf", "scale='min(3840,iw)':-2"] if narrow else []
        stats, late = record(chosen, [out], args.fps, seconds, args.scale, [*scale, *enc])
    else:
        with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
            parts = [Path(tmp) / f"{m['name']}.mkv" for m in chosen]
            stats, late = record(chosen, parts, args.fps, seconds, args.scale, ENCODERS[".mkv"])
            height = max(m["video_height"] for m in chosen)
            graph = "".join(f"[{i}:v]pad=iw:{height}:0:0:black[p{i}];" for i in range(len(chosen)))
            graph += "".join(f"[p{i}]" for i in range(len(chosen))) + f"hstack=inputs={len(chosen)}"
            if narrow:
                graph += ",scale='min(3840,iw)':-2"
            cmd = list(FFMPEG)
            for p in parts:
                cmd += ["-i", str(p)]
            r = subprocess.run([*cmd, "-filter_complex", graph, *enc, str(out)], capture_output=True, text=True)
            if r.returncode:
                sys.exit(f"lcu panel: joining the monitors failed: {r.stderr[-600:]}")
    print(json.dumps({"file": str(out), "source": "kms scanout (what the panel shows)", "monitors": stats,
                      "fps": args.fps, "seconds": seconds, "scale": args.scale, "late": late,
                      "note": "the mouse pointer is not included"}))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("setup")
    p.add_argument("--remove", dest="rest", action="store_const", const=["--remove"], default=[], help="undo the setup")
    p.add_argument("--allow-local", dest="rest", action="store_const", const=["--allow-local"],
                   help="install even though the helper source differs from GitHub (review it first)")
    p = sub.add_parser("record")
    p.add_argument("out")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--screen")
    g.add_argument("--all", action="store_true")
    p.add_argument("--seconds", type=float, default=10)
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--scale", type=float, default=0.5, help="video size relative to the monitor's pixels (1 = exact)")
    args = ap.parse_args()
    try:
        return {"status": cmd_status, "setup": cmd_setup, "record": cmd_record}[args.cmd](args)
    except RuntimeError as e:
        sys.exit(f"lcu panel: {e}")


if __name__ == "__main__":
    sys.exit(main())
