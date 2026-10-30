"""A minimal Wayland client in pure Python (stdlib only), driven by the protocol XMLs in
protocols/. Enough for the COSMIC backend: outputs, toplevels, workspaces,
wl_shm buffers and ext-image-copy-capture. No pywayland, no libwayland-client.

    c = Client()                        # connects, reads the registry
    out = c.bind("wl_output", 4)        # -> Proxy
    out.on("name", lambda name: ...)    # event handler (args in XML order)
    c.roundtrip()                       # flush requests, dispatch until the server caught up
    out.release()                       # requests are methods; new_id args are returned

Wire format: little-endian 32-bit words. Header = object id, then (size << 16 | opcode).
Strings are length-prefixed (including NUL) and padded to 4 bytes; fds travel as
SCM_RIGHTS ancillary data in the same sendmsg/recvmsg.
"""
import array
import os
import select
import socket
import struct
import time
import xml.etree.ElementTree as ET
from pathlib import Path

PROTO_DIR = Path(__file__).resolve().parent / "protocols"


class WaylandError(Exception):
    pass


class Message:
    def __init__(self, name, args, since, destructor=False):
        self.name, self.args, self.since, self.destructor = name, args, since, destructor
        # args: [(name, type, interface, nullable)]


class Interface:
    def __init__(self, name, version):
        self.name, self.version, self.requests, self.events, self.enums = name, version, [], [], {}


def load_protocols(directory=PROTO_DIR):
    ifaces = {}
    for f in sorted(directory.glob("*.xml")):
        for el in ET.parse(f).getroot().iter("interface"):
            it = Interface(el.get("name"), int(el.get("version")))
            for kind, dest in (("request", it.requests), ("event", it.events)):
                for m in el.findall(kind):
                    args = [(a.get("name"), a.get("type"), a.get("interface"), a.get("allow-null") == "true")
                            for a in m.findall("arg")]
                    dest.append(Message(m.get("name"), args, int(m.get("since", "1")), m.get("type") == "destructor"))
            for e in el.findall("enum"):
                it.enums[e.get("name")] = {x.get("name"): int(x.get("value"), 0) for x in e.findall("entry")}
            ifaces[it.name] = it
    return ifaces


INTERFACES = load_protocols()


def _pad(n):
    return (n + 3) & ~3


class Proxy:
    def __init__(self, client, oid, iface, version):
        self._c, self.id, self.iface, self.version = client, oid, iface, version
        self._handlers = {}
        self.data = {}  # free space for callers
        self.alive = True

    def on(self, event, fn):
        self._handlers[event] = fn
        return self

    def __getattr__(self, name):
        for op, m in enumerate(self.iface.requests):
            if m.name == name:
                return lambda *a, **kw: self._c._request(self, op, m, a, kw)
        raise AttributeError(f"{self.iface.name} has no request {name}")

    def __repr__(self):
        return f"<{self.iface.name}@{self.id}>"


class Client:
    def __init__(self, display=None):
        name = display or os.environ.get("WAYLAND_DISPLAY", "wayland-0")
        path = name if name.startswith("/") else os.path.join(os.environ["XDG_RUNTIME_DIR"], name)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.objects, self._next, self._out, self._out_fds = {}, 2, bytearray(), []
        self._in, self._in_fds = bytearray(), []
        self.display = Proxy(self, 1, INTERFACES["wl_display"], 1)
        self.objects[1] = self.display
        self.display.on("error", self._on_error).on("delete_id", self._on_delete)
        self.globals = {}  # name -> (interface, version)
        self.registry = self.display.get_registry()
        self.registry.on("global", lambda n, i, v: self.globals.__setitem__(n, (i, v)))
        self.registry.on("global_remove", lambda n: self.globals.pop(n, None))
        self.roundtrip()

    # --- registry -----------------------------------------------------------------
    def has(self, interface):
        return any(i == interface for i, _ in self.globals.values())

    def bind(self, interface, version=None, index=0):
        """Bind the index-th global of `interface` at min(version, advertised)."""
        found = [(n, v) for n, (i, v) in sorted(self.globals.items()) if i == interface]
        if len(found) <= index:
            raise WaylandError(f"the compositor does not offer {interface}")
        name, adv = found[index]
        ver = min(version or INTERFACES[interface].version, adv, INTERFACES[interface].version)
        return self.registry.bind(name, (interface, ver))

    def bind_all(self, interface, version=None):
        return [self.bind(interface, version, i) for i in range(sum(i == interface for i, _ in self.globals.values()))]

    # --- outgoing -----------------------------------------------------------------
    def _new(self, iface_name, version):
        oid = self._next
        self._next += 1
        p = Proxy(self, oid, INTERFACES[iface_name], version)
        self.objects[oid] = p
        return p

    def _request(self, proxy, opcode, msg, args, kw):
        if not proxy.alive:
            raise WaylandError(f"{proxy} is gone")
        body, created, args = bytearray(), None, list(args)
        for name, typ, iface, nullable in msg.args:
            if typ == "new_id":
                if iface:
                    created = self._new(iface, proxy.version)
                    body += struct.pack("<I", created.id)
                else:  # wl_registry.bind: untyped new_id = (interface string, version, id)
                    iname, ver = args.pop(0)
                    created = self._new(iname, ver)
                    body += self._string(iname) + struct.pack("<II", ver, created.id)
                continue
            v = kw[name] if name in kw else args.pop(0)
            if typ == "int":
                body += struct.pack("<i", int(v))
            elif typ == "uint":
                body += struct.pack("<I", int(v))
            elif typ == "fixed":
                body += struct.pack("<i", int(round(v * 256)))
            elif typ == "string":
                body += self._string(v)
            elif typ == "object":
                body += struct.pack("<I", v.id if v is not None else 0)
            elif typ == "array":
                b = bytes(v)
                body += struct.pack("<I", len(b)) + b + b"\0" * (_pad(len(b)) - len(b))
            elif typ == "fd":
                self._out_fds.append(int(v))
        self._out += struct.pack("<II", proxy.id, ((8 + len(body)) << 16) | opcode) + body
        if msg.destructor:
            proxy.alive = False
        return created

    @staticmethod
    def _string(s):
        if s is None:
            return struct.pack("<I", 0)
        b = s.encode() + b"\0"
        return struct.pack("<I", len(b)) + b + b"\0" * (_pad(len(b)) - len(b))

    def flush(self):
        while self._out:
            anc = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", self._out_fds))] if self._out_fds else []
            n = self.sock.sendmsg([bytes(self._out)], anc)
            self._out_fds = []
            del self._out[:n]

    # --- incoming -----------------------------------------------------------------
    def _read(self, timeout):
        r, _, _ = select.select([self.sock], [], [], timeout)
        if not r:
            return False
        fds = array.array("i")
        data, anc, _, _ = self.sock.recvmsg(65536, socket.CMSG_LEN(28 * fds.itemsize))
        if not data:
            raise WaylandError("the compositor closed the connection")
        for level, typ, cdata in anc:
            if level == socket.SOL_SOCKET and typ == socket.SCM_RIGHTS:
                fds.frombytes(cdata[:len(cdata) - (len(cdata) % fds.itemsize)])
        self._in += data
        self._in_fds += list(fds)
        return True

    def _dispatch_buffered(self):
        n = 0
        while len(self._in) >= 8:
            oid, word = struct.unpack_from("<II", self._in)
            size, opcode = word >> 16, word & 0xFFFF
            if len(self._in) < size:
                break
            body = bytes(self._in[8:size])
            del self._in[:size]
            self._dispatch(oid, opcode, body)
            n += 1
        return n

    def _dispatch(self, oid, opcode, body):
        proxy = self.objects.get(oid)
        if proxy is None:
            return  # event for an object we already destroyed
        msg = proxy.iface.events[opcode]
        vals, off = [], 0
        for name, typ, iface, nullable in msg.args:
            if typ in ("int", "fixed"):
                (v,) = struct.unpack_from("<i", body, off)
                off += 4
                vals.append(v / 256 if typ == "fixed" else v)
            elif typ == "uint":
                vals.append(struct.unpack_from("<I", body, off)[0])
                off += 4
            elif typ == "string":
                (ln,) = struct.unpack_from("<I", body, off)
                off += 4
                vals.append(body[off:off + ln - 1].decode(errors="replace") if ln else None)
                off += _pad(ln)
            elif typ == "array":
                (ln,) = struct.unpack_from("<I", body, off)
                off += 4
                vals.append(body[off:off + ln])
                off += _pad(ln)
            elif typ == "object":
                (i,) = struct.unpack_from("<I", body, off)
                off += 4
                vals.append(self.objects.get(i) if i else None)
            elif typ == "new_id":
                (i,) = struct.unpack_from("<I", body, off)
                off += 4
                p = Proxy(self, i, INTERFACES[iface], proxy.version)
                self.objects[i] = p
                vals.append(p)
            elif typ == "fd":
                vals.append(self._in_fds.pop(0))
        fn = proxy._handlers.get(msg.name)
        if fn:
            fn(*vals)

    def _on_error(self, obj, code, message):
        raise WaylandError(f"protocol error on {obj}: {code} {message}")

    def _on_delete(self, oid):
        p = self.objects.pop(oid, None)
        if p:
            p.alive = False

    def dispatch(self, timeout=0.0):
        """Flush, then read and dispatch whatever arrives within `timeout` seconds."""
        self.flush()
        n = self._dispatch_buffered()
        if self._read(timeout):
            n += self._dispatch_buffered()
        return n

    def roundtrip(self, timeout=5.0):
        done = []
        self.display.sync().on("done", lambda _: done.append(1))
        end = time.monotonic() + timeout
        while not done:
            left = end - time.monotonic()
            if left <= 0:
                raise WaylandError("roundtrip timed out")
            self.dispatch(left)

    def wait(self, cond, timeout):
        """Dispatch until cond() is true; -> its value, or None on timeout."""
        end = time.monotonic() + timeout
        while not (v := cond()):
            left = end - time.monotonic()
            if left <= 0:
                return None
            self.dispatch(min(left, 0.05))
        return v

    def close(self):
        try:
            self.flush()
        finally:
            self.sock.close()
