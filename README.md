# linux-computer-use

An agent skill that lets a coding agent use a Linux Wayland desktop the way a person
does: move and click the mouse, drag and drop, type and paste, press shortcuts, take
screenshots and recordings, find buttons by name or by the text on them, and open,
arrange and close windows. One command, `lcu`, detects whether it is running on
**KDE Plasma 6**, **GNOME** or **COSMIC** and drives that desktop through its own
interfaces: no `/dev/uinput`, no ydotool, nothing from pip, and everything runs as
the desktop user. The one exception is optional: `lcu panel`, which records what the
monitors really show, needs a one-time root setup (see below).

Beyond the basics it can:

- check an input target before sending anything (`input --window`: exactly one window,
  focused, every point on it);
- wait for the screen to stop changing instead of sleeping (`capture shot --settle`,
  `--since PREV.png`);
- record every monitor at once into one video laid out like the desktop
  (`capture record --all`);
- record the kernel's scanout, which shows damage and repaint bugs that a
  compositor-rendered recording hides (`panel record`).

The commands, options and JSON are the same on all three desktops. Where a desktop
cannot do something (COSMIC has no protocol to place a window at x,y, for example),
the tool says so and exits non-zero; [SKILL.md](SKILL.md) has the per-desktop tables.

It follows the open Agent Skills layout (a folder with `SKILL.md`, `name` and
`description` front matter, and its own scripts), and everything it does is plain
shell commands, so it works with any agent that loads such skills and can run a
shell: Codex, Gemini CLI, Antigravity and others. Nothing in it calls one vendor's
tools. It grew out of three per-desktop skills (kde-, gnome- and cosmic-computer-use)
and shares one implementation of input, accessibility, OCR and the lessons log.

## Install

**Claude Code:** add the repository as a marketplace and install the plugin, then turn
on auto-update for the marketplace in `/plugin` > Marketplaces (it is off by default
for marketplaces like this one).

```text
/plugin marketplace add nilltadios/linux-computer-use
/plugin install linux-computer-use@linux-computer-use
```

From a shell: `claude plugin install linux-computer-use --marketplace
nilltadios/linux-computer-use` does both in one step; `claude plugin update
linux-computer-use@linux-computer-use` fetches a new version.

To edit the skill or add shared lessons, use a git clone instead, and keep it current
outside the skill, for example with a session-start hook that runs `git pull --ff-only`.
A clone in `~/.claude/skills/` also loads there, so remove the plugin first, or remove
the clone's symlink if you switch to the plugin.

**Other agents:** clone it into the skills folder your agent reads; see your agent's
documentation for the folder. Common ones: `~/.agents/skills/` (shared by several
agents, Codex among them), `~/.codex/skills/` (Codex), `~/.gemini/config/skills/`
(Antigravity). For several agents, keep one clone and symlink it into the others'
folders, so they share one lessons log.

```bash
git clone https://github.com/nilltadios/linux-computer-use ~/.agents/skills/linux-computer-use
~/.agents/skills/linux-computer-use/lcu detect
~/.agents/skills/linux-computer-use/lcu check
```

`check` lists what is missing for the detected desktop and changes nothing: `need`
lines are required, `opt` lines only for the feature named next to them. Everything
runs on the distribution's Python 3 with PyGObject (`/usr/bin/python3`; a Python from
uv, pyenv or a venv usually lacks it).

| Desktop | Required | Optional (feature) |
|---|---|---|
| all | Wayland session, `libei` 1.x, python3-gobject, gdk-pixbuf2 | at-spi2-core (a11y), tesseract + English data (OCR), wl-clipboard (`paste`), gtk-launch (starting apps), gtk4 and jq (tests) |
| KDE Plasma 6.1+ | KWin's EIS interface (Plasma 6.1+), `spectacle`, `kscreen-doctor`, ffmpeg | GStreamer `pipewiresrc vp8enc webmmux` and xdg-desktop-portal-kde (real-time recording) |
| GNOME 45+ | Mutter RemoteDesktop and ScreenCast, GStreamer `pipewiresrc pngenc vp8enc webmmux`, the bridge extension (`lcu setup`) | ffmpeg (`frames`, `.mp4`); Looking Glass (live extension reloads) |
| COSMIC (cosmic-comp 1.x) | xdg-desktop-portal-cosmic (RemoteDesktop v2); the compositor's toplevel, workspace and `ext-image-copy-capture` Wayland protocols (cosmic-comp offers them) | ffmpeg (recording) |
| `lcu panel` (any desktop) | a DRM graphics card, Mesa EGL (surfaceless) with GLES 3, sudo, setcap (libcap), a root-owned `cc` and `ld` (gcc or clang, binutils, which also gives readelf), a root-owned Rust compiler: a distro `rust` package, or where `/usr/bin/rustc` is rustup's wrapper (Arch `rustup`), root's own toolchain | ffmpeg with utvideo (`.mkv`), libopenh264 (`.mp4`) or libvpx-vp9 (`.webm`) |

One-time setup, always with the person at the screen:

- **KDE:** none, except a screen-share grant for real-time video (`lcu capture
  record-setup`: KDE's share dialog, pick all monitors).
- **GNOME:** the small bridge shell extension (`lcu setup`, active after the next login).
- **COSMIC:** the Remote desktop permission for input (`lcu setup`: one dialog; the grant
  survives reboots).
- **`lcu panel` (optional, any desktop):** `lcu panel setup` builds a small helper
  (Rust, standard library only) and installs it as `/usr/local/libexec/lcu-panel-grab`
  with one file capability, CAP_SYS_ADMIN, which the kernel requires for the scanout
  buffer. It asks for the person's sudo password. **Afterwards any program running as
  that user can read the screen through the helper without a share dialog.** Undo:
  `lcu panel setup --remove`. On Arch with rustup, give root its own toolchain first:
  `sudo rustup toolchain install stable --profile minimal`. Setup builds only a source
  that matches GitHub, which it checks with git, so run it from a git clone; a plugin
  install is not a checkout and refuses unless you compare the printed checksums with
  GitHub yourself and pass `--allow-local`.

## Use

```bash
L=~/.agents/skills/linux-computer-use/lcu    # wherever it is installed
$L window list
$L capture shot /tmp/x.png --window class:org.kde.dolphin
$L capture shot /tmp/after.png --window class:org.kde.dolphin --since /tmp/x.png   # after it changed and settled
$L a11y press dolphin --name "New Folder" --role button
$L input --window class:org.kde.dolphin move 800 400 click left type "hello" key enter
$L input paste "Grüße ✓"
$L capture record /tmp/x.webm --seconds 5 --screen DP-1
$L capture record /tmp/all.webm --seconds 5 --all
$L panel record /tmp/panel.mkv --all --seconds 3         # after `lcu panel setup`
```

[SKILL.md](SKILL.md) is the full reference (and what the agent reads).
[LEARNINGS.md](LEARNINGS.md) is the shared log of lessons from real sessions about
computer use itself, tagged by desktop. Lessons about one specific app go in
`LEARNINGS.local.md` instead (`lcu learn add --local ...`), which is never published:
it is git-ignored in a clone, and a plugin install keeps it in
`~/.local/state/linux-computer-use/`.

## Layout

```
lcu                       entry point: detect, check, setup, input, window, capture, panel, a11y, ocr, learn
.claude-plugin/           Claude Code plugin and marketplace manifests
scripts/lcu_env.py        desktop detection and helpers shared by every script
scripts/input.py          libei input (KWin EIS / Mutter RemoteDesktop / RemoteDesktop portal), --window checks
scripts/portal.py         RemoteDesktop and ScreenCast portal clients
scripts/settle.py         capture shot --settle / --since (shared by every desktop)
scripts/a11y.py           AT-SPI find/press
scripts/ocr.py            tesseract, two passes
scripts/learn.py          LEARNINGS.md and LEARNINGS.local.md helper
scripts/panel.py          kernel scanout recording (GPU decode, ffmpeg)
scripts/panel/            the privileged helper (lcu-panel-grab.rs), its reproducible build and root setup
scripts/kde/              window (KWin script, pointer drags), capture (Spectacle, portal), check
scripts/gnome/            window, capture, bridge extension, setup, check
scripts/cosmic/           window, pointer drags, capture, pure-Python Wayland client + protocol XMLs, check
tests/                    end-to-end and offline tests
```

## Tests

End-to-end tests open their own throwaway probe windows and dialogs:

- `test-input.sh`: clicks, modifiers, drag, wheel, typing, `paste`. Nothing is sent
  until its probe is active, full screen and has seen the pointer.
- `test-input-window.sh`: `input --window` refusals send nothing; accepted input
  reaches only the target.
- `test-window.sh`, `test-move-to-state.sh`: every window action the desktop supports,
  `launch`, and fullscreen/maximized geometry across monitors.
- `test-a11y.sh`: dialogs answered by a11y press, a11y click and OCR click.
- `test-record.sh`, `test-settle-live.sh`: recordings (each monitor, an area, `--all`,
  a window); fixed sleep versus `--settle` versus `--since`.
- `test-panel.sh`: `panel record --all` from the real scanout (skips without setup).

`test-learn.sh` runs on a temporary copy of the lessons log. `test-settle.py`,
`test-portal-grant.py` and `test-resize-validation.py` are offline: no desktop, no
input. Run the Python ones with `/usr/bin/python3 -s`.

On KDE, `test-drag-resize.sh` checks all eight resize handles and `test-drag-move.py`
checks title-bar dragging with a visually verified grab point. Both use KWin-only
window data, and they restore window geometry afterwards. Pass an existing window
only when it is authorized for testing; see each script's usage and
[the window commands](SKILL.md#windows-and-apps-lcu-window).

SKILL.md's Verifying section lists each test's expected output and when it last
passed on which desktop.

## License

MIT, see [LICENSE](LICENSE).
