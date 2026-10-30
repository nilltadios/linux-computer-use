# Learnings

Lessons from real sessions with this skill, oldest first. SKILL.md says when to
read and write this file ("Keep this skill current"). Add entries with
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

Entries before 2026-10-30 come from the three skills this one merges
(kde-computer-use, gnome-computer-use, cosmic-computer-use); their commands name
the old per-desktop scripts (`kde-input.py`, `gnome-a11y.py`...), which are now
`lcu input`, `lcu a11y` and so on.

## Entries

### 2026-10-29 · better · Custom sliders in Electron apps can ignore arrow keys; click the stop
- Status: active
- Desktop: all
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: A web-drawn slider (a reasoning-effort picker in an Electron app) did not move on `key left` with the popup open, while a click on the track moved the handle.
- Do: Crop-screenshot the slider, measure the spacing between stop dots, click one stop away from the handle, then screenshot again and read the label to confirm the value.
- Evidence: `kde-input.py key left` left the label unchanged; `kde-input.py move <handle_x-42> <y> click left` changed it to the next value, confirmed by a crop screenshot.

### 2026-10-29 · better · Re-crop after layout changes; a reused --area can cut off the target
- Status: active
- Desktop: all
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: The same `--area` crop that showed an app's message box in one view cut off its left edge in another view of the app, hiding attached chips that had to be checked before sending.
- Do: Before trusting a crop for verification, derive it from a fresh full-window shot of the current view; if the left or right edge of the control is not visible, widen the crop.
- Evidence: Two `kde-capture.py shot --area` calls with the same box: the first showed the whole composer, the second (different view) started mid-chip; a wider crop showed both chips.

### 2026-10-29 · new · GNOME Shell dialogs (Run a Command, Looking Glass, prompts) open on the monitor under the pointer
- Status: active
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: Alt+F2 opened the Run a Command dialog on DP-1 while the pointer was there; a screenshot of the primary monitor showed only the dim backdrop.
- Do: Find shell dialogs with gnome-a11y.py find gnome-shell --name ... (monitor-independent), or screenshot the monitor that holds the pointer, or move the pointer to the wanted monitor first.
- Evidence: gnome-input.py key alt+f2 -> gnome-capture.py shot --screen eDP-1 showed no dialog, --screen DP-1 showed it; a11y find gnome-shell --name 'run a command' matched in both cases

### 2026-10-29 · broken · GTK4 accessibility boxes ignore container margins; centres can be 10-30 px off
- Status: active
- Desktop: gnome
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: In a zenity (GTK 4.16) dialog the No button's a11y box was at (0,149) in the window while it is drawn at (24,162); nested labels inherit the same origin. Sizes are correct.
- Do: In GTK4 apps prefer gnome-a11y.py press, or OCR coordinates for clicks; if you click at an a11y centre, verify the target with a crop screenshot first.
- Evidence: gnome-a11y.py find zenity --name no -> centre 678,513; screenshot shows the button spanning 642..762 x 504..546 (centre 702,525); OCR gave 702-ish

### 2026-10-29 · better · Never use OCR alone to confirm a dialog opened; the same words may be in another window
- Status: active
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
- Status: active
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

### 2026-10-29 · app · Gear Lever 4.x: the install button is 'Move to the app menu', and it moves the file
- Status: active
- App: it.mijorus.gearlever
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: After an AppImage is opened or dropped, there is no 'Install' button. The red 'Move to the app menu' button installs it: the file is moved (not copied) to ~/AppImages/<name>.appimage and a .desktop entry is written to ~/.local/share/applications. Afterwards the page shows Launch/Remove. The back arrow at the top-left returns to 'Installed applications'. Drag-and-drop of an AppImage onto the main window is accepted.
- Do: gnome-a11y.py press gearlever --name 'Move to the app menu' --role button --exact --depth 25; verify with ls ~/AppImages and the Installed applications list
- Evidence: Gear Lever 4.6.2 flatpak: press -> ok, file gone from source folder, present in ~/AppImages, listed under Installed applications

### 2026-10-29 · app · Starting VSCodium/VS Code with --force-renderer-accessibility switches the editor to Screen Reader Optimized mode
- Status: active
- App: codium
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: Launching the VSCodium AppImage with --force-renderer-accessibility (as SKILL.md advises for an a11y tree) made the status bar show 'Screen Reader Optimized'; the editor then behaves in screen-reader mode (e.g. different word highlighting).
- Do: Only add the flag when you need AT-SPI inside the window; for opening a file or screenshots leave it off, or mention the mode in your report. It applies to that run only unless editor.accessibilitySupport is saved in settings.
- Evidence: vscodium.appimage --force-renderer-accessibility --new-window file.txt -> status bar item 'Screen Reader Optimized' visible in a full-monitor screenshot

### 2026-10-29 · new · Super+Left/Right through gnome-input.py half-tiles the focused window exactly
- Status: active
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

### 2026-10-29 · app · Jira's description editor needs a second click before select-all, and converts pasted Markdown
- Status: active
- App: Jira Cloud (redhat.atlassian.net) in a browser
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: In the Create dialog the first click on the template only activated the editor; ctrl+a + ctrl+v then did nothing. A second click inside the active editor, ctrl+a, ctrl+v replaced the template, and the pasted Markdown (### headings, lists, backticks, links) became formatting.
- Do: Click the description, click again inside it, ctrl+a, ctrl+v; scroll the dialog to check the template is gone. Pickers (Affects versions, Components): click, type the value, Enter.
- Evidence: First paste: template unchanged in a crop screenshot; second: headings and code spans rendered, template text gone

### 2026-10-29 · app · Switch GitLab's comment box to plain text before pasting Markdown
- Status: active
- App: GitLab (gitlab.gnome.org) in a browser
- Desktop: all
- Seen on: GNOME Shell 49.5, mutter 49.4, libei 1.5.0, gtk4 4.16.7
- What: The comment box opens in rich-text mode. Its 'Switch to plain text editing' link under the box gives a Markdown textarea; Markdown pasted there rendered correctly on post. (Pasting Markdown into the rich-text mode was not tested.)
- Do: Click 'Switch to plain text editing', paste, check the text, then click Comment.
- Evidence: Pasted a Markdown comment in plain-text mode; the posted note rendered bullets, code spans and issue links

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
- Status: active
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
- Status: active
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
- Status: active
- App: libcosmic
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: On KWin, resizing a libcosmic (client-side decorated) window by pointer fails silently in four ways. (1) 'input drag' and any drag whose first move is large (~40 px) do nothing. (2) A single jump onto the border from outside the window does not register: the app picks the resize edge from pointer motion inside it. (3) At scale 1.6 the border is only 2-5 px deep (6 px shows the normal arrow), and 2-3 px in at the rounded bottom-right corner is outside the window, so the press lands in the window behind it. (4) A corner touching the screen edge reads as that side edge alone. Hand resizes also stop at the app's minimum size. Likely similar for other CSD toolkits.
- Do: Grab 4 px in at the bottom-right corner, 3 px at the top-left, or the middle of the one edge that must move. Confirm the resize cursor first with 'capture shot --area ... --pointer'. Then: input move <12 px further inside> sleep 100 move X Y sleep 200 down left sleep 300, then rmove steps of at most 8 px (12-50 ms apart), then sleep 400 up left. Compare 'window info' before and after, and stop at the first drag that changed nothing so later presses cannot land in other windows.
- Evidence: input drag 2298 698 2700 900 -> still 700x500; manual sequence from 2296,696 -> 1103.75x698.75. Cursor probes at 2-6 px above the bottom edge: resize arrow at 2-5, normal at 6. 12-step drags of 46 px/step -> unchanged; 8 px steps with an inside approach -> 8 of 8 target sizes reached (widths stop at 940, the app minimum).

### 2026-10-30 · app · 'dolphin --new-window' can open a tab in the existing window, and 'window launch' then returns that window
- Status: wrong (corrected 2026-10-30; the earlier window had already been closed)
- App: org.kde.dolphin
- Desktop: all
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: With Dolphin already running, 'lcu window launch --on DP-1 --match class:org.kde.dolphin -- dolphin --new-window DIR' added DIR as a tab to the user's existing Dolphin window and printed that window as the launched one, so later geometry calls resized the user's window.
- Do: Before launching Dolphin for a test, record the existing Dolphin window ids and their geometry/state. After launch, compare ids; if no new id appeared, do not move or resize anything, restore the window's state (maximize/minimize) and ask the user. Prefer a file manager that is not already open, or ask the user before using theirs.
- Evidence: window list afterwards: one org.kde.dolphin window with tabs 'screen' and 'drop test', same id that launch printed; restored with window maximize + minimize -> 1600x854 maximized, minimized


### 2026-10-30 · app · A new Dolphin window can restore the previous session's tabs
- Status: active
- App: org.kde.dolphin
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: The earlier Dolphin reuse report was incorrect. The previous window had been closed before the test launch; a new window restored the session's tabs and looked like the old window.
- Do: Compare window ids before and after launch. Restored tabs do not prove reuse. Do not change a pre-existing window without authorization. A new test window can still contain restored private tabs; prefer a disposable probe.
- Evidence: Corrected session chronology: previous window closed at 10:27, test launch at about 10:42. The earlier reuse claim was explicitly withdrawn in the handoff. The old entry is retained with Status wrong.

### 2026-10-30 · better · KWin resize safety needs its own hit test and enough initial motion
- Status: promoted (window at and drag-resize)
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: A thin server-side resize border extends outside frameGeometry. Rectangle checks identify a window behind it. Six pixels of initial motion did not start a resize on the GTK4 probe, while sixteen pixels did. A drag can also stop short of the requested dimensions, so the returned geometry matters.
- Do: Use window at, which calls workspace.windowAt, to verify the actual target including resize borders. Use window drag-resize for small stepped motion, crossing the drag threshold before checking the resize flag. Exit 3 means the target was not reached; inspect the actual dimensions rather than assuming a minimum-size failure.
- Evidence: GTK4 probe on KWin: 6 px initial motion -> resizing false; 16 px -> resizing true and width increased 16.25 px. workspace.windowAt returned the probe 1-4 px beyond its right frame, while frame containment returned the window behind it. tests/test-drag-resize.sh verifies all eight handles and reports constrained targets separately.

### 2026-10-30 · new · A Dolphin drop can reach a libcosmic Flatpak through text/uri-list
- Status: active
- App: org.kde.dolphin, libcosmic
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: A real Dolphin-to-libcosmic Flatpak drop opened the receiving app's review. Preferring the portal transfer key failed; preferring text/uri-list opened the file review. The filename contained a space. Files outside the sandbox's readable roots were not covered.
- Do: For compositor drag tests, use input drag after verifying the source and target windows. Confirm the receiving app's review without applying an install. A successful semantic drop command alone does not test a compositor drag.
- Evidence: The app repository's WC-002 follow-up records the real input drag onto the dev Flatpak, the opened review and cancellation.

### 2026-10-30 · new · Direct geometry does not test the minimum size reachable by pointer
- Status: promoted (SKILL.md window commands)
- App: libcosmic
- Desktop: kde
- Seen on: KWin 6.7.5, Plasma 6.7.5, libei 1.6.0, spectacle 6.7.5
- What: Assigning frameGeometry through a KWin script can force a client-decorated window below its advertised minimum. Pointer resizing respects that minimum.
- Do: Use window drag-resize when testing sizes a person can reach. Reserve window geometry for explicit placement or forced-layout tests, and label those tests accordingly.
- Evidence: Isolated libcosmic app: min_size 380x400, direct geometry 190x200 -> actual 190x200. After restoring a normal size, drag-resize to 190x200 -> actual 380x400, exit 3 with target not reached. Normal targets 1160x700, 1000x600 and 1080x640 were reached exactly.

### 2026-10-30 · new · Exact resize targets can depend on window position
- Status: active
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
- Status: active
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
- Status: active
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
- Status: active
- Desktop: all
- Seen on: KWin 6.7.4, Plasma 6.7.4, libei ?, spectacle ?
- What: Looking for a 'Comment' button next to a 'Comment and close issue' button, lcu ocr Comment returned only one match, alone false: the first word of the longer, destructive button. The real button was about 100 px to its left and was not returned at all.
- Do: Before clicking an OCR match for a short label, require alone: true or compute the point from a screenshot, then hover and take capture shot --area ... --pointer to see which button the pointer is on. Treat alone: false on a button-sized label as a warning.
- Evidence: ocr Comment -> [2012,865] alone false (inside 'Comment and close issue'); screenshot placed the Comment button at 1914,863; pointer crop at 1914,863 showed the hand on 'Comment'

### 2026-10-30 · new · Ctrl+wheel zoom works with keydown ctrl ... keyup ctrl in one input call
- Status: active
- Desktop: kde
- Seen on: KWin 6.7.4, Plasma 6.7.4, libei ?, spectacle ?
- What: In LibreWolf on KDE, with the window activated and the pointer over the page, keydown ctrl + three scroll -1 + keyup ctrl zoomed 100% -> 130% (address-bar badge), and the same with scroll 1 went back to 100%.
- Do: Activate the target window, put the pointer over it, and send keydown ctrl, scroll steps, keyup ctrl in one lcu input call so the key is released. Check the result (zoom badge or a screenshot).
- Evidence: lcu input move 768 600 keydown ctrl scroll -1 x3 keyup ctrl -> 130% badge; scroll 1 x3 -> badge gone (100%)
