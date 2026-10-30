"""Desktop detection and the glue every linux-computer-use script shares.

detect() decides which backend drives this session (kde, gnome or cosmic) from, in order:
  1. LCU_DESKTOP (set by `lcu --desktop D`, and by lcu for every child process),
  2. XDG_CURRENT_DESKTOP, confirmed by the compositor's own D-Bus name,
  3. the D-Bus names alone (a session started without XDG_CURRENT_DESKTOP).
Only Wayland sessions are supported: on X11 every desktop's tools are different.

tool(name, *args) -> argv that runs another lcu tool with the same interpreter and
desktop, so backends never hard-code each other's file names.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
LCU = ROOT / "lcu"
DESKTOPS = ("kde", "gnome", "cosmic")
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "linux-computer-use"

# XDG_CURRENT_DESKTOP token -> desktop, and the D-Bus name its compositor/shell owns
XDG = {"KDE": "kde", "GNOME": "gnome", "COSMIC": "cosmic"}
BUS_NAMES = {"kde": "org.kde.KWin", "gnome": "org.gnome.Mutter.RemoteDesktop", "cosmic": "com.system76.CosmicComp"}
# what each backend uses, for `lcu detect` and error messages
BACKENDS = {
    "kde": {"input": "KWin EIS (org.kde.KWin.EIS.RemoteDesktop)", "window": "temporary KWin script",
            "capture": "Spectacle stills; xdg ScreenCast portal for real-time video"},
    "gnome": {"input": "Mutter RemoteDesktop ConnectToEIS", "window": "Computer Use Bridge shell extension",
              "capture": "bridge extension stills; Mutter ScreenCast video"},
    "cosmic": {"input": "RemoteDesktop portal ConnectToEIS (one-time grant)",
               "window": "ext-foreign-toplevel-list + zcosmic-toplevel-info/manager",
               "capture": "ext-image-copy-capture"},
}


def bus_names():
    try:
        out = subprocess.run(["busctl", "--user", "list", "--no-legend", "--acquired"],
                             capture_output=True, text=True, timeout=5).stdout
        return {line.split()[0] for line in out.splitlines() if line.strip()}
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:  # no busctl: ask the bus itself
        out = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path",
                              "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.ListNames"],
                             capture_output=True, text=True, timeout=5).stdout
        return {n.strip(" '[]()\n,") for n in out.split(",")}
    except (OSError, subprocess.TimeoutExpired):
        return set()


def detect():
    """-> {desktop, session, xdg_current_desktop, evidence: [...], warnings: [...]}; desktop None if unknown."""
    session = os.environ.get("XDG_SESSION_TYPE") or ("wayland" if os.environ.get("WAYLAND_DISPLAY")
                                                     else "x11" if os.environ.get("DISPLAY") else "?")
    xdg = os.environ.get("XDG_CURRENT_DESKTOP", "")
    res = {"desktop": None, "session": session, "xdg_current_desktop": xdg, "evidence": [], "warnings": []}
    forced = os.environ.get("LCU_DESKTOP", "").lower()
    if forced:
        if forced not in DESKTOPS:
            sys.exit(f"LCU_DESKTOP={forced!r} is not one of {', '.join(DESKTOPS)}")
        res["desktop"] = forced
        res["evidence"].append(f"LCU_DESKTOP={forced}")
        return res
    names = bus_names()
    on_bus = [d for d in DESKTOPS if BUS_NAMES[d] in names]
    from_xdg = [XDG[t] for t in xdg.upper().split(":") if t in XDG]
    if from_xdg:
        d = from_xdg[0]
        res["desktop"] = d
        res["evidence"].append(f"XDG_CURRENT_DESKTOP={xdg}")
        if d in on_bus:
            res["evidence"].append(f"{BUS_NAMES[d]} is on the session bus")
        else:
            res["warnings"].append(f"{BUS_NAMES[d]} is not on the session bus; the {d} backend may not work")
    elif len(on_bus) == 1:
        res["desktop"] = on_bus[0]
        res["evidence"].append(f"{BUS_NAMES[on_bus[0]]} is on the session bus (XDG_CURRENT_DESKTOP={xdg or 'unset'})")
    if session != "wayland":
        res["warnings"].append(f"session type is {session}: these tools need a Wayland session")
    return res


def desktop():
    """The backend name, or exit with an explanation."""
    d = detect()
    if not d["desktop"]:
        sys.exit(f"unsupported desktop (XDG_CURRENT_DESKTOP={d['xdg_current_desktop'] or 'unset'}, "
                 f"session {d['session']}): linux-computer-use drives KDE Plasma 6, GNOME and COSMIC on Wayland. "
                 "Force one with `lcu --desktop kde|gnome|cosmic` if detection is wrong.")
    return d["desktop"]


def tool(name, *args):
    """argv running `lcu NAME ARGS` with this interpreter and the already detected desktop."""
    return [sys.executable, "-s", str(LCU), "--desktop", desktop(), name, *map(str, args)]


def run_json(name, *args, check=True):
    """Run an lcu tool and parse its JSON stdout. check=False returns (returncode, data|text)."""
    r = subprocess.run(tool(name, *args), capture_output=True, text=True)
    if not check:
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            return r.returncode, (r.stdout + r.stderr).strip()
    if r.returncode:
        try:
            msg = json.loads(r.stdout).get("error")
        except (ValueError, AttributeError):
            msg = None
        sys.exit(msg or r.stdout.strip() or r.stderr.strip() or f"lcu {name} failed ({r.returncode})")
    return json.loads(r.stdout)
