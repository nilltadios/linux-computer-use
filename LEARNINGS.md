# Learnings

Lessons from real sessions with this skill, oldest first. SKILL.md says when to
read and write this file ("Lessons"). Add entries with
`lcu learn add` and run `lcu learn check` after any edit.

Each entry is one verified lesson:

    ### YYYY-MM-DD · kind · one-line lesson
    - Status: active | promoted (moved into SKILL.md) | superseded (by a newer entry) | wrong
    - App: window class or app name (kind app only)
    - Desktop: kde | gnome | cosmic | all (all = holds on every desktop)
    - Seen on: compositor, shell, libei and toolkit versions (stamped by the helper)
    - What: what happened or what is true
    - Do: what to do instead, or how to use it
    - Evidence: the command and the observation that verified it

Kinds: `new` (a capability or trick), `better` (a better way than SKILL.md
gives), `broken` (SKILL.md advice that failed or stopped working), `app` (how
one app behaves under this skill). Never delete an entry; change its Status
and say why, so a later session does not re-learn a dead end.

App lessons go in LEARNINGS.local.md (`lcu learn add --local`): this file is only
for Linux computer use itself. Earlier app entries were moved out on 2026-11-05.

Entries before 2026-10-30 come from the three skills this one merges
(kde-computer-use, gnome-computer-use, cosmic-computer-use); their commands name
the old per-desktop scripts (`kde-input.py`, `gnome-a11y.py`...), which are now
`lcu input`, `lcu a11y` and so on.

## Entries

### 2026-10-29 · better · Custom sliders in Electron apps can ignore arrow keys; click the stop
- Status: promoted (SKILL.md "Input" notes)
- Desktop: all
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: A web-drawn slider (a reasoning-effort picker in an Electron app) did not move on `key left` with the popup open, while a click on the track moved the handle.
- Do: Crop-screenshot the slider, measure the spacing between stop dots, click one stop away from the handle, then screenshot again and read the label to confirm the value.
- Evidence: `kde-input.py key left` left the label unchanged; `kde-input.py move <handle_x-42> <y> click left` changed it to the next value, confirmed by a crop screenshot.

### 2026-10-29 · better · Re-crop after layout changes; a reused --area can cut off the target
- Status: promoted (SKILL.md "Screenshots", 2026-11-04)
- Desktop: all
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: The same `--area` crop that showed an app's message box in one view cut off its left edge in another view of the app, hiding attached chips that had to be checked before sending.
- Do: Before trusting a crop for verification, derive it from a fresh full-window shot of the current view; if the left or right edge of the control is not visible, widen the crop.
- Evidence: Two `kde-capture.py shot --area` calls with the same box: the first showed the whole composer, the second (different view) started mid-chip; a wider crop showed both chips.

### 2026-10-29 · new · GNOME Shell dialogs (Run a Command, Looking Glass, prompts) open on the monitor under the pointer
- Status: promoted (SKILL.md "Windows and focus")
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: Alt+F2 opened the Run a Command dialog on DP-1 while the pointer was there; a screenshot of the primary monitor showed only the dim backdrop.
- Do: Find shell dialogs with gnome-a11y.py find gnome-shell --name ... (monitor-independent), or screenshot the monitor that holds the pointer, or move the pointer to the wanted monitor first.
- Evidence: gnome-input.py key alt+f2 -> gnome-capture.py shot --screen eDP-1 showed no dialog, --screen DP-1 showed it; a11y find gnome-shell --name 'run a command' matched in both cases

### 2026-10-29 · broken · GTK4 accessibility boxes ignore container margins; centres can be 10-30 px off
- Status: promoted (SKILL.md toolkit table)
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: In a zenity (GTK 4.16) dialog the No button's a11y box was at (0,149) in the window while it is drawn at (24,162); nested labels inherit the same origin. Sizes are correct.
- Do: In GTK4 apps prefer gnome-a11y.py press, or OCR coordinates for clicks; if you click at an a11y centre, verify the target with a crop screenshot first.
- Evidence: gnome-a11y.py find zenity --name no -> centre 678,513; screenshot shows the button spanning 642..762 x 504..546 (centre 702,525); OCR gave 702-ish

### 2026-10-29 · better · Never use OCR alone to confirm a dialog opened; the same words may be in another window
- Status: promoted (SKILL.md "Windows and focus")
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: An OCR check for 'Run a Command' matched text in a chat window that quoted the phrase while the dialog itself had not opened on that monitor.
- Do: Confirm shell UI through gnome-shell's accessibility tree (role + exact name + a focused text entry) before typing into it; for app dialogs use gnome-window.py active.
- Evidence: gnome-ocr.py 'Run a Command' --area ... matched a chat line ('alone': false) with no dialog on that screen

### 2026-10-29 · broken · gnome-a11y.py --name "" matched every control; press hit the first button (fixed)
- Status: promoted
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: An empty --name was treated as no name filter, so press --role button activated the first button in the tree (an app's Launch button) instead of failing.
- Do: Fixed: the script now rejects an empty --name. Always pass a real name to press.
- Evidence: gnome-a11y.py press <libadwaita app> --name '' --role button --depth 25 -> pressed first button; after fix -> exits 1 with 'must not be empty'

### 2026-10-29 · better · libadwaita apps need gnome-a11y.py --depth 25-30; default 12 finds nothing
- Status: promoted (SKILL.md a11y default depth)
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: In a libadwaita (GTK4) app, find --name for a visible button returned no matches at the default depth 12; tree --depth 25 showed it.
- Do: Pass --depth 30 to find/press in libadwaita apps; find now prints this hint on stderr when nothing matches.
- Evidence: find gearlever --name 'Check for updates' --exact -> []; same with --depth 30 -> match

### 2026-10-29 · new · Nautilus to GTK4 app drag-and-drop works with a stepped manual drag
- Status: promoted (input.py drag, 2026-10-30)
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: Dragging a file icon from Nautilus into another GTK4 app's window on the same monitor was accepted as a file drop.
- Do: Activate Nautilus, then: move ICON sleep 200 down left sleep 200 rmove 10 5 sleep 100 rmove 20 10 sleep 100, several move steps toward the target with sleep 100, move TARGET sleep 500 rmove 3 3 sleep 500 up left. The small first moves start the DnD; the pause over the target lets it register.
- Evidence: gnome-input.py with that sequence -> target app showed the dropped file's details page

### 2026-10-29 · new · Super+Left/Right through gnome-input.py half-tiles the focused window exactly
- Status: promoted (SKILL.md "Input" notes)
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: To put a window on the left half of a monitor, the GNOME tiling shortcut is simpler than computing geometry and accounts for the work area (panels).
- Do: gnome-window.py activate MATCH; confirm with active; gnome-input.py key super+left; check with gnome-window.py info MATCH.
- Evidence: maximized Electron window on a 1536x960 monitor with a bottom panel -> after key super+left: x=0 y=0 width=768 height=912, maximized=false

### 2026-10-29 · broken · Screenshots of a lower-scale monitor were upscaled and blurry
- Status: promoted (SKILL.md "Coordinates" and gnome-capture.py)
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: Shell.Screenshot renders the whole stage at the largest monitor scale (1.667), so a crop of eDP-1 (scale 1.25) came out 2560x1600 instead of 1920x1200 and visibly soft.
- Do: Fixed in gnome-capture.py with bridge version 3: regions inside one monitor are rendered with Clutter.Stage.paint_to_content at that monitor's scale. Prefer --screen/--window/--area over whole-desktop shots when text must be read.
- Evidence: shot --area 0 0 600 300 before: 1000x500 at 1.6667; after: 750x375 at 1.25, SSIM 1.000 against a native Mutter ScreenCast frame of the same area

### 2026-10-29 · new · New app windows open on the pointer's monitor and may ignore their saved maximized state; use gnome-window.py launch
- Status: promoted (SKILL.md)
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: Loupe opened on DP-1 because the pointer was there, although the task was on eDP-1, and it came back unmaximized after being maximized and closed through gnome-window.py close.
- Do: Start apps with gnome-window.py launch --on OUTPUT [--maximize|--fullscreen] -- CMD; it moves the pointer to OUTPUT first, waits for the new window, moves it if needed and applies the state.
- Evidence: gio open file.png with pointer on DP-1 -> window on DP-1; launch --on eDP-1 --maximize -- loupe file.png -> output eDP-1, maximized true, 0,0 1536x912

### 2026-10-29 · better · Save and restore the user's clipboard around wl-copy pastes
- Status: promoted (SKILL.md)
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: Pasting long text (comments, bug reports) through wl-copy + ctrl+v replaced whatever the user had copied (an image in one case).
- Do: Before: wl-paste --list-types | head -1 > types; wl-paste --no-newline > clip.bak. After: wl-copy --type "$(cat types)" < clip.bak. Mention it in the final message.
- Evidence: Saved image/png 226829 B, pasted a GitLab comment, restored; wl-paste --list-types showed image/png and the same byte count

### 2026-10-29 · broken · pkill -f PATTERN in a Bash tool call can kill the call's own shell
- Status: promoted (SKILL.md)
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: pkill -f /usr/bin/loupe matched the bash -c command line that contained the same text and killed it (exit 144) before anything else ran.
- Do: Use pgrep -x NAME / pkill -x NAME, flatpak kill APPID, or gnome-window.py close; never pkill -f with a pattern that appears in your own command.
- Evidence: bash -c '...pkill -f /usr/bin/loupe; ...' -> exit code 144, no later command ran

### 2026-10-29 · new · Flatpak apps cannot read files passed by path unless they go through the document portal
- Status: promoted (SKILL.md)
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: flatpak run org.gnome.Showtime /tmp/x.webm failed with 'No such file'; the same file opened via gio open (or flatpak run --file-forwarding ... @@u file @@) worked through /run/user/UID/doc/.
- Do: Open files in Flatpak apps with gio open FILE or gnome-window.py launch -- gio open FILE, and keep test files outside /tmp (e.g. under ~/Desktop) since /tmp is private to the sandbox.
- Evidence: Showtime log: filesrc No such file /tmp/...; gio open ~/Desktop/...webm -> Playing video: file:///run/user/1000/doc/<id>/...

### 2026-10-29 · new · Catch short-lived UI glitches by recording the screen and diffing frames
- Status: promoted (SKILL.md)
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: A viewer redrew part of an image wrongly a few seconds after maximizing; single screenshots kept missing the moment or caught the wrong state.
- Do: gnome-capture.py record --screen OUTPUT while reproducing, then ffmpeg -vf fps=20 to PNGs and compare each frame with the last (or a reference) per region to find when and where it changes; crop those frames to look.
- Evidence: 20 fps frame diff of a 10 s recording showed the bottom band changing at 5.95-6.3 s while the top stayed fixed; the cropped frames showed the corrupted strip

### 2026-10-29 · new · cosmic-comp refuses its own EIS D-Bus method to everyone but the portal and the on-screen keyboard
- Status: promoted
- Desktop: cosmic
- Seen on: cosmic-comp 1.10.0, xdg-desktop-portal-cosmic 1.10.0, libei 1.6.0, gtk4 4.24.1
- What: com.system76.CosmicComp.Ei.GetSenderSocket (the COSMIC twin of Mutter's ConnectToEIS) checks that the caller owns org.freedesktop.impl.portal.desktop.cosmic or com.system76.CosmicOSK; any other caller gets AccessDenied.
- Do: Get input through the RemoteDesktop portal with persist_mode 2 and keep the restore token (cosmic-input.py does this). Do not try to own those bus names.
- Evidence: gdbus call to /com/system76/CosmicComp/Ei GetSenderSocket(3) -> org.freedesktop.DBus.Error.AccessDenied; cosmic-comp src/dbus/ei.rs ALLOWED_NAMES lists only those two names

### 2026-10-29 · broken · cosmic-comp sends KEYBOARD_MODIFIERS EIS events every ~150 ms, so "wait until quiet" never ends
- Status: promoted
- Desktop: cosmic
- Seen on: cosmic-comp 1.10.0, xdg-desktop-portal-cosmic 1.10.0, libei 1.6.0, gtk4 4.24.1
- What: After the devices are resumed, the EIS connection keeps receiving bursts of five EI_EVENT_KEYBOARD_MODIFIERS; a device-setup loop that waited for silence ran into its 3 s timeout on every call.
- Do: Count only seat and device events when deciding that device setup is finished (fixed in cosmic-input.py; a call now takes ~0.3 s).
- Evidence: tracing Input._events printed KEYBOARD_MODIFIERS at 0.16 s, 0.31 s, 0.47 s... until 3.0 s; after the fix cosmic-input.py --list-regions took 0.33 s

### 2026-10-29 · new · Two windows can report the activated state at once, one per monitor; only the last activated one gets keys
- Status: promoted
- Desktop: cosmic
- Seen on: cosmic-comp 1.10.0, xdg-desktop-portal-cosmic 1.10.0, libei 1.6.0, gtk4 4.24.1
- What: After moving a focused window to the other monitor, cosmic-window.py list showed it and the previous window on the first monitor both active. A key went to whichever was activated last; moving the pointer over the other one (no click) did not change that.
- Do: Run cosmic-window.py activate MATCH immediately before key/type; do not infer keyboard focus from the active flag alone.
- Evidence: two input_probe.py windows on eDP-1 and DP-1, both active:true; activate P1 + key a -> only P1 logged a; activate P2 + key b -> only P2 logged b; pointer onto P2 + key c -> P1 logged c

### 2026-10-29 · new · GTK 4.24 accessibility boxes line up exactly with cosmic-comp window geometry
- Status: promoted (SKILL.md toolkit table)
- Desktop: cosmic
- Seen on: cosmic-comp 1.10.0, xdg-desktop-portal-cosmic 1.10.0, libei 1.6.0, gtk4 4.24.1
- What: The gnome skill saw GTK 4.16 boxes ignore container margins. On GTK 4.24 a dialog's No button was at window (274,102) 53x34 in AT-SPI, exactly where the screenshot of the window (at cosmic-comp's reported x/y) drew it.
- Do: cosmic-a11y.py find box centres are safe click targets in GTK 4.24 apps (still check with a crop).
- Evidence: cosmic-a11y.py tree on tests/dialog.py vs cosmic-capture.py shot --window: button 'No' (274,102,53,34) = drawn at 343..408 x 128..170 px at scale 1.25; tests/test-a11y.sh 'click No at accessibility coordinates' ok

### 2026-10-29 · new · Window-source captures come out at 1 px per logical px, output captures at native resolution
- Status: promoted
- Desktop: cosmic
- Seen on: cosmic-comp 1.10.0, xdg-desktop-portal-cosmic 1.10.0, libei 1.6.0, gtk4 4.24.1
- What: ext-image-copy-capture of a foreign toplevel returned a 1707x904 buffer for a 1707x904 logical window on a 1.5-scale monitor, while the output capture of that monitor was 2560x1440.
- Do: For sharp window shots raise the window and crop it from its output (cosmic-capture.py shot --window, the default); use --own only when the window is covered.
- Evidence: CaptureSession(window=...) size (1707, 904); CaptureSession(output=DP-1) size (2560, 1440)

### 2026-10-29 · new · A second launch of a single-instance GTK app opens no new window
- Status: promoted (SKILL.md "launch")
- Desktop: all
- Seen on: cosmic-comp 1.10.0, xdg-desktop-portal-cosmic 1.10.0, libei 1.6.0, gtk4 4.24.1
- What: Starting tests/dialog.py twice with the same application id (default GApplication flags) produced only one window: the second process handed its activation to the first and exited.
- Do: For test windows use Gio.ApplicationFlags.NON_UNIQUE; when waiting for a user app's new window, match by new window id (cosmic-window.py launch), not by process.
- Evidence: dialog.py focus-test-A then focus-test-B -> list showed no focus-test-B; with NON_UNIQUE both windows appeared

### 2026-10-29 · new · Drag-and-drop from COSMIC Files works with cosmic-input.py drag; a large first move after the press cancels it
- Status: promoted (input.py drag, 2026-10-30)
- Desktop: cosmic
- Seen on: cosmic-comp 1.10.0, xdg-desktop-portal-cosmic 1.10.0, libei 1.6.0, gtk4 4.24.1
- What: Dropping a file from COSMIC Files on one monitor onto a Flatpak libadwaita window (Gear Lever) on the other monitor works with the built-in drag (20 even steps). It fails when the first motion after the press jumps far from the item (about 190 px), even with pauses and a final move over the target, and with press-jump-release. Pauses are not what makes it work.
- Do: Use cosmic-input.py drag SRC_X SRC_Y DST_X DST_Y. For a hand-built drag, make the first move after down left small (under ~20 px, still on the item), then step to the target.
- Evidence: Files row on DP-1 to Gear Lever on eDP-1, success = Gear Lever opened the file's page: drag 9/10; stepped moves with 100-200 ms pauses but a 190 px first move 0/5, same with a 15 px first move 2/2; press, jump, release 0/5

### 2026-10-30 · better · Spectacle -a and -m give native-scale shots on KDE; -m follows the active output, not the pointer
- Status: promoted (SKILL.md Coordinates, kde/capture.py)
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: Spectacle's whole-desktop grab (-f) is rendered at one uniform scale (2.0 with monitors at 1.25 and 1.6), so crops of lower-scale monitors are upscaled. -a (active window) returns the window at its monitor's scale; -m (current monitor) returns KWin's active output, the one holding the focused window, at its native size, even when the pointer is on the other monitor.
- Do: Promoted: lcu capture shot uses -a for --window and -m for --screen/--area on the active output, else crops -f; the JSON 'source' says which.
- Evidence: spectacle -b -n -f -> 6272x2120 for a 3136x1060 desktop; -m with the pointer on DP-1 and focus on eDP-1 -> 1920x1200 showing eDP-1; -a on a maximized window 1536x914 -> 1920x1143

### 2026-10-30 · broken · KDE ScreenCast recordings of a still screen ended early
- Status: promoted (kde/capture.py)
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: KWin sends PipeWire frames only when the picture changes, so a 3 s recording of a static window gave a 0.6-1.0 s WebM; pipewiresrc keepalive-time=100 did not change that.
- Do: Fixed (promoted): lcu capture record pads the end with the last frame up to the wall-clock length (ffmpeg tpad=stop_mode=clone), like the COSMIC recorder.
- Evidence: record --seconds 3 --window <static probe> -> 0.566 s before the fix; tests/test-record.sh after it -> 3.0 s for both monitors, an area and a window

### 2026-10-30 · broken · wl-copy with captured stdout/stderr never returns; paste lost the user's clipboard once
- Status: promoted (input.py paste)
- Desktop: all
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: wl-copy forks a server that keeps serving the selection and holds the pipes it inherited, so subprocess.run(capture_output=True) on it timed out; the paste action died before restoring the clipboard.
- Do: Fixed (promoted): input.py runs wl-copy with stdout/stderr to /dev/null and text on stdin, and restores the clipboard in a finally block. If a paste ever dies anyway on KDE, Klipper's history (getClipboardHistoryItem 1) holds the previous text.
- Evidence: lcu input paste probe-paste -> TimeoutExpired after 10 s, clipboard left as 'probe-paste'; after the fix tests/test-input.sh 'paste put the clipboard back' ok and the clipboard hash was unchanged

### 2026-10-30 · better · OCR missed a focus-ringed button in a dark theme; a greyscale pass reads it
- Status: promoted (ocr.py)
- Desktop: all
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: tesseract (psm 11) on a dark GTK4 dialog read 'Yes' but not the focused 'No' button (red focus ring), so a search for No matched only the sentence 'click No' and the click missed. The greyscale copy read both; 2x or 3x upscaling made it worse.
- Do: Promoted: lcu ocr reads a greyscale and a colour copy and merges the matches; it now found the button at the same centre the accessibility tree gives.
- Evidence: tests/test-a11y.sh OCR step: FAIL (exit open) before; tesseract on format=gray -> 'No(96) No(96)'; after the change OCR No at 2458,640 = a11y centre, test 3/3 ok

### 2026-10-30 · better · Resize a client-decorated window by pointer: inside approach, small steps, measured grab points
- Status: promoted (window drag-resize)
- App: libcosmic
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: On KWin, resizing a libcosmic (client-side decorated) window by pointer fails silently in four ways. (1) 'input drag' and any drag whose first move is large (~40 px) do nothing. (2) A single jump onto the border from outside the window does not register: the app picks the resize edge from pointer motion inside it. (3) At scale 1.6 the border is only 2-5 px deep (6 px shows the normal arrow), and 2-3 px in at the rounded bottom-right corner is outside the window, so the press lands in the window behind it. (4) A corner touching the screen edge reads as that side edge alone. Hand resizes also stop at the app's minimum size. Likely similar for other CSD toolkits.
- Do: Grab 4 px in at the bottom-right corner, 3 px at the top-left, or the middle of the one edge that must move. Confirm the resize cursor first with 'capture shot --area ... --pointer'. Then: input move <12 px further inside> sleep 100 move X Y sleep 200 down left sleep 300, then rmove steps of at most 8 px (12-50 ms apart), then sleep 400 up left. Compare 'window info' before and after, and stop at the first drag that changed nothing so later presses cannot land in other windows.
- Evidence: input drag 2298 698 2700 900 -> still 700x500; manual sequence from 2296,696 -> 1103.75x698.75. Cursor probes at 2-6 px above the bottom edge: resize arrow at 2-5, normal at 6. 12-step drags of 46 px/step -> unchanged; 8 px steps with an inside approach -> 8 of 8 target sizes reached (widths stop at 940, the app minimum).

### 2026-10-30 · better · KWin resize safety needs its own hit test and enough initial motion
- Status: promoted (window at and drag-resize)
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: A thin server-side resize border extends outside frameGeometry. Rectangle checks identify a window behind it. Six pixels of initial motion did not start a resize on the GTK4 probe, while sixteen pixels did. A drag can also stop short of the requested dimensions, so the returned geometry matters.
- Do: Use window at, which calls workspace.windowAt, to verify the actual target including resize borders. Use window drag-resize for small stepped motion, crossing the drag threshold before checking the resize flag. Exit 3 means the target was not reached; inspect the actual dimensions rather than assuming a minimum-size failure.
- Evidence: GTK4 probe on KWin: 6 px initial motion -> resizing false; 16 px -> resizing true and width increased 16.25 px. workspace.windowAt returned the probe 1-4 px beyond its right frame, while frame containment returned the window behind it. tests/test-drag-resize.sh verifies all eight handles and reports constrained targets separately.

### 2026-10-30 · new · Direct geometry does not test the minimum size reachable by pointer
- Status: promoted (SKILL.md window commands)
- App: libcosmic
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: Assigning frameGeometry through a KWin script can force a client-decorated window below its advertised minimum. Pointer resizing respects that minimum.
- Do: Use window drag-resize when testing sizes a person can reach. Reserve window geometry for explicit placement or forced-layout tests, and label those tests accordingly.
- Evidence: Isolated libcosmic app: min_size 380x400, direct geometry 190x200 -> actual 190x200. After restoring a normal size, drag-resize to 190x200 -> actual 380x400, exit 3 with target not reached. Normal targets 1160x700, 1000x600 and 1080x640 were reached exactly.

### 2026-10-30 · new · Exact resize targets can depend on window position
- Status: promoted (SKILL.md drag-resize exit 3)
- App: it.mijorus.gearlever
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: All eight handles worked on libcosmic, GTK4/libadwaita and Qt windows. Three GTK4 bottom-facing growth targets stopped 3.75 logical pixels beyond the requested height at one position; moving the window 40 pixels upward made the same three growth/shrink pairs reach their targets exactly. This is consistent with desktop snapping; the test did not isolate its cause.
- Do: Treat exit 3 as a real target mismatch, not a failure to start a drag. Inspect attempts, actual size and fixed edges. For a suspected position-dependent constraint, save the original geometry and retest at a nearby clear position before changing the input code. Restore the original geometry afterward.
- Evidence: Physical pointer test of all eight handles, growing 50 px and shrinking back: libcosmic 16/16 exact targets, Qt 16/16, GTK4/libadwaita 13/16 at the initial position. The three GTK4 bottom-facing handles passed all 6 operations after a -40 px vertical translation. All unselected edges stayed within 1 logical pixel throughout, and all original geometries were restored. Initial target mismatches remain in the test record.

### 2026-10-30 · better · Verify title-bar moves and preserve the pointer
- Status: promoted (window drag-move)
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: A verified header point can move libcosmic, GTK4/libadwaita and Qt windows through real pointer input. A tiny requested movement still needs enough initial motion to start the drag. Targets 8 px from an output edge can snap to the edge even when the window size stays unchanged.
- Do: Choose a non-interactive header point from a fresh screenshot and pass its frame-relative coordinates to window drag-move. The command hit-tests before pressing, checks pointer/window stability, confirms moving with unchanged size, and corrects actual motion. It requires a 16 px destination margin, starts inward when necessary, releases the button and restores the pointer on exit. Treat exit 3 as a constrained target and inspect actual geometry.
- Evidence: Authenticator (libcosmic), Gear Lever (GTK4/libadwaita), KWrite (Qt): all eight directions plus a 2-by-3-pixel move and a no-op passed per app (30 checks). Final tiny/near-edge/no-op checks passed on each app (9 checks), with unchanged sizes and restored pointer positions. A target 8 px from the edge snapped flush with the edge and returned exit 3; the 16 px margin retest reached its target. Original window geometries were restored. Regression tests cover obstruction, pointer interference, invalid/ambiguous targets and failed-grab cleanup.

### 2026-10-30 · new · After stopping a KDE recording, wait for the final JSON line before using the file
- Status: promoted (SKILL.md "Recording", re-verified 2026-11-04 on KWin 6.8.2)
- Desktop: kde
- Seen on: KWin 6.7.4, Plasma 6.7.4, libei ?, spectacle ?
- What: kill -INT on capture record returns at once, but the script then finalises gst output and re-encodes with ffmpeg (padding to wall-clock length). For an 80 s 2560x1440 take this took about a minute; reading the file earlier gave 'File ended prematurely' and a partial size.
- Do: Run record with stdout redirected to a log; after kill -INT, wait until the log has a second JSON line with "file" (or the pid is gone) before ffprobe or frame extraction.
- Evidence: capture record --seconds 900 --screen DP-1 in background, kill -INT after ~80 s -> immediate ffprobe: truncated file; ~60 s later log printed {"file": ...} and ffprobe gave duration 82.8 s, frames readable

### 2026-10-30 · broken · KDE recordings without --pointer hide the drag-and-drop icon too, so drags are invisible
- Status: promoted
- Desktop: kde
- Seen on: KWin 6.7.4, Plasma 6.7.4, libei ?, spectacle ?
- What: capture record --screen without --pointer requests cursor_mode hidden. A Dolphin to Gear Lever drag produced no changed frames at all (0 to 19 s static, drop result at 19.6 s). The same kind of drag recorded with --pointer showed the cursor and the dragged file icon moving every frame. The DnD icon is composited with the cursor in the ScreenCast stream.
- Do: Pass --pointer whenever the video should show input. For a visible drag, also slow it down (manual down/move/sleep/up sequence over ~3 s); input drag finishes in about 1 s.
- Evidence: no --pointer: mpdecimate found no distinct frames during the drag; --pointer: distinct frames every ~33 ms from 9.4 to 13.5 s, extracted frames show cursor plus Dolphin drag icon over the target folder

### 2026-10-30 · broken · KDE drag-resize and drag-move refuse a window that fills the usable height
- Status: promoted (SKILL.md and window drag-resize panel check)
- Desktop: kde
- Seen on: KWin 6.7.4, Plasma 6.7.4, libei ?, spectacle ?
- What: Gear Lever (GTK4, client-side decorations) at y 0 with height equal to the usable area: drag-resize --edge bottom-left failed with 'bottom edge is off the usable area' (needs 2 px margin) and drag-move refused any destination (needs the whole frame 16 px inside). After nudging the frame to y 4, height 906, the left edge resized but the bottom press still did not start a resize: the CSD resize border lies under the panel. The top edge then worked.
- Do: For a full-height or tiled window, first run window geometry to inset it a few px from top and bottom (not a drag; say so if the user asked for drags), then resize height with --edge top, then drag-move. Avoid bottom-edge resizes when the bottom sits on the panel. Since 2026-10-30 the script detects that case (panel windows are reported with dock: true) and exits 1 with 'resize zone is under a panel' instead of pressing on the panel and then inside the window; before, a panel-margin press counted as a wallpaper press. A person cannot resize from an edge they cannot reach either, so the refusal is intended.
- Evidence: drag-resize 1000 800 --edge bottom-left -> exit 1 off usable area; drag-move 2389 100 -> exit 1 must fit 16 px; after geometry y4 h906: bottom-left -> width 1000 but 'no press on the bottom edge started a resize'; --edge top -> exit 0 1000x800; drag-move 1889 57 --grab 400 20 -> exit 0

### 2026-10-30 · broken · drag-move across monitors with different scales reported a size change
- Status: promoted
- Desktop: kde
- Seen on: KWin 6.7.4, Plasma 6.7.4, libei ?, spectacle ?
- What: Dragging a 665.3x705.3 libcosmic window from DP-1 (scale 1.5) to eDP-1 (scale 1.25) reached the target but exited 1 'window size changed during the move': the size became 666.4x706.4. Logical size is whole physical pixels over the scale, so it shifts by about a pixel when the scale changes. Fixed: the size check allows 2 px when the output changed (1 px otherwise).
- Do: Nothing extra; if a cross-monitor move still reports a size change, compare the change with 2/scale before treating it as a resize.
- Evidence: drag-move DP-1 -> eDP-1: target reached, 665.33x705.33 -> 666.4x706.4, exit 1 before the fix; tests/test-resize-validation.py test_size_tolerance_across_monitor_scales; after the fix 700x700 window DP-1 <-> eDP-1 both exit 0

### 2026-10-30 · better · drag-move speed: any glide speed lands exactly; default is now 0.4 s press to release
- Status: promoted
- Desktop: kde
- Seen on: KWin 6.7.4, Plasma 6.7.4, libei ?, spectacle ?
- What: drag-move used 8 px moves 25 ms apart plus fixed pauses: about 2 s overhead and 9.5 s for 1620 px. Benchmarks on a libcosmic window (same screen and across monitors with scales 1.25/1.5): step 8-2000 px, interval 0-25 ms, all exit 0 with 0 px error. A plain timed drag without the threshold step lands one pointer step short (the client starts its move on the first motion), and fixed sleeps overrun (50 moves at 20 ms took 1.5 s). KWin script queries take about 4 ms.
- Do: Use the default (0.4 s), --fast (0.1 s) or --slow (1 s); the glide is clock-paced and aims at target + measured lag. For hand-built timed drags with input, nudge 4 px first and shift the end point by the nudge, and pace moves by the clock, not fixed sleeps.
- Evidence: Warehouse COSMIC 700x700, eDP-1 <-> DP-1: --fast 0.103-0.105 s, default 0.404 s, --slow 1.005 s, all landed exactly, corrections 0; earlier raw input drags: 0.1 s -> 77,16 px short, 1 s (50x20 ms) -> 14,3 px short and 1.5 s long

### 2026-10-30 · better · OCR can match a word inside a neighbouring longer button; check alone and a pointer crop
- Status: promoted (SKILL.md OCR "alone")
- Desktop: all
- Seen on: KWin 6.7.4, Plasma 6.7.4, libei ?, spectacle ?
- What: Looking for a 'Comment' button next to a 'Comment and close issue' button, lcu ocr Comment returned only one match, alone false: the first word of the longer, destructive button. The real button was about 100 px to its left and was not returned at all.
- Do: Before clicking an OCR match for a short label, require alone: true or compute the point from a screenshot, then hover and take capture shot --area ... --pointer to see which button the pointer is on. Treat alone: false on a button-sized label as a warning.
- Evidence: ocr Comment -> [2012,865] alone false (inside 'Comment and close issue'); screenshot placed the Comment button at 1914,863; pointer crop at 1914,863 showed the hand on 'Comment'

### 2026-10-30 · new · Ctrl+wheel zoom works with keydown ctrl ... keyup ctrl in one input call
- Status: promoted (SKILL.md "Input" examples)
- Desktop: kde
- Seen on: KWin 6.7.4, Plasma 6.7.4, libei ?, spectacle ?
- What: In LibreWolf on KDE, with the window activated and the pointer over the page, keydown ctrl + three scroll -1 + keyup ctrl zoomed 100% -> 130% (address-bar badge), and the same with scroll 1 went back to 100%.
- Do: Activate the target window, put the pointer over it, and send keydown ctrl, scroll steps, keyup ctrl in one lcu input call so the key is released. Check the result (zoom badge or a screenshot).
- Evidence: lcu input move 768 600 keydown ctrl scroll -1 x3 keyup ctrl -> 130% badge; scroll 1 x3 -> badge gone (100%)

### 2026-10-30 · better · Find a context menu's real position with window list --all before clicking its items
- Status: promoted (SKILL.md "Windows and focus")
- Desktop: kde
- Seen on: KWin 6.7.4, Plasma 6.7.4, libei ?, spectacle ?
- What: A right-click near a monitor's bottom-right edge in LibreWolf opened the menu up and to the left of the pointer, so a crop below the pointer missed it. window list --all listed the menu as a librewolf window with an empty title and its exact geometry (942,255 357x381); OCR inside that area found the items.
- Do: After right-clicking, run window list --all, take the new untitled popup of that app, crop and OCR inside its geometry, and click an item whose match has alone: true (Copy vs Copy Link to Highlight, Paste vs Paste Without Formatting).
- Evidence: right-click at 1300,637 -> popup librewolf '' 942,255 357x381; ocr Copy in that area -> [973,278] alone true and [973,361] alone false; click -> clipboard held the selected text

### 2026-11-02 · new · GNOME: resize and move by pointer drag work with plain input down/move/up; CSD resize zone is in the shadow
- Status: promoted (SKILL.md "Windows and apps", 2026-11-04)
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: drag-resize and drag-move are KDE-only. On GNOME a hand-built drag works: for a libadwaita/GTK4 window (CSD, buffer 25 px larger than the frame on each side) pressing 5 px outside the visible frame edge or corner, then 6 px steps, resized it exactly on all 8 handles; a press on a blank header spot and a 20-step glide moved it exactly with the size unchanged.
- Do: Activate the window, press 5 px outside the visible frame (window info x/y/width/height; the buffer holds the shadow), lcu input move X Y down left rmove 2 2 then rmove steps, move to the end point, up left; check window info. For moves, pick a blank header spot from a fresh screenshot.
- Evidence: Gear Lever 700x700: each of 8 handles shrank by exactly 60 px and grew back to 700x700; header drag (-200,+120) moved 1801,29 -> 1601,149 and back, size unchanged

### 2026-11-02 · broken · GNOME: buttons and wheel of a new input session are dropped until it has moved
- Status: promoted (input.py)
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: Mutter dropped every click and wheel detent sent as the first actions of an lcu input call (no move first); waiting 100-300 ms did not help, a zero rmove did. Keys were unaffected. The old per-desktop test passed only because of timing. Fixed in input.py: on GNOME a session that has not moved sends rmove 0 0 before its first button or scroll.
- Do: Nothing; input.py does it. If clicks vanish on another compositor, test 'click left' against 'rmove 0 0 click left' on the probe.
- Evidence: probe: 'click left', 'sleep 300 click left' -> 0 presses; 'rmove 0 0 click left' -> 1; bare 'scroll 1' -> 0 wheel; tests/test-input.sh 14 ok after the fix

### 2026-11-02 · broken · libcosmic apps ignore the pointer-enter position; a single jump misses their resize border
- Status: promoted (input.py)
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: lcu input move sent one absolute motion; jumping into a libcosmic window (COSMIC Authenticator on GNOME) arrives as wl_pointer.enter only, which the app ignores, so a press right after hit no resize border (edges did nothing at any offset) while GTK windows resized. Any second motion fixes it, even to the same point. Fixed: the CLI move action and the start of drag repeat the motion once (move(settle=True)). Likely on KDE too; untested there.
- Do: Nothing; input.py does it. In custom drags built from Input.move, pass settle=True for the press point.
- Evidence: 'move X Y down left ...' -> 962x664 unchanged; 'move X Y move X Y down left ...' -> 902x664; after the fix all 8 edges/corners shrank 60 px and grew back exactly

### 2026-11-02 · broken · GNOME: wl-paste takes focus, and hangs while a keep-above window is focused
- Status: promoted (SKILL.md and input paste)
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: Reading the clipboard with wl-paste moved focus from a full-screen keep-above probe to the window below, so the keys that followed went there (paste and the input test's own clipboard read). With a keep-above window focused, wl-paste --list-types never returned (5 s timeout); windowed or full-screen without keep-above it answered in 20 ms. Fixed: paste restores focus before ctrl+v and refuses if it cannot; test-input.sh reads the clipboard before its safety checks and no longer sets keep-above on GNOME.
- Do: Do not run wl-paste between a focus check and input; check focus again after it. Use lcu input paste, which handles this.
- Evidence: active before wl-paste: probe, after: the window below; wl-paste --list-types: windowed rc 0 in 0.02 s, keep-above rc 124 after 5 s, fullscreen-only rc 0

### 2026-11-02 · new · COSMIC: window drag-move and drag-resize by pointer; no geometry while a window is held
- Status: promoted (SKILL.md COSMIC drags, 2026-11-04)
- Desktop: cosmic
- Seen on: cosmic-comp 1.11.0, xdg-desktop-portal-cosmic 1.11.0, libei 1.6.0, gtk4 4.24.1
- What: cosmic-comp sends no geometry for a window while a move or resize grab holds it: an open toplevel-info connection gets no events until the release, and a new one sees x/y null (after waiting its 0.6 s geometry timeout). An idle desktop can also lag geometry past a short timeout, so null is not a usable moving flag. The window follows the pointer without lag, and its resize zone reaches 3 px outside the frame for SSD (Qt), GTK and libcosmic windows alike.
- Do: Use lcu window drag-move / drag-resize; they release on schedule and verify after. Do not poll lcu window info during a held drag (each call then takes ~0.7 s). Keep move targets 16 px inside the usable area: a pointer near the top edge snapped a window to the top half.
- Evidence: Dolphin (Flatpak, SSD), COSMIC Terminal, Gear Lever on DP-1 (scale 1.5): 8 edges/corners each shrank 60 px and grew back exactly (24/24); 12 header moves incl. DP-1 <-> eDP-1 (scale 1.25) landed exactly in 0.40 s, --fast 0.1 s, --slow 1.0 s; panel size M measured 56 logical px on both monitors

### 2026-11-02 · broken · KDE move-to must preserve fullscreen and maximized destination geometry
- Status: promoted
- Desktop: kde
- Seen on: KWin 6.8.2, Plasma 6.8.2, libei 1.6.0, spectacle 6.8.2
- What: Moving fullscreen or maximized windows between differently sized outputs retained the old dimensions because normal-window centering overwrote KWin destination sizing.
- Do: After sendClientToScreen, let KWin size fullscreen and maximized windows; center only normal windows. Run tests/test-move-to-state.sh on a two-monitor desktop to check actual geometry as well as the state flag.
- Evidence: KDE 6.8.2: the previous release failed all four fullscreen/maximized cross-monitor geometry checks; skipping normal-window centering for those states passed all four.

### 2026-11-04 · broken · KDE screen-share grants belong to the app lcu runs under
- Status: promoted (portal.py per-app tokens, SKILL.md "Recording", 2026-11-04)
- Desktop: kde
- Seen on: KWin 6.8.2, Plasma 6.8.2, libei 1.6.0, spectacle 6.8.2
- What: The ScreenCast portal stores a restore token for the app id it reads from the caller's systemd scope (app-<id>-<n>.scope). A grant saved while lcu ran under one app was not accepted when lcu ran under another: the portal showed 'Choose screens to share with <app>' and record timed out. Seen after a distribution upgrade, when the same machine started running lcu from a desktop app's scope; likely on any portal backend that keys grants by app id.
- Do: Nothing; portal.py now keeps one grant per app id and the error names the app. When record says the grant was not accepted, run capture record-setup with the user from that same app.
- Evidence: PermissionStore Lookup screencast showed the saved token under app '' and two others under the desktop app's id; test-record.sh failed 4/4 with the old file, a screenshot during record showed the share dialog naming the app; with the per-app token file all 4 passed.

### 2026-11-05 · broken · On a locked COSMIC screen, input still reaches the greeter
- Status: active
- Desktop: cosmic
- Seen on: cosmic-comp 1.11.0, xdg-desktop-portal-cosmic 1.11.0, libei 1.6.0, gtk4 4.24.1
- What: With the screen locked, lcu input keeps working: typed text and Enter go to cosmic-greeter as a password attempt. A capture can fail with 'no frame' once and then return only the wallpaper, and loginctl LockedHint stays no.
- Do: Treat any 'no frame' capture, or a shot showing no windows, as a locked screen. Take a shot and confirm the window before each input, as separate calls so a failed shot stops the input. Never send input until the user has unlocked.
- Evidence: capture shot -> no frame within 5 s; input type + key enter -> journal shows cosmic-greeter authentication failure; next area shot -> wallpaper only; LockedHint=no

### 2026-11-05 · broken · Update the skill from outside SKILL.md, before it is read
- Status: active
- Desktop: all
- Seen on: cosmic-comp 1.11.0, xdg-desktop-portal-cosmic 1.11.0, libei 1.6.0, gtk4 4.24.1
- What: SKILL.md used to tell agents to check for updates and reread it, so an update cost two reads of the skill in one session. The check is removed; nothing in the skill updates it now, so an install with no outside update stays on its old version.
- Do: Do not add an update step back to SKILL.md. Claude Code users who only use the skill: install the plugin and turn on auto-update for its marketplace; a new version normally loads the next session. Anyone editing the skill or adding shared lessons: keep a git clone and pull it from a session-start hook (git pull --ff-only, silent, with a timeout) so the first read is current; a pull that cannot fast-forward leaves the clone behind with no warning. Other agents: use their own start hook or pull by hand. If an install looks out of date, tell the user once rather than updating mid-session.
- Evidence: SessionStart hook in a new session -> .git/FETCH_HEAD updated; test clone one commit behind -> pulled to latest; clone with a local commit -> unchanged; plugin install from GitHub -> skill found and lcu runs from the cached copy. Plugin auto-update has not been seen firing yet.

### 2026-11-08 · new · Input drags work on COSMIC; the Remote desktop grant survives reboots
- Status: active
- Desktop: cosmic
- Seen on: cosmic-comp 1.11.0, xdg-desktop-portal-cosmic 1.11.0, libei 1.6.0, gtk4 4.24.1
- What: Real pointer drags with 'input --window id:ID drag X1 Y1 X2 Y2' moved a libcosmic splitter (mouse_area with on_press) as expected. No Remote desktop dialog appeared, not even for the first input call after a reboot: the restore token saved in an earlier session was reused and rewritten. The app saw its first motion a few px after the press, so a 100 px drag moved the splitter about 97 px; likely the same for any iced/libcosmic drag handle.
- Do: Use input --window ... drag for drag-to-resize tests on COSMIC; find the handle in a fresh 'capture shot --window MATCH --own' (1 px per logical px) and allow about 3 px of lift-off in assertions. Expect no dialog once a grant exists for the app.
- Evidence: drag of 100 px -> splitter +97 px; drag of 60 px -> +57 px; drag past the limit -> clamped; no permission prompt this boot, token mtime updated at the first call

### 2026-11-08 · new · record --all films every monitor from one portal session
- Status: promoted
- Desktop: kde
- Seen on: KWin 6.8.2, Plasma 6.8.2, libei 1.6.0, spectacle 6.8.2
- What: Two simultaneous 'capture record --screen' runs race for KDE's single-use restore token; the loser gets the share dialog and exits 1 (one parallel pair worked, the next failed). Added 'capture record --all': one session, one GStreamer branch per shared monitor, composed in the desktop layout.
- Do: Use 'lcu capture record OUT.mp4 --all' to film several monitors at once; never start two record runs together. Written into SKILL.md (Recording) and tests/test-record.sh.
- Evidence: parallel --screen eDP-1 + --screen DP-1 -> b=1 'grant ... not accepted silently'; record --all --seconds 8 -> rc 0, 3838x1298, 7.97 s; tests/test-record.sh -> 5 ok (all: 3.0 s, 3838x1298)
