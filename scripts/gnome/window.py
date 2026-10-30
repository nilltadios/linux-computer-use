#!/usr/bin/python3
"""List and control windows on GNOME Wayland through the Computer Use Bridge extension.

GNOME Shell refuses window lists (Introspect.GetWindows), Eval and screenshots to
outside callers, so the small extension in extension/ runs these inside the shell
and answers over D-Bus (org.gnome.Shell /org/claude/ComputerUse). It must be
installed and enabled once (scripts/setup.sh), then active after a login.

Usage:
  lcu window list [--all]                  # JSON, one object per window, topmost first
  lcu window active                        # the focused window
  lcu window ACTION MATCH [ARGS]
  lcu window launch [--on OUTPUT] [--maximize|--fullscreen] [--match MATCH] -- CMD [ARGS]
MATCH: id:N | class:PREFIX (WM_CLASS, GTK app id, Flatpak app id or .desktop id,
       case-insensitive) | title:SUBSTRING (case-insensitive) | pid:N.  ACTION
       applies to every match unless --first is given (then the topmost one).
ACTIONS:
  wait-stable         wait until it exists and its geometry is unchanged for 0.4 s
  activate            raise + focus (unminimizes, switches workspace)
  raise               raise without taking focus
  minimize | unminimize
  maximize | unmaximize
  fullscreen | unfullscreen
  keep-above | no-keep-above
  close               ask the window to close (like the title-bar X; the app may
                      prompt to save). Never use on the user's apps without asking.
  move-to OUTPUT      e.g. DP-1, eDP-1 (keeps size, centres)
  geometry X Y W H    logical pixels (frame, without CSD shadows)
  info                print the matched windows
--all also lists panels, popups and other non-normal windows.

launch starts CMD detached and waits (20 s) for its new window, then prints it.
GNOME opens new windows on the monitor that holds the pointer and apps do not
reliably restore their maximized state, so --on moves the pointer to the middle of
OUTPUT before starting (no click) and moves the window there if it still opened
elsewhere; --maximize/--fullscreen apply after it appears. --match picks the window
when the app opens more than one (default: the first new window).
"""
import json
import os
import subprocess
import sys
import time

from gcu_common import outputs, windows

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lcu_env import tool  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def run(action, match="", args=(), first=False, all_windows=False):
    if action == "move-to":
        outs = outputs()
        if args[0] not in outs:
            return {"ok": False, "error": f"no output {args[0]}; have {', '.join(outs)}"}
        x, y, w, h = outs[args[0]]
        args = [{"x": x, "y": y, "width": w, "height": h}]
    return windows(action, match, args, first, all_windows)


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
    opts, cmd = argv[:argv.index("--")] if "--" in argv else argv, argv[argv.index("--") + 1:] if "--" in argv else []
    if not cmd:
        sys.exit("launch needs -- CMD [ARGS]")
    on = opts[opts.index("--on") + 1] if "--on" in opts else None
    match = opts[opts.index("--match") + 1] if "--match" in opts else None
    if on:
        outs = outputs()
        if on not in outs:
            sys.exit(f"no output {on}; have {', '.join(outs)}")
        x, y, w, h = outs[on]
        subprocess.run(tool("input", "move", x + w // 2, y + h // 2), check=True)
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
        run("move-to", m, [on])
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
