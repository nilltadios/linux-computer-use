#!/usr/bin/python3
"""Find and operate app controls by name through AT-SPI (accessibility), on KDE, GNOME and COSMIC.

  lcu a11y apps                                   # accessible apps: pid, name
  lcu a11y tree APP [--depth 8] [--all]           # controls: role, name, states, screen box
  lcu a11y find APP --name TEXT [--role ROLE]     # JSON matches with screen centre (logical px)
  lcu a11y press APP --name TEXT [--role ROLE]    # run the control's default action (no mouse)

APP: a pid, or a case-insensitive substring of the app's accessible name, or of the
     class/app id or title of one of its windows (from `lcu window list`).
TEXT: case-insensitive substring of the control's name (use --exact for whole-name match).

Uses libatspi through PyGObject (gi.repository.Atspi). Wayland apps do not know where
their window is, so screen positions are the window's origin from the compositor (the
client area on KDE, the frame on GNOME and COSMIC) plus the control's window-relative
box. Windows are matched to the app by pid, or by title where the compositor gives no
pid (COSMIC). Click positions with `lcu input`; prefer `press` when the control has an
action (buttons, menu items, check boxes): no coordinates.

GTK4 apps register on the accessibility bus by themselves. GTK3, Qt and Electron apps
register only when the bus is enabled at their start (`gsettings set
org.gnome.desktop.interface toolkit-accessibility true`, which sets org.a11y.Status
IsEnabled); Electron apps also need --force-renderer-accessibility. COSMIC's own apps
(libcosmic/iced) do not use AT-SPI and show nothing here: use `lcu ocr` for them.
"""
import argparse
import json
import sys
import warnings

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402

from lcu_env import desktop, run_json  # noqa: E402

STATES = (("showing", Atspi.StateType.SHOWING), ("focused", Atspi.StateType.FOCUSED),
          ("checked", Atspi.StateType.CHECKED), ("enabled", Atspi.StateType.ENABLED),
          ("selected", Atspi.StateType.SELECTED))


def apps():
    desk = Atspi.get_desktop(0)
    for i in range(desk.get_child_count()):
        try:
            a = desk.get_child_at_index(i)
            if a is not None:
                yield a, a.get_process_id(), a.get_name() or ""
        except Exception:
            continue


def all_windows():
    code, wins = run_json("window", "list", "--all", check=False)
    if code or not isinstance(wins, list):
        print("note: no window list from the compositor; names and actions work, positions do not",
              file=sys.stderr)
        return []
    return wins


def app_titles(app):
    """Names of the app's top-level frames (= its window titles)."""
    out = []
    try:
        for i in range(min(app.get_child_count(), 50)):
            c = app.get_child_at_index(i)
            if c is not None and c.get_name():
                out.append(c.get_name())
    except Exception:
        pass
    return out


def pick_app(spec):
    wins = all_windows()
    cands = []
    for a, pid, name in apps():
        if spec.isdigit():
            ok = pid == int(spec)
        else:
            s = spec.lower()
            titles = app_titles(a)
            ok = s in name.lower() or any(
                (w.get("pid") == pid if w.get("pid") else w["title"] in titles)
                and any(s in (w.get(k) or "").lower() for k in ("class", "app_id", "desktop_file", "desktop_app",
                                                                 "sandboxed_app_id", "title"))
                for w in wins)
        if ok:
            cands.append((a, pid, name))
    if not cands:
        hint = "COSMIC's own apps never appear; " if desktop() == "cosmic" else ""
        sys.exit(f"no accessible app matches {spec!r}; see `apps` ({hint}GTK3/Qt/Electron apps need "
                 "toolkit-accessibility on before they start; use `lcu ocr` otherwise)")
    return cands[0], wins


def states(o):
    try:
        ss = o.get_state_set()
        return [n for n, st in STATES if ss.contains(st)]
    except Exception:
        return []


def toplevel(o):
    p = o
    try:
        while p is not None and p.get_parent() is not None and p.get_parent().get_role() != Atspi.Role.APPLICATION:
            p = p.get_parent()
    except Exception:
        pass
    return p


def screen_box(o, pid, wins):
    """Window-relative extents + the frame origin of the matching toplevel window."""
    try:
        if o.get_component_iface() is None:
            return None
        e = o.get_extents(Atspi.CoordType.WINDOW)
    except Exception:
        return None
    if e.width <= 0 or e.height <= 0:
        return None
    top = toplevel(o)
    title = (top.get_name() or "") if top is not None else ""
    mine = [w for w in wins if w.get("pid") == pid and w.get("x") is not None]
    if mine:  # KDE, GNOME: the app's windows by pid, then the one whose title matches the frame
        w = next((w for w in mine if title and w["title"] == title), None) or \
            next((w for w in mine if title and w["title"].startswith(title)), None) or \
            next((w for w in mine if w.get("active")), None) or mine[0]
    else:  # COSMIC: no pids; the window whose title is the accessible frame's name
        mine = [w for w in wins if title and w["title"] == title and w.get("x") is not None] or \
            [w for w in wins if title and w["title"].startswith(title) and w.get("x") is not None]
        if not mine:
            return None
        w = next((w for w in mine if w.get("active")), None) or mine[0]
    w = dict(w, **w.get("client", {}))  # KDE reports the client area separately from the frame
    x, y = w["x"] + e.x, w["y"] + e.y
    return {"x": x, "y": y, "width": e.width, "height": e.height,
            "center": [round(x + e.width / 2), round(y + e.height / 2)], "window": w["id"]}


def walk(o, depth, maxdepth):
    yield o, depth
    if depth >= maxdepth:
        return
    try:
        n = o.get_child_count()
    except Exception:
        return
    for i in range(min(n, 2000)):
        try:
            c = o.get_child_at_index(i)
        except Exception:
            continue
        if c is not None:
            yield from walk(c, depth + 1, maxdepth)


def matches(args, app):
    want = args.name.lower() if args.name is not None else None
    for o, d in walk(app, 0, args.depth):
        try:
            name, role = o.get_name() or "", o.get_role_name()
        except Exception:
            continue
        if args.role and role.lower() != args.role.lower():
            continue
        if want is not None:
            n = name.lower()
            if (args.exact and n != want) or (not args.exact and want not in n):
                continue
        if not args.all and "showing" not in states(o):
            continue
        yield o, d, name, role


def actions(o):
    try:
        if o.get_action_iface() is None:
            return []
        with warnings.catch_warnings():  # get_action_name is deprecated but the only name getter in libatspi 2.56
            warnings.simplefilter("ignore", DeprecationWarning)
            return [o.get_action_name(i) for i in range(o.get_n_actions())]
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["apps", "tree", "find", "press"])
    ap.add_argument("app", nargs="?")
    ap.add_argument("--name")
    ap.add_argument("--role", help="e.g. 'button', 'menu item', 'check box', 'text', 'combo box'")
    ap.add_argument("--exact", action="store_true")
    ap.add_argument("--depth", type=int, default=30)
    ap.add_argument("--all", action="store_true", help="include controls that are not showing")
    args = ap.parse_args()

    if args.cmd == "apps":
        for _, pid, name in apps():
            print(f"{pid}\t{name}")
        return
    if not args.app:
        sys.exit("APP is required")
    (app, pid, appname), wins = pick_app(args.app)

    if args.cmd == "tree":
        for o, d, name, role in matches(args, app):
            box = screen_box(o, pid, wins)
            where = f" @{box['center'][0]},{box['center'][1]} {box['width']}x{box['height']}" if box else ""
            print(f"{'  ' * d}{role}: {name!r}{where} [{','.join(states(o))}]")
        return

    if args.name is not None and not args.name.strip():
        sys.exit("--name must not be empty (an empty name would match every control)")
    if not args.name and not args.role:
        sys.exit("find/press need --name and/or --role")
    hits = [(o, {"name": name, "role": role, "states": states(o), "actions": actions(o),
                 "box": screen_box(o, pid, wins)}) for o, d, name, role in matches(args, app)]
    if args.cmd == "find":
        print(json.dumps({"app": appname, "pid": pid, "matches": [h[1] for h in hits]}, indent=1))
        if not hits:
            print(f"no match within --depth {args.depth}; libadwaita apps nest deep, try --depth 50", file=sys.stderr)
        sys.exit(0 if hits else 1)
    actionable = [h for h in hits if h[1]["actions"]]
    if not actionable:
        sys.exit(f"no matching control with an action ({len(hits)} matches without one); click its box centre instead")
    o, info = actionable[0]
    ok = o.do_action(0)
    print(json.dumps({"pressed": info["name"], "role": info["role"], "action": info["actions"][0], "ok": bool(ok),
                      "other_matches": len(actionable) - 1}))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
