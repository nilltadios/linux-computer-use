#!/usr/bin/python3
"""Load (or reload) the Computer Use Bridge extension into the running GNOME Shell,
without logging out.

GNOME Shell on Wayland only discovers new extensions at login and caches extension
code once imported. This drives Looking Glass (Alt+F2 -> lg) with `lcu input` and
evaluates ExtensionManager calls there, loading the extension from a fresh copy in
$XDG_RUNTIME_DIR so changed code is picked up. Before each typing step it checks
gnome-shell's accessibility tree (the dialog may open on any monitor, and OCR would
also match the same words inside other windows); on a mismatch it presses Escape and
stops. It needs
org.gnome.shell development-tools = true (Looking Glass); with --allow-devtools it
turns that on for the duration and restores it afterwards.

  load-extension-live.py [--allow-devtools] [--force]

Exit 0 when the bridge answers with "bridge-version" from extension/metadata.json.
Takes over keyboard focus for ~5 s; run only when the user agreed or is away.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from gcu_common import BRIDGE, UUID, bridge_ok, get_prop

sys.path.insert(1, str(Path(__file__).resolve().parent.parent))
from lcu_env import tool  # noqa: E402

HERE = Path(__file__).resolve().parent
SRC = HERE / "extension" / UUID
PY = [sys.executable]


def running():
    """-> (version, path) of the running bridge, or (None, None)."""
    try:
        if bridge_ok():
            ver = get_prop(*BRIDGE, "Version")
            try:
                return ver, get_prop(*BRIDGE, "Path")
            except Exception:
                return ver, None
    except Exception:
        pass
    return None, None


def inp(*a):
    subprocess.run(tool("input", *a), check=True)


def in_shell(name, role, tries=8):
    """True once gnome-shell shows a control `name` and has a focused text entry."""
    a11y = tool("a11y", "find", "gnome-shell", "--depth", "40")
    for _ in range(tries):
        if subprocess.run(a11y + ["--name", name, "--role", role, "--exact"], capture_output=True).returncode == 0:
            r = subprocess.run(a11y + ["--role", "text"], capture_output=True, text=True)
            if r.returncode == 0 and any("focused" in m["states"] for m in json.loads(r.stdout)["matches"]):
                return True
        time.sleep(0.25)
    return False


def gsettings(*a):
    return subprocess.run(["gsettings", *a], capture_output=True, text=True).stdout.strip()


def main():
    # GNOME refuses a changed metadata "version" until logout, so the bridge's own version
    # (its D-Bus Version property) lives in "bridge-version"
    want = json.loads((SRC / "metadata.json").read_text())["bridge-version"]
    have, _ = running()
    if have == want and "--force" not in sys.argv:
        print(json.dumps({"bridge": "already running", "version": have}))
        return 0
    devtools = gsettings("get", "org.gnome.shell", "development-tools")
    if devtools != "true":
        if "--allow-devtools" not in sys.argv:
            sys.exit("Looking Glass is off (org.gnome.shell development-tools=false); rerun with --allow-devtools "
                     "or log out and back in to load the extension")
        gsettings("set", "org.gnome.shell", "development-tools", "true")
    copy = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / f"claude-gcu-{int(time.time())}" / UUID
    shutil.copytree(SRC, copy)
    js = ("(async()=>{const em=Main.extensionManager,u='%s',o=em.lookup(u);if(o)await em.unloadExtension(o);"
          "const e=em.createExtensionObject(u,Gio.File.new_for_path('%s'),2);await em.loadExtension(e);"
          "em.enableExtension(u)})()") % (UUID, copy)
    try:
        inp("key", "alt+f2")
        if not in_shell("Run a Command", "label"):
            inp("key", "escape")
            sys.exit("the Run a Command dialog did not appear; nothing was typed")
        inp("type", "lg", "key", "enter")
        if not in_shell("Evaluator", "button"):
            inp("key", "escape")
            sys.exit("Looking Glass did not open; pressed Escape")
        inp("type", js, "key", "enter")
        end = time.monotonic() + 5
        while time.monotonic() < end and running() != (want, str(copy)):
            time.sleep(0.2)
        inp("key", "escape")
    finally:
        if devtools != "true":
            gsettings("set", "org.gnome.shell", "development-tools", devtools)
    have, path = running()
    ok = (have, path) == (want, str(copy))
    print(json.dumps({"bridge": "loaded" if ok else "failed", "version": have, "from": path}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
