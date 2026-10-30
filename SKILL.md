---
name: linux-computer-use
description: Control this user's Linux Wayland desktop (KDE Plasma 6, GNOME or COSMIC, detected automatically) - move the mouse, left/right/middle/double click, scroll, click-and-drag and drag-and-drop, shift-click and ctrl-click, type, paste any text and press key combos, take screenshots of the whole desktop, one monitor, an area or one app's window, record the screen/an area/one window, find buttons by name (accessibility) or by text (OCR), and open, focus, minimize, maximize, fullscreen, move or close apps. Use it for "computer use" on this Linux machine, for driving a native desktop app (Dolphin, Okular, System Settings, Files/Nautilus, COSMIC Files, any Qt/GTK/Electron/Flatpak app), or when the user asks to click, type, screenshot or record something on their screen. Websites go through the Chrome or built-in-browser skills instead (see "Pick the right tool first").
---

# Computer use on Linux (KDE Plasma 6, GNOME, COSMIC)

Everything works as the desktop user: no root, no uinput, no ydotool, nothing from
pip. One command, `lcu`, detects the desktop and drives it through that
compositor's own interfaces; the commands, options and JSON are the same everywhere.
It is plain shell commands, so any agent that can run a shell (Claude Code, Codex,
Gemini CLI, Antigravity...) uses it the same way.

```bash
SKILL_DIR=<the folder that holds this SKILL.md>   # e.g. ~/.agents/skills/linux-computer-use
L=$SKILL_DIR/lcu
$L detect          # which desktop, why, and which backend each tool uses
$L check           # every requirement for this desktop; changes nothing; exit 0 = ok
```

| Tool | KDE Plasma 6 | GNOME | COSMIC |
|---|---|---|---|
| `input` | KWin EIS D-Bus (`connectToEIS`) | Mutter RemoteDesktop `ConnectToEIS` | RemoteDesktop portal (grant once) |
| `window` | temporary KWin script | bridge shell extension | `ext-foreign-toplevel` + `zcosmic-toplevel-*` |
| `capture shot` | Spectacle (`-a`/`-m` native, `-f` whole) | bridge extension | `ext-image-copy-capture` |
| `capture record` | ScreenCast portal (grant once) | Mutter ScreenCast | `ext-image-copy-capture` -> ffmpeg |
| `a11y`, `ocr` | AT-SPI, tesseract (shared) | same | same (COSMIC's own apps: OCR only) |
| one-time setup | `capture record-setup` for video | `setup` (extension, a11y switch) | `setup` (Remote desktop dialog) |

Checked on KDE: Fedora 44, KWin 6.7.5, libei 1.6.0, Spectacle 6.7.5 (2026-10-30, all
tests). GNOME (CentOS Stream 10, GNOME Shell 49.5, Mutter 49.4) and COSMIC (CachyOS,
cosmic-comp 1.10.0) were checked on 2026-10-29 with the earlier per-desktop skills
whose code this one carries; the merged `lcu` has not yet run on them (see Verifying).

Detection order: `lcu --desktop kde|gnome|cosmic` or `LCU_DESKTOP`, then
`XDG_CURRENT_DESKTOP` confirmed by the compositor's D-Bus name, then the D-Bus names
alone. X11 sessions and other compositors are not supported; `detect` says so.
Scripts run on `/usr/bin/python3 -s` (PyGObject from the distro); `lcu TOOL --help`
lists every option.

## Keep this skill current

This skill learns from use. Lessons from earlier sessions are in `LEARNINGS.md`
(shared with everyone who installs the skill) and `LEARNINGS.local.md` (this
machine only, git-ignored); you add to them, and fix this file, as you work.
Every entry is tagged `Desktop: kde|gnome|cosmic|all`.

**Before you start**, read what applies to the task:

```bash
$L learn list --app <window class or app name>   # lessons for the app you will drive
$L learn list --kind broken                      # advice below that is known not to work
```

`list` shows this desktop's entries plus the `all` ones (`--desktop any`: every entry).

**Record a lesson** when something here would have saved this session time,
or would save the next one time:
- a command or rule below failed, behaved differently, or no longer works (`broken`);
- you found a more reliable or faster way than the one given here (`better`);
- you found a capability or trick that is not written down yet (`new`);
- an app has a quirk an agent must know to drive it, such as where a control
  lives, which keys it ignores, or what a dialog means (`app`).

Rules:
1. **Only verified lessons.** Record what you saw work or fail, with the command
   and the observation as Evidence. A guess, or one unexplained flake, is not a lesson.
2. **Generic, not this task.** Write it so it helps any later task: name the
   app, control and condition, not the user's files or what they asked for.
3. **Tag the desktop honestly.** `add` stamps the detected desktop. Use
   `--desktop all` only for what does not depend on the compositor (an Electron,
   Flatpak, website or toolkit quirk, or the shared `input`/`a11y`/`ocr`/`learn`
   scripts). A lesson seen on one desktop that probably holds on the others is
   still tagged with the one you saw; say "likely elsewhere too" in What.
4. **The repo may be public.** No home paths, names, accounts, emails, tokens,
   links to the user's content, or anything read from their windows. `check`
   rejects the common leaks; you catch the rest.
   **Shared or local?** A lesson goes in the shared LEARNINGS.md only if most
   users of the skill could hit it: the desktops, the skill's own scripts, and
   common apps or toolkits (Qt, GTK, libadwaita, Electron, Firefox, Dolphin,
   Nautilus, COSMIC Files...). Lessons about apps or setups few users have go in
   LEARNINGS.local.md with `add --local`.
5. **Fix SKILL.md itself when it is plainly wrong or out of date.** Correct the
   text in place, keep "Checked on"/test dates true, and add a `broken` or
   `better` entry pointing to the change with Status `promoted`. Use LEARNINGS.md
   alone for app quirks and for lessons seen only once.
6. **One lesson per entry, no duplicates.** If an entry already covers it,
   edit that entry (add evidence, correct it) instead of adding another.
   Never delete an entry: set Status to `superseded` or `wrong` and say why.
7. **Promote what keeps coming up.** When an active entry has proved itself
   again (or is about this skill's own scripts), move it into the right section
   below and set its Status to `promoted`.
8. **Script bugs get fixed, not just noted**, when the fix is small and you can
   test it (`tests/`). A fix to a desktop backend you cannot test here gets a
   `broken` entry for that desktop instead. GNOME extension changes need
   `$L setup` and then `scripts/gnome/load-extension-live.py --force`.

```bash
$L learn add --kind better --title "One-line lesson" \
  --what "what happened" --do "what to do instead" --evidence "command -> observation"
$L learn add --kind app --app org.kde.dolphin --title "..." --what "..." --do "..." --evidence "..."
$L learn add --desktop all --kind app --app codium --title "..." ...   # not desktop-specific
$L learn add --local --kind app --app SomeNicheApp --title "..." ...   # this machine only
$L learn check        # must exit 0; also lists this desktop's entries recorded on an older stack
```

**Before you finish the task**: run `$L learn check`, then commit the skill
change locally (`git -C "$SKILL_DIR" add -A && git -C "$SKILL_DIR" commit -m "learn: <lesson>"`)
so it can be reviewed and reverted. **Never push**; pushing needs the user's
explicit yes after they have seen the diff. In your final message, tell the
user in one line what you recorded or changed in the skill, or that nothing new came up.

When `check` lists entries to re-verify (the desktop was updated since they were
recorded), test the ones that matter for your task and update their Seen on
line or Status.

## Pick the right tool first

1. A dedicated MCP/connector for the app (Gmail, Calendar, Drive...) if connected.
2. Web pages: your agent's browser tool, never pixel clicks (a browser
   extension or built-in browser, a browser MCP server such as Playwright or
   Chrome DevTools, or the agent's browser sub-agent). They are DOM-aware and much
   more reliable; follow that tool's own instructions.
3. A CLI, D-Bus or config route for the app if one exists: `xdg-open`, `gio open`,
   `gsettings`, `gdbus`; KDE `kwriteconfig6`, `qdbus-qt6`, `dolphin --select`,
   `okular --page`; GNOME `nautilus --select`; COSMIC `cosmic-randr`,
   `~/.config/cosmic/<component>/v1/<key>` files.
4. This skill, for native GUI apps and cross-app work.

If your agent has its own desktop computer-use tools that work in this Linux
session, prefer them; most target macOS/Windows only.

## Safety rules (learned the hard way)

During development a test sent clicks to the centre of a monitor believing a test
window was there; it was not, and the clicks landed in the file manager and opened
one of the user's documents. Later a click meant for a test dialog landed in the
agent's own chat app because the dialog was not where an earlier listing said. So:

- **Never click or type blind.** Before every click, make sure the intended window
  is the one under the pointer: `$L window info MATCH` for its geometry and
  `$L window active` for focus, then a screenshot of that spot to see the control.
  After an action that changes the UI, take a new screenshot before the next click.
  Coordinates from an old screenshot or listing are stale.
- **Keys go to the focused window, not the one under the pointer**, and hovering
  does not move focus. Run `$L window activate MATCH` right before `key`/`type`/
  `paste` and confirm with `$L window active`. If the user's chat or terminal keeps
  focus, your keystrokes land there (and Enter may send them).
- **COSMIC: `active` can list two windows** (one per monitor). Only the one
  activated last receives keys, and the protocol does not say which, so `activate`
  the target immediately before typing instead of trusting `active`.
- **Shell UI is not a window.** GNOME's Alt+F2, Activities search and system
  dialogs open on the monitor under the pointer: confirm them with
  `$L a11y find gnome-shell --name ... --exact --depth 40`. COSMIC's launcher, app
  library, panel and notifications are invisible to `window list` and to
  accessibility: confirm them with a screenshot of each monitor. KDE's panels and
  popups appear only with `window list --all`.
- **Never use OCR alone to confirm a dialog opened**; the same words may be in
  another window (a chat quoting them). Use `window active`/`info` or the
  accessibility tree.
- A right-click opens a menu at the pointer; the next click at the same spot
  picks the top menu item. Close menus with `key escape`.
- Do not close, quit or kill apps the user has open, and do not act inside their
  private apps beyond the task. `window close` only for windows you opened or with
  permission.
- Your agent's own safety and ask-first rules still apply to anything done
  through the GUI (purchases, sending messages, passwords, deleting).
- Full-desktop screenshots contain private windows; look only at what the task
  needs and prefer `--window`/`--area` crops.
- `paste` replaces the clipboard for a moment and then restores it; say so in your
  report. Do not use bare `wl-copy` for this.
- GNOME shows its screen-sharing/remote-desktop indicator while input or a
  ScreenCast runs; that is expected. COSMIC delivers no capture frames while the
  screen is locked (`shot` and `record` fail after 5 s): never try to unlock it.

## Coordinates

All coordinates are the compositor's **logical** pixels: the space `$L capture
screens` prints and `$L window` returns, and the space `input` takes. Check the
layout per task; it changes. Example from this machine (KDE, 2026-10-30): `eDP-1`
0,0 1536x960 (scale 1.25, left), `DP-1` 1536,160 1600x900 (scale 1.6, right).

Every `shot` prints `logical_region` and `pixels_per_logical`. To click something
you see in a screenshot:

```
logical_x = region_x + image_x / pixels_per_logical      (same for y)
```

How sharp a shot is depends on the desktop and the target (all three: prefer
`--window`/`--screen`/`--area` over whole-desktop shots for anything you must read;
they are also smaller, so cheaper to look at):

- **KDE:** `--window` raises the window and grabs it with Spectacle's
  active-window mode: the window's own pixels at its monitor's scale, nothing that
  covers it. `--screen`, or an `--area` inside one monitor, is native when that
  monitor is KWin's **active output** (the one holding the focused window, not the
  pointer; `screens` marks it `"active"`); otherwise it is cut from the whole
  desktop, which Spectacle renders at one uniform scale (2.0 here) so lower-scale
  monitors come out upscaled and soft. `source` in the JSON says which was used.
- **GNOME:** a region inside one monitor is rendered at that monitor's own scale;
  the whole desktop at the largest scale (soft on the others).
- **COSMIC:** a region inside one monitor is cut from that monitor's native
  capture; `--window --own` gives the window's own surface at 1 px per logical px.

`$L input --list-regions` prints the absolute-pointer regions (one per monitor); a
point outside every region is ignored.

## Mouse and keyboard: `lcu input`

COSMIC only: the first call (or `$L setup`) shows COSMIC's **Remote desktop**
dialog, which the user must allow (the script waits up to 120 s); later calls reuse
the saved grant silently. Ask the user before triggering it. KDE and GNOME need no grant.

Actions run in order over one EIS connection:

```bash
$L input move 2336 610                         # absolute, logical px
$L input rmove 40 -10                          # relative
$L input move 2336 610 click left              # left click (default button)
$L input click right                           # at current position
$L input click middle
$L input click left 2                          # double click (3 = triple)
$L input down left move 900 500 up left        # manual press/hold/release
$L input drag 2100 400 2500 700                # drag-and-drop: press, nudge, glide, hover, release
$L input drag 2100 400 2500 700 right          # drag with another button
$L input scroll 3      ; $L input scroll -3    # wheel detents down / up
$L input hscroll 2     ; $L input hscroll -2   # right / left
$L input keydown shift click left keyup shift                      # shift-click
$L input keydown ctrl move 2200 500 click left move 2300 500 click left keyup ctrl   # ctrl-click several
$L input move 2100 400 click left keydown shift move 2300 600 click left keyup shift # range select
$L input key ctrl+c ; $L input key ctrl+shift+t ; $L input key alt+f4 ; $L input key super
$L input type "Hello, world!"                  # US keymap only
$L input paste "Grüße, 你好 ✓"                  # any text: clipboard + ctrl+v, clipboard restored
$L input paste-term "text"                     # same with ctrl+shift+v (terminals)
$L input sleep 300                             # ms, between actions
```

- Keys: letters, digits, `f1`..`f12`, `enter`, `esc`, `tab`, `space`,
  `backspace`, `delete`, `home`, `end`, `pageup`, `pagedown`, arrows (`up`...),
  `ctrl`, `shift`, `alt`, `altgr`, `super`/`meta`, `menu`, `print`, or a raw
  evdev keycode number. `--help-keys` lists them.
- `type` sends evdev keycodes, which the compositor maps through the user's
  current keymap; the table assumes a US layout. For anything else (accents, CJK,
  emoji, long text) use `paste`: it saves the clipboard, pastes, and puts the
  user's clipboard back (stderr says what it restored).
- The EIS connection exists only while the script runs; held keys are released
  when it exits, so put `keydown`...`keyup` sequences in one call.
- `drag` works for drag-and-drop between apps, also across monitors (COSMIC
  Files to a Flatpak app 9/10; Nautilus to a GTK4 app). It makes small first moves
  while still on the item (a large first jump cancels the DnD) and hovers over the
  target before releasing. Build a drag by hand only when you must, with the same
  shape: `down left sleep 200 rmove 3 2 rmove 8 4 ...steps... sleep 300 up left`.
- Desktop shortcuts differ: GNOME `super+left/right` half-tiles the focused window
  (and accounts for panels); COSMIC's shortcuts are in Settings > Keyboard >
  Keyboard shortcuts and `~/.config/cosmic/com.system76.CosmicSettings.Shortcuts/`;
  KDE's in System Settings > Shortcuts. Check before assuming another desktop's.
- Web-drawn sliders in Electron apps may ignore arrow keys: click the stop next to
  the handle and confirm the value with a crop.

## Windows and apps: `lcu window`

```bash
$L window list                       # topmost first (COSMIC: active first): id, class, title, pid, x/y/width/height, output, active, minimized, maximized, fullscreen ...
$L window active                     # focused window (COSMIC: possibly two)
$L window activate class:org.kde.dolphin   # raise + focus (unminimizes)
$L window minimize title:"Okular"    ; $L window unminimize class:org.kde.okular
$L window maximize class:librewolf   ; $L window unmaximize class:librewolf
$L window fullscreen class:org.gnome.Loupe ; $L window unfullscreen class:org.gnome.Loupe
$L window move-to class:org.kde.dolphin DP-1
$L window wait-stable title:"Save"   # wait until a new window has stopped moving
$L window close id:...               # like the title-bar X; only with permission
```

MATCH is `id:ID` (from `list`), `class:PREFIX` (Wayland app id / desktop file /
WM_CLASS, case-insensitive; COSMIC also matches the last dot component),
`title:SUBSTRING` or `pid:N` (not COSMIC: it reports no pids). An action applies to
every match; add `--first` for one. `--all` (KDE, GNOME) adds panels, popups and
other non-normal windows. Changes are applied asynchronously: wait ~0.3 s before a
screenshot.

KDE also provides `window at X Y`, KWin's input hit test including decoration
resize borders, and `window drag-resize MATCH W H [--edge EDGE] [--step PX]`.
`EDGE` is left, right, top, bottom, or a corner such as bottom-right. The default
chooses edges that fit the usable area; `--left` / `--top` choose the other sides.
The command requires exactly one window and refuses minimized, maximized or
fullscreen windows. It raises the target unless `--no-raise` is supplied, checks
KWin's actual hit target before a press, approaches from inside, and uses steps
of at most 8 px. It releases the button and restores the pointer at the end.
Exit 0 means the target size was reached (within 1 logical pixel); exit 3 means
a size limit, size increments or desktop snapping prevented it. Inspect `to`,
`target`, `note` and `window` in the JSON. Other failures exit 1.
`window info` includes `area` (usable screen rectangle), `screen`, `buffer`,
`min_size` (client size), `decorated`, `resizing` and `moving` on KDE.
`window geometry` assigns frame dimensions directly and can bypass an app's
minimum size; use pointer resizing to test the size a person can reach.

What each desktop can do beyond that:

| | KDE | GNOME | COSMIC |
|---|---|---|---|
| `geometry X Y W H`, `keep-above`/`no-keep-above`, `raise` (no focus) | yes | yes | no protocol: exits with a reason; use maximize, `move-to`, tiling keys or drag the header |
| `sticky`/`unsticky` (all workspaces), `workspaces` | - | - | yes |
| `pointer` (pointer position, KWin's active output) | yes | - | - |
| window `x/y/width/height` | frame; `client` = inside | visible frame, no CSD shadow (`buffer` has it) | visible geometry |

Opening apps: new windows open where the compositor decides (GNOME: the monitor
under the pointer; KDE and COSMIC: by their placement settings) and apps do not
reliably come back maximized, so prefer `launch`, which waits for the new window,
moves it and sets its state:

```bash
$L window launch --on DP-1 --maximize -- dolphin ~/Pictures     # prints the new window
$L window launch --on eDP-1 --fullscreen --match class:codium -- codium file.txt
$L window launch --on DP-1 -- gio open ~/Desktop/clip.webm      # Flatpak default handler
gtk-launch org.kde.dolphin              # by .desktop id (ls /usr/share/applications ~/.local/share/applications ~/.local/share/flatpak/exports/share/applications /var/lib/flatpak/exports/share/applications)
xdg-open /path/or/url                   # default handler
```

- `launch` compares window ids, so a single-instance app that opens a new window in
  an already running process is handled. On KDE, an existing window gaining focus
  is reported as reuse. With `--match`, a title change also detects reuse. An
  existing window is never returned as a new test window.
  On GNOME `--on` moves the pointer to that monitor first (no click).
- Without `launch`, start long-running GUI apps detached (`setsid -f ...` or
  your agent's background-process option) so they outlive the shell call, then
  `$L window wait-stable class:<id>`.
- Flatpak apps only see files passed through the document portal, and `/tmp` is
  private to their sandbox: open files with `gio open FILE`, not
  `flatpak run APP /path`, and keep test files out of `/tmp`.
- Closing: `$L window close` (graceful; the app may ask to save) or the app's own
  quit shortcut. Never `kill` a GUI app the user is using. For processes you
  started, use `pkill -x NAME` or `flatpak kill APPID`: `pkill -f PATTERN` matches
  the agent's own shell command line when it contains PATTERN and kills the call.

## Finding controls by name: `lcu a11y` (accessibility) and `lcu ocr` (OCR)

Prefer these to reading coordinates off a screenshot.

```bash
$L a11y apps                                         # pid and name of every accessible app
$L a11y tree <pid|name|class|title> --depth 12       # role: 'name' @centre WxH [states]
$L a11y press <app> --name Save --role button --exact   # default action, no mouse
$L a11y find <app> --name "New Folder"               # JSON: role, actions, box.center
$L ocr "Save as" --window class:org.kde.kate         # text on screen -> box.center
$L ocr --dump --window class:codium                  # every line OCR read, with boxes
```

Order of preference:
1. `$L a11y press`: activates buttons, menu items, check boxes by name. Nothing can
   be mis-clicked. Works for Qt, GTK3/4 and Electron.
2. Click coordinates: from `$L a11y find` (`box.center`) or `$L ocr`, depending on
   the toolkit:

   | Toolkit | a11y box | Use |
   |---|---|---|
   | Qt (KDE apps) | exact | a11y |
   | GTK 4.24+ | exact (COSMIC check) | a11y |
   | GTK 4.16 | ignores container margins, 10-30 px off | OCR |
   | GTK4 dialog on KDE, GTK 4.22 | exact (KDE test 2026-10-30) | a11y |
   | Electron/Chromium | 15+ px off | OCR |
   | COSMIC's own apps (libcosmic) | not on AT-SPI at all | OCR |

   Always check the chosen point with a crop screenshot before clicking.
3. `$L ocr` for everything else. It reads a greyscale and a colour copy (tesseract
   misses some light-on-dark or focus-ringed text in one of them), matches whole
   words, ignores stray icon glyphs, splits a line at wide gaps, and ranks text
   standing alone (a button, a menu entry: `alone: true`) before the same words
   inside a sentence.

- Accessibility must be on (`gsettings set org.gnome.desktop.interface
  toolkit-accessibility true`; GNOME's `$L setup` sets it). GTK4 apps register by
  themselves; GTK3, Qt and Electron apps started before it was on expose nothing
  until restarted. Never restart the user's apps for this; fall back to OCR.
- Electron apps (VS Code/VSCodium, Slack, the Claude or ChatGPT desktop apps...) need
  `--force-renderer-accessibility` for the tree inside the window. Add it only when
  you start such an app yourself and need the tree: it also switches VS
  Code/VSCodium into Screen Reader Optimized mode (mention it in your report).
- libadwaita apps nest controls deeply; `find`/`press` search 30 levels by
  default (`--depth 50` if nothing matches). `--name` must not be empty.
- Roles are AT-SPI names: `button`, `menu item`, `check box`, `text`,
  `combo box`, `frame`, `dialog`, `label`. Run `tree` first to see them.
- A new window is often resized and re-centred just after it appears, and KWin
  cascades new dialogs: `$L window wait-stable MATCH` before reading any
  position, and `activate` it before clicking.
- Window classes are often reverse-DNS (`org.kde.kdialog`); take them from
  `list`/`tree` output, not a guess.

## Screenshots: `lcu capture shot`

```bash
$L capture screens                                   # monitor layout, scale (KDE: active output, pointer)
$L capture shot out.png                              # whole desktop (soft on lower-scale monitors)
$L capture shot out.png --screen DP-1                # one monitor
$L capture shot out.png --area 1600 200 800 450      # logical X Y W H
$L capture shot out.png --window class:org.kde.dolphin   # raises it, grabs it, gives focus back
$L capture shot out.png --window title:Okular --no-raise # crop where it is (may include windows on top)
$L capture shot out.png --pointer                    # include the cursor
$L capture shot out.png --window MATCH --own         # COSMIC: the window's own surface, even if covered
$L capture shot out.png --screencast                 # GNOME: without the extension (no --window)
```

Prints JSON with the file, pixel size, logical region and `pixels_per_logical`.
Save into the session scratchpad or a task folder, never loose in the home folder.
Read the PNG to look at it; downscale very wide ones first
(`ffmpeg -i in.png -vf scale=1600:-1 out.png`). `grim` does not work on KWin or
Mutter (and before 1.5 not on COSMIC), `gnome-screenshot` is refused on GNOME
Wayland, and the screenshot portal asks the user; this script needs none of them.
KDE: avoid Spectacle's `-a`/`-u`/`-r` by hand; `-a` grabs whatever is active.

## Recording

```bash
$L capture record out.webm --seconds 10 --screen DP-1             # one monitor
$L capture record out.webm --seconds 10 --area 1600 200 800 450   # an area
$L capture record out.mp4 --seconds 10 --window class:org.kde.dolphin
$L capture record out.webm --seconds 300 --window class:codium &  # long take in the background;
kill -INT <pid printed on its first line>                          # stop early, file stays valid
$L capture record out.webm --pointer ...                          # cursor drawn into the video
$L capture frames out.webm --seconds 10 --screen DP-1             # ~1-2 fps stills joined: small evidence files
```

- Videos are as long as the recording took: when nothing changes, the last frame
  is repeated (KDE pads the end; COSMIC writes a constant rate).
- `.webm` gives VP8/VP9, `.mp4` H.264 (OpenH264; Fedora's ffmpeg has no libx264).
- **KDE** records the monitor that holds the target and crops it, so `--window`
  raises the window without focus (else whatever covers it is filmed) and puts the
  previous top window back at the end; a window moved mid-recording is not
  followed. It needs a saved screen-share grant; without one `record` exits 3 and
  shows no dialog. Then run `$L capture record-setup` once with the user: tick
  EVERY monitor tile (not "full workspace", "virtual screen" or "region"), keep
  "Allow restoring" ticked, press Share. Click it only when the user asked you
  to, verifying each click with a screenshot. A new monitor or layout can
  invalidate the grant; `record` then stops with a message instead of a dialog.
- **GNOME** and **COSMIC** need no grant. `--window` records the window's own
  pixels: it follows the window and is not hidden by windows on top; the frame is
  a fixed size (GNOME: window top-left, rest black, possibly 2x on fractional scaling).
- Default target: the monitor of the active window.
- To catch a glitch that lasts a second or two, record `--screen` while
  reproducing, extract frames (`ffmpeg -i rec.webm -vf fps=20 f/%04d.png`) and
  compare each frame with the last per region; single screenshots miss the moment.
- 2560x1440 at 30 fps costs about one CPU core on COSMIC (Python copies frames).

## One-time setup per desktop

- **KDE:** nothing for input, windows, screenshots, a11y or OCR. Real-time video:
  `$L capture record-setup` (above). Revoke: delete
  `~/.local/state/linux-computer-use/screencast-monitors.token`.
- **GNOME:** GNOME refuses window lists, screenshots and `Eval` to outside
  processes, so `scripts/gnome/extension/computer-use@claude.local` (~200 lines)
  does them inside the shell and exports `org.claude.ComputerUse` on
  `org.gnome.Shell` (any session-bus process can call it, the same exposure Mutter's
  RemoteDesktop/ScreenCast APIs already have; Flatpak apps cannot). `$L setup`
  installs it, adds it to `enabled-extensions` and turns accessibility on; it is
  active from the next login, or at once with `scripts/gnome/load-extension-live.py`
  (drives Looking Glass through Alt+F2 after confirming that UI by accessibility;
  takes the keyboard for ~5 s; needs `org.gnome.shell development-tools` or
  `--allow-devtools`; run it only when the user agreed or is away; `--force`
  reloads changed code). Undo: `gnome-extensions uninstall computer-use@claude.local`.
- **COSMIC:** `$L setup` shows the Remote desktop dialog once (input). cosmic-comp
  refuses its own EIS method to everyone but its portal, so there is no way around
  that dialog. `$L input --forget` deletes the grant. Nothing else asks.

Grants live in `~/.local/state/linux-computer-use/`; grants saved by the earlier
per-desktop skills (`~/.local/state/claude-kde-capture/`,
`~/.local/state/cosmic-computer-use/`) are picked up once.

## Verifying (rerun after desktop or libei updates)

| Test | Checks | Expected | Last pass |
|---|---|---|---|
| `tests/test-input.sh [MONITOR]` | full-screen GTK4 probe: clicks, shift/ctrl-click, drag, wheel, typing, ctrl+a, `paste` and clipboard restore | 14 `ok`, exit 0 (exit 2 = aborted before any input) | KDE 2026-10-30 |
| `tests/test-window.sh [MONITOR]` | every window action the desktop supports on a probe, plus `launch` | all `ok` (13 on KDE) | KDE 2026-10-30 |
| `tests/test-a11y.sh` | three GTK4 dialogs answered by a11y press, a11y click, OCR click; their exit codes prove the button | 3 `ok` | KDE 2026-10-30 |
| `tests/test-record.sh` | each monitor, an area and a probe window; duration and size | all `ok` (KDE needs the grant) | KDE 2026-10-30 |
| `tests/test-learn.sh` | `lcu learn` on a copy of the log | 12 `ok` | 2026-10-30 |

`test-input.sh` refuses to send input unless the probe is the active, full-screen
window on MONITOR and has seen the pointer move over it. On GNOME and COSMIC the
same tests passed with the earlier per-desktop skills on 2026-10-29; run them under
`lcu` there before relying on the merged code, and record what breaks.

## Prior art

Checked 2026-10-29. kwin-mcp (isac322: KWin EIS + AT-SPI, mostly in virtual KWin
sessions), gnome-ui-mcp (asattelmaier), cosmic-desktop-mcp (mtul0729: Rust, the same
COSMIC protocols), computer-use-linux (agent-sh: Rust MCP, many desktops) and
lihe07/computer-use (COSMIC via the portal) are MCP servers that need a build or a
container. The ydotool/uinput-based skills (dual-wield-mcp, LinUse,
desktop-control-wayland, dev-test-linux, tine) need root setup. The agent
vendors' own computer-use features mostly target macOS/Windows. This skill keeps one interface across
the three desktops as plain scripts on the system Python, with nothing to build.
