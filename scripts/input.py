#!/usr/bin/python3
"""Mouse and keyboard input on Wayland through libei (EIS), on KDE, GNOME and COSMIC.

No root, no uinput, no ydotool. The compositor hands this process a libei socket and
we emulate a pointer and keyboard on it with libei through ctypes. Where the socket
comes from depends on the desktop (lcu detect):
  kde     KWin's org.kde.KWin.EIS.RemoteDesktop.connectToEIS: no dialog, ever.
  gnome   Mutter's private org.gnome.Mutter.RemoteDesktop session, ConnectToEIS: no
          dialog; GNOME shows its remote-desktop indicator while a call runs.
  cosmic  cosmic-comp answers only its own portal, so the RemoteDesktop portal:
          CreateSession -> SelectDevices (persist until revoked) -> Start -> ConnectToEIS.
          The first time COSMIC shows a "Remote desktop" dialog the user must allow;
          the restore token is saved in ~/.local/state/linux-computer-use/ and later
          calls reuse it without a dialog. `lcu input --setup` does that up front.
LCU_INPUT=portal forces the portal route on any desktop whose portal has ConnectToEIS.

Coordinates are the compositor's logical (desktop) pixels, the space `lcu capture
screens` prints and `lcu window` returns. Keys are evdev codes interpreted with the
user's current keymap.

Usage (actions run in order in one connection):
  lcu input move X Y
  lcu input move 800 400 click left
  lcu input rmove 40 -10                # relative
  lcu input click right                 # at the current pointer position
  lcu input click left 2                # double click (3 = triple)
  lcu input down left move 900 500 up left
  lcu input drag 100 100 600 400        # press at A, nudge, glide to B, hover, release
  lcu input drag 100 100 600 400 right  # with another button
  lcu input drag 100 100 600 400 step 8 # at most 8 px per move, 25 ms apart (libcosmic edge resize)
  lcu input scroll 3                    # 3 wheel detents down (negative = up)
  lcu input hscroll -2                  # 2 detents left
  lcu input key ctrl+shift+t
  lcu input keydown shift click left keyup shift      # shift-click
  lcu input keydown ctrl move 500 300 click left move 600 300 click left keyup ctrl
  lcu input type "hello world"          # US keymap; see --help-keys
  lcu input paste "héllo wörld ✓"       # any text: clipboard + ctrl+v, clipboard restored after
  lcu input paste-term "text"           # the same with ctrl+shift+v (terminals)
  lcu input sleep 250                   # milliseconds
  lcu input --list-regions              # print the absolute-pointer regions
  lcu input --setup | --forget          # COSMIC/portal: save / delete the input grant
"""
import ctypes
import math
import os
import select
import subprocess
import sys
import time

import lcu_env

# --- libei ------------------------------------------------------------------
ei = ctypes.CDLL("libei.so.1")
P, D, I, U, B = ctypes.c_void_p, ctypes.c_double, ctypes.c_int, ctypes.c_uint32, ctypes.c_bool


def sig(name, res, *args):
    f = getattr(ei, name)
    f.restype, f.argtypes = res, list(args)
    return f


sig("ei_new_sender", P, P)
sig("ei_configure_name", None, P, ctypes.c_char_p)
sig("ei_setup_backend_fd", I, P, I)
sig("ei_get_fd", I, P)
sig("ei_dispatch", None, P)
sig("ei_get_event", P, P)
sig("ei_event_get_type", I, P)
sig("ei_event_type_to_string", ctypes.c_char_p, I)
sig("ei_event_get_seat", P, P)
sig("ei_event_get_device", P, P)
sig("ei_event_unref", P, P)
sig("ei_now", ctypes.c_uint64, P)
ei.ei_seat_bind_capabilities.restype = None  # variadic, NULL-terminated
sig("ei_device_ref", P, P)
sig("ei_device_get_name", ctypes.c_char_p, P)
sig("ei_device_has_capability", B, P, I)
sig("ei_device_start_emulating", None, P, U)
sig("ei_device_stop_emulating", None, P)
sig("ei_device_frame", None, P, ctypes.c_uint64)
sig("ei_device_pointer_motion", None, P, D, D)
sig("ei_device_pointer_motion_absolute", None, P, D, D)
sig("ei_device_button_button", None, P, U, B)
sig("ei_device_scroll_discrete", None, P, ctypes.c_int32, ctypes.c_int32)
sig("ei_device_keyboard_key", None, P, U, B)
sig("ei_device_get_region", P, P, ctypes.c_size_t)
for n, r in [("x", U), ("y", U), ("width", U), ("height", U)]:
    sig(f"ei_region_get_{n}", r, P)
sig("ei_region_get_physical_scale", D, P)

# enum ei_device_capability (libei 1.x)
CAP_POINTER, CAP_POINTER_ABSOLUTE, CAP_KEYBOARD, CAP_TOUCH, CAP_SCROLL, CAP_BUTTON = (1 << i for i in range(6))
CAP_NAMES = {CAP_POINTER: "pointer", CAP_POINTER_ABSOLUTE: "pointer-absolute", CAP_KEYBOARD: "keyboard",
             CAP_TOUCH: "touch", CAP_SCROLL: "scroll", CAP_BUTTON: "button"}

BUTTONS = {"left": 0x110, "right": 0x111, "middle": 0x112, "back": 0x113, "forward": 0x114}

# --- evdev keycodes (US layout) -----------------------------------------------
KEYS = {
    "esc": 1, "escape": 1, "minus": 12, "equal": 13, "backspace": 14, "tab": 15,
    "enter": 28, "return": 28, "ctrl": 29, "control": 29, "leftctrl": 29, "shift": 42, "leftshift": 42,
    "rightshift": 54, "alt": 56, "leftalt": 56, "space": 57, "capslock": 58,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65, "f8": 66, "f9": 67, "f10": 68,
    "f11": 87, "f12": 88, "rightctrl": 97, "altgr": 100, "rightalt": 100, "home": 102, "up": 103,
    "pageup": 104, "pgup": 104, "left": 105, "right": 106, "end": 107, "down": 108, "pagedown": 109,
    "pgdn": 109, "insert": 110, "delete": 111, "del": 111, "super": 125, "meta": 125, "win": 125,
    "menu": 127, "print": 99, "sysrq": 99,
}
for i, ch in enumerate("1234567890"):
    KEYS[ch] = 2 + i
for row, start in (("qwertyuiop", 16), ("asdfghjkl", 30), ("zxcvbnm", 44)):
    for i, ch in enumerate(row):
        KEYS[ch] = start + i
# character -> (keycode, needs shift)
CHARS = {c: (KEYS[c], False) for c in "1234567890qwertyuiopasdfghjklzxcvbnm"}
CHARS.update({c.upper(): (KEYS[c], True) for c in "qwertyuiopasdfghjklzxcvbnm"})
CHARS.update({" ": (57, False), "\n": (28, False), "\t": (15, False)})
for plain, shifted, code in [("-", "_", 12), ("=", "+", 13), ("[", "{", 26), ("]", "}", 27), (";", ":", 39),
                             ("'", '"', 40), ("`", "~", 41), ("\\", "|", 43), (",", "<", 51), (".", ">", 52),
                             ("/", "?", 53)]:
    CHARS[plain], CHARS[shifted] = (code, False), (code, True)
for ch, digit in zip("!@#$%^&*()", "1234567890"):
    CHARS[ch] = (KEYS[digit], True)


def keycode(name):
    n = name.lower()
    if n in KEYS:
        return KEYS[n]
    if n.isdigit():
        return int(n)  # raw evdev code
    sys.exit(f"unknown key {name!r}; see --help-keys")


def provider():
    forced = os.environ.get("LCU_INPUT")
    if forced:
        return forced
    return {"kde": "kwin", "gnome": "mutter", "cosmic": "portal"}[lcu_env.desktop()]


class KWinEIS:
    """KWin hands out EIS sockets to any session-bus client (Plasma 6.1+)."""
    DEST, PATH, IFACE = "org.kde.KWin", "/org/kde/KWin/EIS/RemoteDesktop", "org.kde.KWin.EIS.RemoteDesktop"

    def connect(self, _timeout):
        from gi.repository import Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        try:
            r, fdl = self.bus.call_with_unix_fd_list_sync(self.DEST, self.PATH, self.IFACE, "connectToEIS",
                                                          GLib.Variant("(i)", (63,)), GLib.VariantType("(hi)"),
                                                          Gio.DBusCallFlags.NONE, 10000, None, None)
        except GLib.Error as e:
            sys.exit(f"KWin refused connectToEIS (needs Plasma 6.1+): {e.message}")
        handle, self.cookie = r.unpack()
        return fdl.get(handle)

    def close(self):
        from gi.repository import Gio, GLib
        try:
            self.bus.call_sync(self.DEST, self.PATH, self.IFACE, "disconnect", GLib.Variant("(i)", (self.cookie,)),
                               None, Gio.DBusCallFlags.NONE, 5000, None)
        except GLib.Error:
            pass


class MutterEIS:
    """Mutter's private RemoteDesktop API is open to session-bus clients: no dialog."""
    RD = "org.gnome.Mutter.RemoteDesktop"

    def connect(self, _timeout):
        from gi.repository import Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)

        def call(path, iface, method, args=None, rtype=None):
            r, fdl = self.bus.call_with_unix_fd_list_sync(self.RD, path, iface, method, args,
                                                          GLib.VariantType(rtype) if rtype else None,
                                                          Gio.DBusCallFlags.NONE, 10000, None, None)
            return (r.unpack() if r is not None else ()), fdl
        self._call = call
        try:
            self.session = call("/org/gnome/Mutter/RemoteDesktop", self.RD, "CreateSession", rtype="(o)")[0][0]
            call(self.session, self.RD + ".Session", "Start")
            (handle,), fdl = call(self.session, self.RD + ".Session", "ConnectToEIS",
                                  GLib.Variant("(a{sv})", ({},)), "(h)")
        except GLib.Error as e:
            sys.exit(f"Mutter RemoteDesktop refused: {e.message}")
        return fdl.get(handle)

    def close(self):
        from gi.repository import GLib
        try:
            self._call(self.session, self.RD + ".Session", "Stop")
        except GLib.Error:
            pass


class Input:
    def __init__(self, interactive_timeout=120):
        kind = provider()
        if kind == "portal":
            from portal import RemoteDesktop
            self.portal = RemoteDesktop()
        else:
            self.portal = {"kwin": KWinEIS, "mutter": MutterEIS}[kind]()
        fd = self.portal.connect(interactive_timeout)
        self.ctx = ei.ei_new_sender(None)
        ei.ei_configure_name(self.ctx, b"linux-computer-use")
        if ei.ei_setup_backend_fd(self.ctx, fd) != 0:
            sys.exit("ei_setup_backend_fd failed")
        self.devices, self.seq = [], 1
        self._wait_for_devices()
        # Mutter drops buttons and wheel from a new session until it has sent a motion
        # (waiting does not help); a zero relative motion first fixes it. GNOME only.
        self.unmoved = kind == "mutter"
        self.kind = kind

    def _events(self, timeout):
        r, _, _ = select.select([ei.ei_get_fd(self.ctx)], [], [], timeout)
        ei.ei_dispatch(self.ctx)
        while ev := ei.ei_get_event(self.ctx):
            yield ev, ei.ei_event_type_to_string(ei.ei_event_get_type(ev)).decode()
            ei.ei_event_unref(ev)

    def _wait_for_devices(self, timeout=3.0):
        end, resumed, quiet_since = time.monotonic() + timeout, set(), None
        while time.monotonic() < end:
            got = False
            for ev, name in self._events(0.05):
                got = got or name.startswith(("EI_EVENT_SEAT", "EI_EVENT_DEVICE"))  # cosmic-comp repeats KEYBOARD_MODIFIERS
                if name == "EI_EVENT_SEAT_ADDED":
                    ei.ei_seat_bind_capabilities(P(ei.ei_event_get_seat(ev)), *[I(c) for c in CAP_NAMES], P(None))
                elif name == "EI_EVENT_DEVICE_RESUMED":
                    dev = ei.ei_device_ref(ei.ei_event_get_device(ev))
                    if dev not in resumed:
                        resumed.add(dev)
                        ei.ei_device_start_emulating(dev, self.seq)
                        self.seq += 1
                        self.devices.append(dev)
                elif name == "EI_EVENT_DISCONNECT":
                    sys.exit("the compositor closed the EIS connection")
            # all devices usually arrive together; stop once things go quiet
            if self.devices and not got:
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since > 0.15:
                    break
            else:
                quiet_since = None
        if not self.devices:
            sys.exit("no EIS devices were resumed by the compositor")

    def dev(self, cap):
        for d in self.devices:
            if ei.ei_device_has_capability(d, cap):
                return d
        sys.exit(f"no device with capability {CAP_NAMES[cap]}")

    def frame(self, d, pause=0.012):
        ei.ei_device_frame(d, ei.ei_now(self.ctx))
        for _ in self._events(0):
            pass
        time.sleep(pause)

    # actions
    def move(self, x, y, settle=False):
        # settle: repeat the motion in a second frame. A jump into a window arrives as
        # wl_pointer.enter alone; libcosmic apps on GNOME ignore the enter position, so a
        # press right after it misses their resize border. A real mouse always sends more.
        d = self.dev(CAP_POINTER_ABSOLUTE)
        self.unmoved = False
        for _ in range(2 if settle else 1):
            ei.ei_device_pointer_motion_absolute(d, float(x), float(y))
            self.frame(d)

    def rmove(self, dx, dy):
        d = self.dev(CAP_POINTER)
        self.unmoved = False
        ei.ei_device_pointer_motion(d, float(dx), float(dy))
        self.frame(d)

    def _prime(self):
        if getattr(self, "unmoved", False):
            self.rmove(0, 0)

    def button(self, name, down):
        self._prime()
        d = self.dev(CAP_BUTTON)
        ei.ei_device_button_button(d, BUTTONS.get(name, None) or int(name, 0), down)
        self.frame(d)

    def click(self, name="left", count=1):
        for _ in range(count):
            self.button(name, True)
            self.button(name, False)
            time.sleep(0.04)

    def drag(self, x1, y1, x2, y2, step=None, button="left"):
        # Drag-and-drop between apps starts only when the first motion after the press is
        # small and still on the item (a ~190 px first jump cancelled it on COSMIC), and
        # drops register more reliably after a short hover over the target (GNOME).
        # step = largest move in px, with a 25 ms pause per move: libcosmic windows ignore
        # an edge resize made of bigger steps (KWin and GTK4 borders take any step size).
        if step is not None and (not math.isfinite(step) or step <= 0):
            raise ValueError("drag step must be a finite positive number")
        dist = max(abs(x2 - x1), abs(y2 - y1), 1)
        steps = math.ceil(dist / step) if step else max(20, round(dist / 40))
        self.move(x1, y1, settle=True)
        self.button(button, True)
        time.sleep(0.08)
        if step is None:
            for px in (3, 8):  # nudge toward the target, past the DnD threshold, still on the item
                f = min(px / dist, 0.5)
                self.move(x1 + (x2 - x1) * f, y1 + (y2 - y1) * f)
                time.sleep(0.03)
        for i in range(1, int(steps) + 1):
            self.move(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
            if step:
                time.sleep(0.025)
        time.sleep(0.15)
        nudge = min(2, step) if step is not None else 2
        self.move(x2 + nudge, y2 + nudge)  # a last small motion over the target, then hover
        self.move(x2, y2)
        time.sleep(0.2)
        self.button(button, False)

    def scroll(self, dy, dx=0):
        self._prime()
        d = self.dev(CAP_SCROLL)
        step_y = 1 if dy > 0 else -1
        step_x = 1 if dx > 0 else -1
        for _ in range(abs(dy)):
            ei.ei_device_scroll_discrete(d, 0, 120 * step_y)
            self.frame(d, 0.03)
        for _ in range(abs(dx)):
            ei.ei_device_scroll_discrete(d, 120 * step_x, 0)
            self.frame(d, 0.03)

    def key(self, code, down):
        d = self.dev(CAP_KEYBOARD)
        ei.ei_device_keyboard_key(d, code, down)
        self.frame(d, 0.01)

    def combo(self, spec):
        codes = [keycode(k) for k in spec.split("+")]
        for c in codes:
            self.key(c, True)
        for c in reversed(codes):
            self.key(c, False)

    def type(self, text):
        for ch in text:
            if ch not in CHARS:
                sys.exit(f"cannot type {ch!r} with the US keymap; use `paste` (or `paste-term` in terminals) instead")
            code, shift = CHARS[ch]
            if shift:
                self.key(KEYS["shift"], True)
            self.key(code, True)
            self.key(code, False)
            if shift:
                self.key(KEYS["shift"], False)

    def paste(self, text, combo="ctrl+v"):
        """Put text on the clipboard, press combo, then put the user's clipboard back."""
        def copy(data, mime=None):
            # wl-copy forks a server that keeps serving the selection: give it no pipes to
            # hold open, or a captured call never returns (it hung here once).
            r = subprocess.run(["wl-copy"] + (["--type", mime] if mime else []), input=data, timeout=10,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return r.returncode == 0
        # GNOME has no data-control protocol: wl-paste maps a surface for a moment to read
        # the clipboard, and focus does not always come back (a full-screen window lost it
        # to the one below). Note the focused window and put it back before the keys.
        def focused():
            if self.kind != "mutter":
                return None
            w = lcu_env.run_json("window", "active", check=False)[1]
            return w[0]["id"] if isinstance(w, list) and w else None

        def refocus(wid):
            if wid is None or focused() == wid:
                return True
            lcu_env.run_json("window", "activate", f"id:{wid}", check=False)
            time.sleep(0.3)
            return focused() == wid
        target = focused()
        saved = None
        try:
            types = subprocess.run(["wl-paste", "--list-types"], capture_output=True, timeout=5).stdout.decode().split()
            if types:
                # prefer the plain-text form; otherwise the first offered type (an image...)
                mime = next((t for t in types if t in ("text/plain;charset=utf-8", "UTF8_STRING")), types[0])
                r = subprocess.run(["wl-paste", "--no-newline", "--type", mime], capture_output=True, timeout=5)
                saved = (mime, r.stdout) if r.returncode == 0 else None
        except FileNotFoundError:
            sys.exit("paste needs wl-clipboard (wl-copy, wl-paste)")
        except subprocess.TimeoutExpired:
            # GNOME: wl-paste waits forever while a keep-above window has focus
            refocus(target)
            sys.exit("wl-paste did not answer, so the clipboard could not be saved; nothing was pasted "
                     "(GNOME: a keep-above window has focus; turn keep-above off, or use `type`)")
        try:
            if not copy(text.encode()):
                sys.exit("wl-copy failed")
            time.sleep(0.15)
            if not refocus(target):
                sys.exit("focus moved away while using the clipboard and could not be put back; nothing was pasted")
            self.combo(combo)
            time.sleep(0.4)  # apps read the clipboard asynchronously after the key
        finally:
            if saved:
                copy(saved[1], saved[0])
            else:
                subprocess.run(["wl-copy", "--clear"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            refocus(target)
        print(f"pasted {len(text)} characters; clipboard " + (f"restored ({saved[0]}, {len(saved[1])} bytes)"
                                                             if saved else "was empty and is cleared again"),
              file=sys.stderr)

    def regions(self):
        d = self.dev(CAP_POINTER_ABSOLUTE)
        i = 0
        while r := ei.ei_device_get_region(d, i):
            print(f"region {i}: x={ei.ei_region_get_x(r)} y={ei.ei_region_get_y(r)} "
                  f"w={ei.ei_region_get_width(r)} h={ei.ei_region_get_height(r)} "
                  f"scale={ei.ei_region_get_physical_scale(r):g}")
            i += 1
        for dv in self.devices:
            caps = [n for c, n in CAP_NAMES.items() if ei.ei_device_has_capability(dv, c)]
            print(f"device {ei.ei_device_get_name(dv).decode()}: {', '.join(caps)}")

    def close(self):
        for d in self.devices:
            ei.ei_device_stop_emulating(d)
        for _ in self._events(0.02):
            pass
        self.portal.close()


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    if argv[0] in ("--setup", "--forget") and provider() != "portal":
        print(f"nothing to {argv[0][2:]}: input on {lcu_env.desktop()} needs no grant")
        return
    if argv[0] == "--forget":
        from portal import forget_token
        forget_token()
        return
    if argv[0] == "--help-keys":
        print("named keys:", " ".join(sorted(KEYS)))
        print("typeable characters:", "".join(sorted(CHARS)).replace("\n", "\\n").replace("\t", "\\t"))
        return
    inp = Input()
    try:
        if argv[0] == "--setup":
            print("granted; the restore token is saved, later calls need no dialog")
            return
        if argv[0] == "--list-regions":
            inp.regions()
            return
        args = list(argv)

        def num(kind=float):
            return kind(args.pop(0))

        def opt_button():
            return args.pop(0) if args and (args[0] in BUTTONS) else "left"

        while args:
            a = args.pop(0)
            if a == "move":
                inp.move(num(), num(), settle=True)
            elif a == "rmove":
                inp.rmove(num(), num())
            elif a == "click":
                b = opt_button()
                n = num(int) if args and args[0].isdigit() else 1
                inp.click(b, n)
            elif a in ("down", "up"):
                inp.button(opt_button(), a == "down")
            elif a == "drag":
                x1, y1, x2, y2 = num(), num(), num(), num()
                b = opt_button()
                st = (args.pop(0), num())[1] if args and args[0] == "step" else None
                inp.drag(x1, y1, x2, y2, step=st, button=b)
            elif a == "scroll":
                inp.scroll(num(int))
            elif a == "hscroll":
                inp.scroll(0, num(int))
            elif a == "key":
                inp.combo(args.pop(0))
            elif a in ("keydown", "keyup"):
                inp.key(keycode(args.pop(0)), a == "keydown")
            elif a == "type":
                inp.type(args.pop(0))
            elif a in ("paste", "paste-term"):
                inp.paste(args.pop(0), "ctrl+v" if a == "paste" else "ctrl+shift+v")
            elif a == "sleep":
                time.sleep(num() / 1000)
            else:
                sys.exit(f"unknown action {a!r}; see --help")
    finally:
        inp.close()


if __name__ == "__main__":
    main(sys.argv[1:])
