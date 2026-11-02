#!/usr/bin/python3
"""List and control windows on COSMIC (cosmic-comp) through its Wayland protocols.

ext-foreign-toplevel-list gives every window an id, title and app id;
zcosmic-toplevel-info adds state, geometry, output and workspace;
zcosmic-toplevel-manager acts on them. All are offered to ordinary clients: no
extension, no dialog.

Usage:
  lcu window list                          # JSON, active window first
  lcu window active                        # the focused window
  lcu window workspaces                    # workspaces per output, active flag
  lcu window ACTION MATCH [ARGS] [--first]
  lcu window launch [--on OUTPUT] [--maximize|--fullscreen] [--match MATCH] -- CMD [ARGS]
MATCH: id:ID (the ext-foreign-toplevel identifier from `list`) | class:APP_ID (exact,
       prefix, or last dot-component, case-insensitive) | title:SUBSTRING | active.
       ACTION applies to every match unless --first is given.
ACTIONS:
  info                print the matched windows
  wait-stable         wait until it exists and its geometry is unchanged for 0.4 s
  activate            raise + focus (unminimizes, switches workspace)
  minimize | unminimize
  maximize | unmaximize
  fullscreen [OUTPUT] | unfullscreen
  sticky | unsticky   show on every workspace
  move-to OUTPUT      move to the active workspace of OUTPUT (e.g. DP-1, eDP-1)
  close               ask the window to close (like its X button; the app may prompt
                      to save). Never use on the user's apps without asking.
  drag-move MATCH X Y --grab GX GY [--fast|--slow|--duration MS]
                      move it by a real header drag so its frame lands at X,Y (0.4 s)
  drag-resize MATCH W H [--edge EDGE] [--left] [--top] [--step PX]
                      resize it by dragging an edge or corner with the pointer
cosmic-comp has no protocol request to move a window to x,y, resize it or keep it
above others; the two drag commands do it with the pointer, like a person.

launch starts CMD detached, waits (20 s) for its new window and prints it. --on moves it
to OUTPUT if it opened elsewhere; --maximize/--fullscreen apply after it appears.
"""
import json
import subprocess
import sys
import time

from ccu_common import Desktop, public


def info(match, first=False):
    d = Desktop()
    hits = d.find(match, first)
    d.close()
    return hits


def wait_stable(match, timeout=10):
    """-> the matched windows once they exist and their geometry is unchanged for 0.4 s, else None."""
    last, since, end = None, time.monotonic(), time.monotonic() + timeout
    while time.monotonic() < end:
        hits = info(match, first=True)
        geo = [(w["x"], w["y"], w["width"], w["height"], w["output"]) for w in hits] or None
        if geo != last:
            last, since = geo, time.monotonic()
        elif geo and time.monotonic() - since >= 0.4:
            return hits
        time.sleep(0.1)
    return None


def act(action, match, args, first):
    d = Desktop()
    hits = d.find(match, first)
    if not hits:
        sys.exit(f"no window matches {match!r}; see lcu window list")
    for w in hits:
        d.act(w, action, args[0] if args else None)
    ids = [w["id"] for w in hits]
    d.close()
    time.sleep(0.2)  # the compositor applies changes asynchronously
    d = Desktop()
    out = [public(w) for w in d.windows if w["id"] in ids]
    d.close()
    return out


def launch(argv):
    opts, cmd = (argv[:argv.index("--")], argv[argv.index("--") + 1:]) if "--" in argv else (argv, [])
    if not cmd:
        sys.exit("launch needs -- CMD [ARGS]")
    on = opts[opts.index("--on") + 1] if "--on" in opts else None
    match = opts[opts.index("--match") + 1] if "--match" in opts else None
    d = Desktop()
    if on:
        d.output(on)  # validate
    before = {w["id"] for w in d.windows}
    d.close()
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    win, end = None, time.monotonic() + 20
    while not win and time.monotonic() < end:
        time.sleep(0.2)
        d = Desktop()
        fresh = [w for w in d.windows if w["id"] not in before and (not match or w in d.find(match))]
        win = public(fresh[0]) if fresh else None
        d.close()
    if not win:
        sys.exit(f"no new window appeared within 20 s for {' '.join(cmd)}")
    m = f"id:{win['id']}"
    wait_stable(m)
    if on and info(m)[0]["output"] != on:
        act("move-to", m, [on], True)
        wait_stable(m)
    for flag in ("--maximize", "--fullscreen"):
        if flag in opts:
            act(flag[2:], m, [], True)
    time.sleep(0.3)
    print(json.dumps([public(w) for w in (wait_stable(m) or info(m))], indent=1))
    return 0


def workspaces():
    d = Desktop()
    res = []
    for g in d.groups:
        outs = [d.by_proxy[o.id].name for o in g.data["outputs"] if o.id in d.by_proxy]
        for ws in g.data["workspaces"]:
            res.append({**d._ws_name(ws), "coordinates": ws.data["coordinates"],
                        "windows": [w["id"] for w in d.windows if d._ws_name(ws) in w["workspace"]
                                    and w["output"] in outs]})
    d.close()
    return res


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "launch":
        return launch(argv[1:])
    first = "--first" in argv
    argv = [a for a in argv if a != "--first"]
    action = argv[0]
    if action in ("list", "active"):
        d = Desktop()
        print(json.dumps([public(w) for w in (d.windows if action == "list" else d.active())], indent=1))
        return 0
    if action == "workspaces":
        print(json.dumps(workspaces(), indent=1))
        return 0
    if len(argv) < 2:
        sys.exit("need a MATCH, see --help")
    match, args = argv[1], argv[2:]
    if action == "info":
        hits = info(match, first)
        print(json.dumps([public(w) for w in hits], indent=1))
        return 0 if hits else 1
    if action == "wait-stable":
        hits = wait_stable(match)
        if not hits:
            sys.exit(f"{match} did not appear or settle within 10 s")
        print(json.dumps([public(w) for w in hits], indent=1))
        return 0
    if action in ("drag-move", "drag-resize"):
        import drag
        return (drag.drag_move if action == "drag-move" else drag.drag_resize)(argv[1:])
    if action in ("geometry", "keep-above", "no-keep-above", "raise"):
        sys.exit(f"{action}: cosmic-comp offers no protocol for this; see --help")
    known = ("activate", "minimize", "unminimize", "maximize", "unmaximize", "fullscreen", "unfullscreen",
             "sticky", "unsticky", "move-to", "close")
    if action not in known:
        sys.exit(f"unknown action {action!r}; see --help")
    if action == "move-to" and not args:
        sys.exit("move-to needs an OUTPUT")
    print(json.dumps(act(action, match, args, first), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
