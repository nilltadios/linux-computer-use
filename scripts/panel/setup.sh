#!/usr/bin/env bash
# One-time root setup for `lcu panel` (recording what the monitors really show).
#   setup.sh                 build and install the helper with sudo (asks for your password once)
#   setup.sh --allow-local   same, but accept a source that differs from GitHub (your own edits)
#   setup.sh --remove        undo: delete the installed helper
# What root does, and nothing else:
#   copy lcu-panel-grab.rs + build.sh into a root-only temp folder, check they are the files shown
#   below, build with the root-owned system compiler (/usr/bin/rustc, `sudo dnf install rust`), then
#   install -o root -g <your primary group> -m 0750  lcu-panel-grab  /usr/local/libexec/lcu-panel-grab
#   setcap cap_sys_admin+ep /usr/local/libexec/lcu-panel-grab
# Why it is built this way: the result runs with CAP_SYS_ADMIN, so nothing your account can write
# (rustup's compiler, ccache, a temp folder you own, an edited source) may reach it unseen:
#   - the compiler, its standard library and the linker must be root-owned (build.sh checks);
#   - the source must match GitHub's (origin/main), unless you pass --allow-local. This check runs
#     as you, from files your account can change, so it catches accidents, not an agent with your
#     account: before typing the password, open the printed commit on GitHub and compare the sums;
#   - root builds from its own copy, so the file cannot be swapped between build and install.
# Mode 0750 with your group keeps other accounts (service users in the video group) from running
# it. Install before setcap: any later chown/chgrp drops the capability.
# The capability stays on the file across reboots and system updates; rerun only if the helper's
# source changes. Effect to know about: after this, any program running under your account can
# read the screen through this helper without a share dialog.
set -euo pipefail
export PATH=/usr/bin:/bin   # no user-owned folder may supply sudo, git or sha256sum here
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
dest=/usr/local/libexec/lcu-panel-grab
if [[ ${1:-} == --remove ]]; then
  /usr/bin/sudo rm -f "$dest" && echo "removed $dest"
  exit 0
fi
allow_local=; [[ ${1:-} == --allow-local ]] && allow_local=1
[[ -x /usr/bin/rustc ]] || { echo "Fedora's Rust compiler is needed: sudo dnf install rust" >&2; exit 1; }
[[ -x /usr/sbin/setcap || -x /usr/bin/setcap ]] || { echo "setcap (libcap) is needed" >&2; exit 1; }

# What will be built: the two files, their commit, and whether they match GitHub.
files=(lcu-panel-grab.rs build.sh setup.sh)
repo=$(git -C "$here" rev-parse --show-toplevel 2>/dev/null || true)
if [[ $repo ]]; then
  echo "Source:     $(git -C "$here" log -1 --format='%h %ci %s' -- "${files[@]}")"
  git -C "$repo" fetch -q origin 2>/dev/null || echo "WARNING: could not reach GitHub to compare"
  changed=$(git -C "$here" diff --name-only origin/main -- "${files[@]}" 2>/dev/null; git -C "$here" status --porcelain -- "${files[@]}")
  if [[ $changed ]]; then
    echo "Differs from GitHub (origin/main): $(echo $changed | tr '\n' ' ')"
    [[ $allow_local ]] || { echo "Refusing: review the change (git diff origin/main -- scripts/panel), then rerun with --allow-local" >&2; exit 1; }
  else echo "Matches GitHub (origin/main)"; fi
else
  echo "WARNING: not a git checkout; cannot compare with GitHub"
  [[ $allow_local ]] || { echo "Refusing without --allow-local" >&2; exit 1; }
fi
declare -A sum
for f in "${files[@]}"; do sum[$f]=$(sha256sum "$here/$f" | cut -d' ' -f1); echo "sha256:     ${sum[$f]}  $f"; done
grp=$(id -gn)
echo "Allowed:    root and group $grp ($(getent group "$grp" | cut -d: -f4))"
echo "Installing $dest with CAP_SYS_ADMIN (sudo will ask for your password):"

# Root half: fixed text in this file; the only inputs are the paths, the checksums and the group.
/usr/bin/sudo env -i PATH=/usr/bin:/bin bash -s -- "$here" "$dest" "$grp" "${sum[lcu-panel-grab.rs]}" "${sum[build.sh]}" <<'ROOT'
set -euo pipefail
src=$1 dest=$2 grp=$3
w=$(mktemp -d); trap 'rm -rf "$w"' EXIT; chmod 0700 "$w"
cp -- "$src/lcu-panel-grab.rs" "$src/build.sh" "$w/"
echo "$4  $w/lcu-panel-grab.rs" | sha256sum -c --quiet || { echo "source changed after it was shown: stop" >&2; exit 1; }
echo "$5  $w/build.sh" | sha256sum -c --quiet || { echo "build.sh changed after it was shown: stop" >&2; exit 1; }
bash "$w/build.sh" "$w/out/lcu-panel-grab"
install -D -o root -g "$grp" -m 0750 "$w/out/lcu-panel-grab" "$dest"
setcap cap_sys_admin+ep "$dest"
ROOT
getcap "$dest"
stat -c '%A %U:%G %n' "$dest"
echo "installed sha256: $(sha256sum "$dest" | cut -d' ' -f1)"
"$dest" list || echo "(no monitor listed: are the screens on?)"
echo "done: \`lcu panel record OUT.mkv --screen NAME\` now works"
