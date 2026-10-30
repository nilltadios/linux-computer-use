"""xdg-desktop-portal clients (PyGObject only): RemoteDesktop for input, ScreenCast for video.

RemoteDesktop: cosmic-comp's own com.system76.CosmicComp.Ei.GetSenderSocket answers
only the portal and the on-screen keyboard (AccessDenied for anyone else), so input on
COSMIC goes through the portal. With persist_mode 2 the portal returns a restore token;
the next session that passes it is started without a dialog. Each Start returns a fresh
token, saved in ~/.local/state/linux-computer-use/.

ScreenCast: KDE's real-time recording (Spectacle cannot record from a script). The same
restore-token scheme; KDE's tokens are single-use, so the newest is always kept.
"""
import os
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

PORTAL = ("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
RD = "org.freedesktop.portal.RemoteDesktop"
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "linux-computer-use"
TOKEN = STATE / "remote-desktop.token"
# grants saved by the earlier per-desktop skills; read once, then saved under STATE
LEGACY = {TOKEN: STATE.parent / "cosmic-computer-use" / "remote-desktop.token",
          STATE / "screencast-monitors.token": STATE.parent / "claude-kde-capture" / "restore-token-monitors"}
KEYBOARD, POINTER = 1, 2
PERSIST_UNTIL_REVOKED = 2


def load_token(path=TOKEN):
    for p in (path, LEGACY.get(path)):
        try:
            if p and (tok := p.read_text().strip()):
                return tok
        except OSError:
            pass
    return None


def save_token(tok, path=TOKEN):
    STATE.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(tok)


def forget_token():
    TOKEN.unlink(missing_ok=True)
    if LEGACY[TOKEN].exists():
        LEGACY[TOKEN].unlink()
    print(f"removed {TOKEN}; the next input call shows the portal dialog again")


class _Portal:
    IFACE = RD

    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.sender = self.bus.get_unique_name()[1:].replace(".", "_")
        self.session = None
        self._n = 0

    def _call(self, method, args, rtype="(o)", fds=None):
        r, fdl = self.bus.call_with_unix_fd_list_sync(*PORTAL, self.IFACE, method, args, GLib.VariantType(rtype),
                                                      Gio.DBusCallFlags.NONE, 30000, fds, None)
        return r.unpack(), fdl

    def _request(self, method, build, timeout, missing=None):
        """Call a portal method that answers through a Request object; -> results dict."""
        self._n += 1
        token = f"lcu{os.getpid()}_{self._n}"
        path = f"/org/freedesktop/portal/desktop/request/{self.sender}/{token}"
        got = []
        sub = self.bus.signal_subscribe(PORTAL[0], "org.freedesktop.portal.Request", "Response", path, None,
                                        Gio.DBusSignalFlags.NONE,
                                        lambda *a: got.append(a[5].unpack()))
        try:
            self._call(method, build({"handle_token": GLib.Variant("s", token)}))
            ctx, end = GLib.MainContext.default(), time.monotonic() + timeout
            while not got and time.monotonic() < end:
                ctx.iteration(False) or time.sleep(0.01)
        finally:
            self.bus.signal_unsubscribe(sub)
        if not got:
            if missing:
                return missing
            sys.exit(f"the portal did not answer {method} within {timeout:g} s"
                     + (" (nobody approved the Remote desktop dialog?)" if method == "Start" else ""))
        code, results = got[0]
        if code == 1:
            sys.exit(f"{method}: the request was cancelled (the dialog was denied or closed)")
        if code != 0:
            sys.exit(f"{method}: the portal failed (response {code})")
        return results

    def close(self):
        if self.session:
            try:
                self.bus.call_sync(PORTAL[0], self.session, "org.freedesktop.portal.Session", "Close", None, None,
                                   Gio.DBusCallFlags.NONE, 5000, None)
            except GLib.Error:
                pass
            self.session = None

    def _create_session(self):
        res = self._request("CreateSession", lambda o: GLib.Variant("(a{sv})", ({
            **o, "session_handle_token": GLib.Variant("s", f"lcu{os.getpid()}_{self._n}")},)), 10)
        self.session = res["session_handle"]


class RemoteDesktop(_Portal):
    def connect(self, interactive_timeout=120):
        """-> a raw fd of the EIS socket."""
        try:
            ver = self.bus.call_sync(*PORTAL, "org.freedesktop.DBus.Properties", "Get",
                                     GLib.Variant("(ss)", (RD, "version")), GLib.VariantType("(v)"),
                                     Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
        except GLib.Error as e:
            sys.exit(f"no RemoteDesktop portal: {e.message}")
        if ver < 2:
            sys.exit(f"RemoteDesktop portal version {ver} has no ConnectToEIS (need 2)")
        self._create_session()
        token = load_token()
        opts = {"types": GLib.Variant("u", KEYBOARD | POINTER),
                "persist_mode": GLib.Variant("u", PERSIST_UNTIL_REVOKED)}
        if token:
            opts["restore_token"] = GLib.Variant("s", token)
        self._request("SelectDevices", lambda o: GLib.Variant("(oa{sv})", (self.session, {**o, **opts})), 10)
        if not token:
            print("The desktop is asking for permission: allow the Remote desktop dialog on screen "
                  f"(waiting up to {interactive_timeout} s)", file=sys.stderr, flush=True)
        res = self._request("Start", lambda o: GLib.Variant("(osa{sv})", (self.session, "", o)),
                            interactive_timeout if not token else 15)
        if res.get("restore_token"):
            save_token(res["restore_token"])
        if not res.get("devices", 0) & POINTER or not res.get("devices", 0) & KEYBOARD:
            print(f"warning: the portal granted devices={res.get('devices')} (1 keyboard, 2 pointer)",
                  file=sys.stderr)
        (handle,), fdl = self._call("ConnectToEIS", GLib.Variant("(oa{sv})", (self.session, {})), "(h)",
                                    Gio.UnixFDList())
        return fdl.get(handle)


class ScreenCast(_Portal):
    """Monitor streams through the ScreenCast portal, restored from a saved grant."""
    IFACE = "org.freedesktop.portal.ScreenCast"
    TOKEN = STATE / "screencast-monitors.token"

    def start(self, interactive, pointer=False):
        """-> [(pipewire node, {position, size, ...})]. Without a saved grant and not
        interactive: exit 3 and show nothing."""
        token = load_token(self.TOKEN)
        if not token and not interactive:
            sys.exit(3)
        self._create_session()
        opts = {"types": GLib.Variant("u", 1), "multiple": GLib.Variant("b", True),
                "cursor_mode": GLib.Variant("u", 2 if pointer else 1), "persist_mode": GLib.Variant("u", 2)}
        if token and not interactive:
            opts["restore_token"] = GLib.Variant("s", token)
        self._request("SelectSources", lambda o: GLib.Variant("(oa{sv})", (self.session, {**o, **opts})), 30)
        # A valid grant answers at once; a dialog means the grant is missing or no longer matches.
        res = self._request("Start", lambda o: GLib.Variant("(osa{sv})", (self.session, "", o)),
                            600 if interactive else 8, missing="timeout")
        if res == "timeout":
            self.close()
            sys.exit("the saved screen-share grant was not accepted silently (the desktop showed a dialog); "
                     "dismiss it and run `lcu capture record-setup` once with the person present")
        if res.get("restore_token"):
            save_token(res["restore_token"], self.TOKEN)
        return [(node, dict(props)) for node, props in res.get("streams", [])]

    def pipewire_fd(self):
        (handle,), fdl = self._call("OpenPipeWireRemote", GLib.Variant("(oa{sv})", (self.session, {})), "(h)",
                                    Gio.UnixFDList())
        return fdl.get(handle)

    def forget(self):
        self.TOKEN.unlink(missing_ok=True)
        LEGACY[self.TOKEN].unlink(missing_ok=True)
