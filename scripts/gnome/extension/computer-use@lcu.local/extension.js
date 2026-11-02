// D-Bus bridge for gnome-computer-use: what KWin scripting gives on KDE, GNOME Shell only
// gives from inside the shell (Introspect.GetWindows, Shell.Screenshot and Eval refuse
// outside callers). Exported on the shell's own connection:
//   bus name org.gnome.Shell, object /org/lcu/ComputerUse, interface org.lcu.ComputerUse
// Windows(request JSON) -> result JSON; Screenshot(path, pointer) -> result JSON (whole
// desktop at the largest monitor scale); ScreenshotArea(path, x, y, w, h, scale, pointer) -> result
// JSON (one logical area rendered at the given scale, e.g. its monitor's own, so it is not
// resampled).
// Input and screen recording do not go through here: Mutter's RemoteDesktop/ScreenCast
// D-Bus APIs already allow them without a dialog.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Mtk from 'gi://Mtk';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

Gio._promisify(Shell.Screenshot.prototype, 'screenshot', 'screenshot_finish');
Gio._promisify(Shell.Screenshot, 'composite_to_stream', 'composite_to_stream_finish');

const VERSION = 3;
const IFACE = `<node><interface name="org.lcu.ComputerUse">
  <method name="Windows"><arg type="s" direction="in" name="request"/><arg type="s" direction="out" name="result"/></method>
  <method name="Screenshot"><arg type="s" direction="in" name="path"/><arg type="b" direction="in" name="pointer"/>
    <arg type="s" direction="out" name="result"/></method>
  <method name="ScreenshotArea"><arg type="s" direction="in" name="path"/>
    <arg type="i" direction="in" name="x"/><arg type="i" direction="in" name="y"/>
    <arg type="i" direction="in" name="width"/><arg type="i" direction="in" name="height"/>
    <arg type="d" direction="in" name="scale"/><arg type="b" direction="in" name="pointer"/>
    <arg type="s" direction="out" name="result"/></method>
  <property name="Version" type="u" access="read"/>
  <property name="Path" type="s" access="read"/>
</interface></node>`;

const rect = r => ({x: r.x, y: r.y, width: r.width, height: r.height});
const BOTH = Meta.MaximizeFlags?.BOTH ?? 3;

function appId(w) {
    const app = Shell.WindowTracker.get_default().get_window_app(w);
    return app?.get_id()?.replace(/\.desktop$/, '') ?? '';
}

function isMaximized(w) {
    return w.is_maximized ? w.is_maximized() : w.get_maximized() === BOTH;
}

function maximize(w, on) {
    // Mutter 49 dropped the flags argument of maximize()/unmaximize()
    if (on)
        w.set_maximize_flags ? w.set_maximize_flags(BOTH) : w.maximize(BOTH);
    else
        w.set_unmaximize_flags ? w.set_unmaximize_flags(BOTH) : w.unmaximize(BOTH);
}

function info(w) {
    const f = w.get_frame_rect(), b = w.get_buffer_rect(), m = w.get_monitor();
    return {
        id: String(w.get_id()), class: w.get_wm_class() ?? '', app_id: w.get_gtk_application_id() ?? '',
        sandboxed_app_id: w.get_sandboxed_app_id() ?? '', desktop_app: appId(w),
        title: w.get_title() ?? '', pid: w.get_pid(), x: f.x, y: f.y, width: f.width, height: f.height,
        buffer: rect(b), monitor: m >= 0 ? rect(global.display.get_monitor_geometry(m)) : null,
        active: w === global.display.focus_window, minimized: w.minimized, maximized: isMaximized(w),
        fullscreen: w.is_fullscreen(), keepAbove: w.is_above(),
        normal: w.get_window_type() === Meta.WindowType.NORMAL && !w.is_skip_taskbar(),
        workspace: w.get_workspace()?.index() ?? -1, client_type: w.get_client_type() === Meta.WindowClientType.X11 ? 'x11' : 'wayland',
    };
}

function matches(w, match) {
    const i = match.indexOf(':');
    const k = match.slice(0, i), v = match.slice(i + 1).toLowerCase();
    const lc = s => (s ?? '').toLowerCase();
    if (k === 'id')
        return String(w.get_id()) === v;
    if (k === 'class')
        return [w.get_wm_class(), w.get_wm_class_instance(), w.get_gtk_application_id(),
            w.get_sandboxed_app_id(), appId(w)].some(s => s && lc(s).startsWith(v));
    if (k === 'title')
        return lc(w.get_title()).includes(v);
    if (k === 'pid')
        return String(w.get_pid()) === v;
    return false;
}

function allWindows(all) {
    const wins = global.get_window_actors().map(a => a.meta_window)
        .filter(w => all || (w.get_window_type() === Meta.WindowType.NORMAL && !w.is_skip_taskbar()) ||
            w.get_window_type() === Meta.WindowType.DIALOG || w.get_window_type() === Meta.WindowType.MODAL_DIALOG);
    // sort_windows_by_stacking returns bottom..top; topmost first like the KDE backend
    return global.display.sort_windows_by_stacking(wins).reverse();
}

function monitorIndex(g) {
    for (let i = 0; i < global.display.get_n_monitors(); i++) {
        const m = global.display.get_monitor_geometry(i);
        if (m.x === g.x && m.y === g.y && m.width === g.width && m.height === g.height)
            return i;
    }
    return -1;
}

function act(w, action, args) {
    const now = global.get_current_time();
    switch (action) {
    case 'activate': Main.activateWindow(w, now); break;
    case 'raise': w.raise(); break;
    case 'minimize': w.minimize(); break;
    case 'unminimize': w.unminimize(); break;
    case 'maximize': maximize(w, true); break;
    case 'unmaximize': maximize(w, false); break;
    case 'fullscreen': w.make_fullscreen(); break;
    case 'unfullscreen': w.unmake_fullscreen(); break;
    case 'keep-above': w.make_above(); break;
    case 'no-keep-above': w.unmake_above(); break;
    case 'close': w.delete(now); break;
    case 'move-to': {   // args[0] = target monitor geometry {x,y,width,height} (resolved by the caller)
        const idx = monitorIndex(args[0]);
        if (idx < 0)
            return 'no monitor with geometry ' + JSON.stringify(args[0]);
        if (isMaximized(w))
            maximize(w, false);
        w.move_to_monitor(idx);
        const a = args[0], f = w.get_frame_rect();
        const width = Math.min(f.width, a.width), height = Math.min(f.height, a.height);
        w.move_resize_frame(true, a.x + Math.round((a.width - width) / 2), a.y + Math.round((a.height - height) / 2), width, height);
        break;
    }
    case 'geometry':
        if (w.is_fullscreen())
            w.unmake_fullscreen();
        if (isMaximized(w))
            maximize(w, false);
        w.move_resize_frame(true, +args[0], +args[1], +args[2], +args[3]);
        break;
    case 'info': break;
    default: return 'unknown action ' + action;
    }
    return null;
}

class Bridge {
    constructor(path) {
        this._path = path;
    }

    get Version() {
        return VERSION;
    }

    get Path() {   // where the running code was loaded from (load-extension-live.py checks it)
        return this._path;
    }

    Windows(request) {
        const out = {ok: true, windows: []};
        try {
            const {action, match = '', args = [], first = false, all = false} = JSON.parse(request);
            const wins = allWindows(all);
            if (action === 'list') {
                out.windows = wins.map(info);
            } else if (action === 'active') {
                const f = global.display.focus_window;
                out.windows = f ? [info(f)] : [];
            } else {
                let hit = wins.filter(w => matches(w, match));
                if (first)
                    hit = hit.slice(0, 1);
                if (!hit.length) {
                    out.ok = false;
                    out.error = 'no window matches ' + match;
                }
                for (const w of hit) {
                    const err = act(w, action, args);
                    if (err) {
                        out.ok = false;
                        out.error = err;
                    }
                }
                out.windows = hit.map(info);
            }
        } catch (e) {
            out.ok = false;
            out.error = String(e);
        }
        return JSON.stringify(out);
    }

    async ScreenshotAsync([path, pointer], invocation) {
        try {
            const stream = Gio.File.new_for_path(path).replace(null, false, Gio.FileCreateFlags.NONE, null);
            await new Shell.Screenshot().screenshot(pointer, stream);
            stream.close(null);
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify({ok: true, file: path})]));
        } catch (e) {
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify({ok: false, error: String(e)})]));
        }
    }

    async ScreenshotAreaAsync([path, x, y, width, height, scale, pointer], invocation) {
        try {
            const area = new Mtk.Rectangle({x, y, width, height});
            const texture = global.stage.paint_to_content(area, scale,
                pointer ? Clutter.PaintFlag.FORCE_CURSORS : Clutter.PaintFlag.NO_CURSORS).get_texture();
            const stream = Gio.File.new_for_path(path).replace(null, false, Gio.FileCreateFlags.NONE, null);
            await Shell.Screenshot.composite_to_stream(texture, 0, 0, -1, -1, scale, null, 0, 0, 1, stream);
            stream.close(null);
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify({ok: true, file: path})]));
        } catch (e) {
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify({ok: false, error: String(e)})]));
        }
    }
}

export default class ComputerUseBridge extends Extension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, new Bridge(this.path));
        this._dbus.export(Gio.DBus.session, '/org/lcu/ComputerUse');
    }

    disable() {
        this._dbus?.unexport();
        this._dbus = null;
    }
}
