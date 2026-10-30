#!/usr/bin/python3
"""Keep LEARNINGS.md, the skill's log of lessons from real sessions, usable.

  lcu learn add --kind KIND --title T --what W --do D --evidence E [--app APP] [--desktop D] [--local]
  lcu learn list [--app SUBSTRING] [--kind KIND] [--desktop D|any] [--all]
  lcu learn check            # exit 1 on a malformed or privacy-leaking entry
  lcu learn versions         # the desktop stack an entry gets stamped with

KIND: new (a capability or trick), better (a better way than SKILL.md says),
broken (SKILL.md advice that failed or no longer works), app (how one app behaves).
DESKTOP: kde, gnome, cosmic, or all for a lesson that does not depend on the desktop
(an Electron or Flatpak quirk, a website, the skill's shared scripts). `add` defaults
to the detected desktop; `list` shows the detected desktop's entries plus `all` ones
(--desktop any shows every entry).
Entries are appended with today's date, Status: active and the current desktop stack's
versions; `check` also lists this desktop's active entries recorded on a different
stack so they can be re-verified.

LEARNINGS.md is shared with everyone who installs the skill. --local writes to
LEARNINGS.local.md instead (git-ignored), for lessons that only matter on this
machine or need software most users do not have; list and check read both.
"""
import argparse, datetime, os, re, subprocess, sys
from pathlib import Path

LOG = Path(os.environ.get("LCU_LEARN_LOG") or Path(__file__).resolve().parent.parent / "LEARNINGS.md")
LOCAL = LOG.with_name("LEARNINGS.local.md")
LOCAL_HEAD = """# Local learnings

Lessons for this machine only (git-ignored, never published): same format as
LEARNINGS.md, for apps or setups most users of the skill do not have.

## Entries
"""
KINDS = ("new", "better", "broken", "app")
STATUSES = ("active", "promoted", "superseded", "wrong")
FIELDS = ("Status", "Desktop", "Seen on", "What", "Do", "Evidence")
DESKTOPS = ("kde", "gnome", "cosmic", "all")
HEAD = re.compile(r"^### (\d{4}-\d{2}-\d{2}) · (\w+) · (.+)$")
FIELD = re.compile(r"^- ([A-Za-z ]+): (.*)$")
# LEARNINGS.md is public: its entries must not carry the user's paths, accounts or secrets.
PRIVATE = [
    (re.compile(r"/home/(?!<user>)[A-Za-z0-9_.-]+"), "home path (write ~ or /home/<user>)"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "email address"),
    (re.compile(r"\b(ghp_|gho_|github_pat_|sk-|xox[bp]-|AKIA)[A-Za-z0-9_-]{8,}"), "token"),
    (re.compile(r"(?i)\b(password|passwd|secret|api[_ ]?key)\s*[:=]\s*\S+"), "credential"),
    (re.compile(r"[?&]list=PL[\w-]+|youtu\.be/\S+|watch\?v=\S+"), "personal media link"),
]


def pkg_version(pkg):
    """Installed version from pacman, rpm or dpkg, else '?'."""
    for cmd in (["pacman", "-Q", pkg], ["rpm", "-q", "--qf", "%{VERSION}", pkg],
                ["dpkg-query", "-W", "-f", "${Version}", pkg]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0 and r.stdout.strip():
            v = r.stdout.split()[-1]
            return v.split(":", 1)[-1].split("-")[0]  # drop epoch and release
    return "?"


def bin_version(*cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.split()
        return out[-1] if out else "?"
    except (OSError, subprocess.TimeoutExpired):
        return "?"


def current_desktop():
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import lcu_env
        return lcu_env.detect()["desktop"]
    except (ImportError, SystemExit):
        return None


def versions(desk=None):
    desk = desk or current_desktop()
    if desk == "kde":
        return (f"KWin {bin_version('kwin_wayland', '--version')}, Plasma {bin_version('plasmashell', '--version')}, "
                f"libei {pkg_version('libei')}, spectacle {pkg_version('spectacle')}")
    if desk == "gnome":
        return (f"GNOME Shell {bin_version('gnome-shell', '--version')}, mutter {pkg_version('mutter')}, "
                f"libei {pkg_version('libei')}, gtk4 {pkg_version('gtk4')}")
    if desk == "cosmic":
        return ", ".join(f"{p} {pkg_version(p)}" for p in ("cosmic-comp", "xdg-desktop-portal-cosmic", "libei", "gtk4"))
    return "unknown desktop"


def parse(text, name="LEARNINGS.md"):
    entries, cur = [], None
    for n, line in enumerate(text.splitlines(), 1):
        m = HEAD.match(line)
        if m:
            cur = {"file": name, "line": n, "date": m[1], "kind": m[2], "title": m[3].strip(), "fields": {}, "raw": [line]}
            entries.append(cur)
        elif cur is not None and line.startswith("## "):
            cur = None
        elif cur is not None:
            cur["raw"].append(line)
            f = FIELD.match(line)
            if f:
                cur["fields"][f[1]] = f[2].strip()
    return entries


def load():
    entries = parse(LOG.read_text(), LOG.name)
    if LOCAL.exists():
        entries += parse(LOCAL.read_text(), LOCAL.name)
    return entries


def problems(entries):
    out, seen = [], {}
    for e in entries:
        where = f"{e['file']}:{e['line']} '{e['title']}'"
        try:
            datetime.date.fromisoformat(e["date"])
        except ValueError:
            out.append(f"{where}: bad date {e['date']}")
        if e["kind"] not in KINDS:
            out.append(f"{where}: kind '{e['kind']}' not one of {', '.join(KINDS)}")
        for f in FIELDS:
            if not e["fields"].get(f):
                out.append(f"{where}: missing '- {f}:'")
        st = e["fields"].get("Status", "").split()[0] if e["fields"].get("Status") else ""
        if st and st not in STATUSES:
            out.append(f"{where}: status '{st}' not one of {', '.join(STATUSES)}")
        if e["fields"].get("Desktop") and e["fields"]["Desktop"] not in DESKTOPS:
            out.append(f"{where}: desktop '{e['fields']['Desktop']}' not one of {', '.join(DESKTOPS)}")
        if e["kind"] == "app" and not e["fields"].get("App"):
            out.append(f"{where}: kind app needs '- App:'")
        key = e["title"].lower()
        if key in seen:
            out.append(f"{where}: same title as {seen[key]}; update that entry instead")
        seen[key] = f"{e['file']}:{e['line']}"
        if e["file"] != LOCAL.name:
            body = "\n".join(e["raw"])
            for rx, what in PRIVATE:
                if rx.search(body):
                    out.append(f"{where}: contains a {what}; LEARNINGS.md is public (use --local)")
    return out


def cmd_add(a):
    target = LOCAL if a.local else LOG
    if any(e["title"].lower() == a.title.lower() for e in load()):
        sys.exit(f"an entry titled '{a.title}' exists; edit it instead")
    desk = a.desktop or current_desktop()
    if desk not in DESKTOPS:
        sys.exit("cannot tell the desktop; pass --desktop kde|gnome|cosmic|all")
    lines = [f"### {datetime.date.today()} · {a.kind} · {a.title}", "- Status: active"]
    if a.app:
        lines.append(f"- App: {a.app}")
    lines += [f"- Desktop: {desk}", f"- Seen on: {versions()}", f"- What: {a.what}", f"- Do: {a.do}",
              f"- Evidence: {a.evidence}"]
    bad = problems(parse("\n".join(lines), target.name))
    if bad:
        sys.exit("not added:\n  " + "\n  ".join(bad))
    text = target.read_text() if target.exists() else LOCAL_HEAD
    target.write_text(text.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n")
    print(f"added to {target}:\n" + "\n".join(lines))


def cmd_list(a):
    desk = a.desktop or current_desktop()
    for e in load():
        f = e["fields"]
        if not a.all and not f.get("Status", "").startswith("active"):
            continue
        if desk and desk != "any" and f.get("Desktop") not in (desk, "all"):
            continue
        if a.kind and e["kind"] != a.kind:
            continue
        if a.app and a.app.lower() not in (f.get("App", "") + " " + e["title"]).lower():
            continue
        print(f"[{e['file']}]\n" + "\n".join(e["raw"]).rstrip() + "\n")


def cmd_check(a):
    entries = load()
    bad = problems(entries)
    desk = current_desktop()
    now = versions(desk)
    stale = [e for e in entries if e["fields"].get("Status", "").startswith("active")
             and e["fields"].get("Desktop") == desk and e["fields"].get("Seen on") and e["fields"]["Seen on"] != now]
    for e in stale:
        print(f"re-verify (recorded on {e['fields']['Seen on']}; now {now}): {e['title']}")
    for p in bad:
        print("ERROR", p)
    active = sum(e["fields"].get("Status", "").startswith("active") for e in entries)
    local = sum(e["file"] == LOCAL.name for e in entries)
    print(f"{len(entries)} entries ({local} local), {active} active, {len(bad)} errors, {len(stale)} to re-verify")
    sys.exit(1 if bad else 0)


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = p.add_subparsers(dest="cmd", required=True)
s = sub.add_parser("add")
s.add_argument("--kind", choices=KINDS, required=True)
s.add_argument("--title", required=True, help="one line, unique; the lesson itself, not the task")
s.add_argument("--what", required=True, help="what happened or what is true")
s.add_argument("--do", required=True, help="what to do instead / how to use it")
s.add_argument("--evidence", required=True, help="the command and observation that verified it")
s.add_argument("--app", help="window class or app name, required for --kind app")
s.add_argument("--local", action="store_true", help="write to LEARNINGS.local.md (this machine only, not published)")
s.add_argument("--desktop", choices=DESKTOPS, help="default: the detected desktop; all = not desktop-specific")
s.set_defaults(fn=cmd_add)
s = sub.add_parser("list")
s.add_argument("--app")
s.add_argument("--kind", choices=KINDS)
s.add_argument("--all", action="store_true", help="include promoted/superseded/wrong entries")
s.add_argument("--desktop", choices=DESKTOPS[:-1] + ("any",), help="default: the detected desktop (plus `all` entries)")
s.set_defaults(fn=cmd_list)
sub.add_parser("check").set_defaults(fn=cmd_check)
sub.add_parser("versions").set_defaults(fn=lambda a: print(versions()))
a = p.parse_args()
if a.cmd == "add" and a.kind == "app" and not a.app:
    p.error("--kind app needs --app")
a.fn(a)
