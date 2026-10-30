# linux-computer-use

A Claude Code skill that lets Claude use a Linux Wayland desktop the way a person
does: move and click the mouse, drag and drop, type and paste, press shortcuts, take
screenshots and recordings, find buttons by name or by the text on them, and open,
arrange and close windows. One command, `lcu`, detects whether it is running on
**KDE Plasma 6**, **GNOME** or **COSMIC** and drives that desktop through its own
interfaces: no root, no `/dev/uinput`, no ydotool, nothing from pip.

It merges three earlier skills, kde-computer-use, gnome-computer-use and
cosmic-computer-use, into one interface, and carries their lessons across: KDE
gained `window launch`, sharp native-scale screenshots, `paste` with clipboard
restore, drag-and-drop that apps accept, full-length recordings of still screens
and a two-pass OCR; all three share one input, accessibility, OCR and lessons-log
implementation.

## Install

```bash
git clone https://github.com/<owner>/linux-computer-use ~/.claude/skills/linux-computer-use
~/.claude/skills/linux-computer-use/lcu detect
~/.claude/skills/linux-computer-use/lcu check
```

`check` lists what is missing for the detected desktop and changes nothing.
Everything runs on the distribution's Python 3 with PyGObject.

| Desktop | Required | Optional (feature) |
|---|---|---|
| all | Wayland session, `libei` 1.x, python3-gobject, gdk-pixbuf2 | at-spi2-core (a11y), tesseract + English data (OCR), ffmpeg (recording, frames), wl-clipboard (`paste`), gtk4 (tests), jq (tests) |
| KDE Plasma 6.1+ | `spectacle`, `kscreen-doctor` | GStreamer `pipewiresrc vp8enc webmmux`, xdg-desktop-portal-kde (real-time recording) |
| GNOME 45+ | GStreamer `pipewiresrc pngenc vp8enc webmmux`; the bridge extension (`lcu setup`) | Looking Glass for live extension reloads |
| COSMIC (cosmic-comp 1.x) | xdg-desktop-portal-cosmic (RemoteDesktop v2) | |

One-time setup: KDE needs none except a screen-share grant for real-time video
(`lcu capture record-setup`); GNOME needs the small bridge shell extension
(`lcu setup`, active after the next login); COSMIC asks once for remote-desktop
permission (`lcu setup`).

## Use

```bash
L=~/.claude/skills/linux-computer-use/lcu
$L window list
$L capture shot /tmp/x.png --window class:org.kde.dolphin
$L a11y press dolphin --name "New Folder" --role button
$L input move 800 400 click left type "hello" key enter
$L input paste "Grüße ✓"
$L capture record /tmp/x.webm --seconds 5 --screen DP-1
```

[SKILL.md](SKILL.md) is the full reference (and what Claude reads);
[LEARNINGS.md](LEARNINGS.md) is the log of lessons from real sessions, tagged by desktop.

## Layout

```
lcu                    entry point: detect, check, setup, input, window, capture, a11y, ocr, learn
scripts/lcu_env.py     desktop detection and helpers shared by every script
scripts/input.py       libei input (KWin EIS / Mutter RemoteDesktop / RemoteDesktop portal)
scripts/portal.py      RemoteDesktop and ScreenCast portal clients
scripts/a11y.py        AT-SPI find/press
scripts/ocr.py         tesseract, two passes
scripts/learn.py       LEARNINGS.md helper
scripts/kde/           window (KWin script), capture (Spectacle, portal), check
scripts/gnome/         window, capture, bridge extension, setup, check
scripts/cosmic/        window, capture, pure-Python Wayland client + protocol XMLs, check
tests/                 end-to-end tests (probe window, dialogs, recording, learn)
```

## Tests

`tests/test-input.sh`, `test-window.sh`, `test-a11y.sh`, `test-record.sh` and
`test-learn.sh` run against throwaway windows the tests open themselves; the input
test sends nothing until its probe window is active, full screen and has seen the
pointer. SKILL.md lists expected output and when each last passed on which desktop.

## License

MIT, see [LICENSE](LICENSE).
