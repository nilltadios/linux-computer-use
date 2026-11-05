#!/usr/bin/python3 -s
"""Offline tests of the grant lookup and slow-answer notice in scripts/portal.py."""
import contextlib, io, os, sys, tempfile, types
from pathlib import Path
root = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import portal
st = Path(root) / "linux-computer-use"; st.mkdir()
old = st / "remote-desktop.token"; new = portal.TOKEN
cos = Path(root) / "cosmic-computer-use" / "remote-desktop.token"; cos.parent.mkdir()
old_is_new = old == new
assert portal.load_token() is None
cos.write_text("cosmic"); assert portal.load_token() == "cosmic"
old.write_text("old"); assert portal.load_token() == "old"
new.write_text("new"); assert portal.load_token() == "new"
if not old_is_new:  # outside an app scope both names are the same file
    new.write_text("  \n"); assert portal.load_token() == "old"   # an empty file falls through
new.write_text("new"); print("ok lookup order")
with contextlib.redirect_stdout(io.StringIO()): portal.forget_token()
assert not new.exists() and not old.exists() and not cos.exists(); print("ok forget removes all")
sc = portal.ScreenCast.__new__(portal.ScreenCast); sc.TOKEN.write_text("x"); sc.forget(); assert not sc.TOKEN.exists(); print("ok screencast forget")
class P(portal._Portal):
    def __init__(self): self.sender, self._n, self.bus = "s", 0, types.SimpleNamespace(signal_subscribe=lambda *a: 1, signal_unsubscribe=lambda *a: None)
    def _call(self, *a): return (), None
def run(**kw):
    e = io.StringIO()
    with contextlib.redirect_stderr(e): r = P()._request("Start", lambda o: None, 0.5, missing="timed-out", **kw)
    return r, e.getvalue()
assert run(notice=(0.1, "ASK")) == ("timed-out", "ASK\n"); print("ok notice once when slow")
assert run(notice=(5, "ASK")) == ("timed-out", ""); print("ok no notice before its time")
assert run() == ("timed-out", ""); print("ok no notice by default")
