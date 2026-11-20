#!/usr/bin/env bash
# Build lcu-panel-grab from lcu-panel-grab.rs: the one build command setup.sh and audits share.
#   build.sh OUT            build with the root-owned system compiler (a distro `rust` package, or
#                           root's own rustup toolchain where /usr/bin/rustc is rustup's wrapper)
#   build.sh --dev OUT      build with whatever rustc is on PATH (rustup): for testing only;
#                           setup.sh never installs a --dev build
#   build.sh --test         compile and run the unit tests with the rustc on PATH (no privilege)
# Same source + same compiler -> byte-identical output (fixed flags, no paths or timestamps).
# Why the system compiler: the result runs with CAP_SYS_ADMIN, so the compiler, its standard
# library and the linker must be files only root can change. rustup's (~/.rustup) belong to the
# user account, so any program running as the user could plant code in them. No Cargo: it would
# read ~/.cargo/config.toml, which can add flags.
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
if [[ ${1:-} == --test ]]; then
  t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  rustc --edition 2024 --test -o "$t/tests" "$here/lcu-panel-grab.rs" && "$t/tests"
  exit
fi
# The real compiler binary of the account running this (root, under setup.sh):
#   - /usr/bin/rustc from a distro package (Fedora/Arch `rust`, Debian `rustc`), or
#   - where /usr/bin/rustc is rustup's wrapper (Arch `rustup`): this account's own default
#     toolchain, resolved with `rustup which` and then run directly, so rustup never takes part.
# Ownership is checked by the caller; a user's ~/.rustup toolchain is refused there.
system_rustc() {
  local r=/usr/bin/rustc home
  if [[ ! -x $r ]]; then
    echo "build.sh: no Rust compiler at $r. Install one: Fedora \`sudo dnf install rust\`, Arch \`sudo pacman -S rust\` (or, with rustup, \`sudo rustup toolchain install stable --profile minimal\`), Debian/Ubuntu \`sudo apt install rustc\`" >&2
    return 1
  fi
  if [[ $(basename "$(readlink -f "$r")") != rustup ]]; then echo "$r"; return; fi
  home=$(getent passwd "$(id -u)" | cut -d: -f6)
  r=$(env -i PATH=/usr/bin:/bin HOME="$home" /usr/bin/rustup which rustc 2>/dev/null) || r=
  if [[ ! -x $r ]]; then
    echo "build.sh: /usr/bin/rustc is rustup's wrapper and $(id -un) has no rustup toolchain. As root this needs root's own: \`sudo rustup toolchain install stable --profile minimal\` (installs to $home/.rustup; your own toolchains cannot be used, they are not root-owned)" >&2
    return 1
  fi
  echo "$r"
}

dev=; [[ ${1:-} == --dev ]] && { dev=1; shift; }
out=${1:?usage: build.sh [--dev] OUT}
out=$(realpath -m "$out")

if [[ $dev ]]; then
  rustc=$(command -v rustc)
else
  rustc=$(system_rustc)
  # the compiler, its sysroot (std, librustc_driver) and the linker must not be writable by anyone but root
  sysroot=$(env -i PATH=/usr/bin:/bin "$rustc" --print sysroot)
  [[ -d $sysroot ]] || { echo "build.sh: $rustc reports no sysroot" >&2; exit 1; }
  for f in "$(readlink -f "$rustc")" "$sysroot" "$sysroot/lib" "$sysroot/lib/rustlib" /usr/bin/cc "$(readlink -f /usr/bin/cc)" /usr/bin/ld "$(readlink -f /usr/bin/ld)"; do
    read -r owner mode <<<"$(stat -L -c '%U %a' "$f")"   # -L: a symlink's own mode is always 777
    [[ $owner == root && $(( 8#$mode & 8#022 )) == 0 ]] || { echo "build.sh: $f is not root-owned and protected ($owner $mode)" >&2; exit 1; }
  done
  bad=$(find "$sysroot" \( ! -user root -o \( ! -type l -perm /022 \) \) -print -quit)
  [[ -z $bad ]] || { echo "build.sh: $bad in the compiler's sysroot is not root-owned and protected" >&2; exit 1; }
fi

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cp "$here/lcu-panel-grab.rs" "$tmp/lcu-panel-grab.rs"
# Clean environment: no RUSTFLAGS, CARGO_*, CCACHE, LD_* or PATH entries from the caller.
# --dev keeps HOME/RUSTUP_* so rustup can find its toolchain.
envs=(PATH=/usr/bin:/bin LANG=C SOURCE_DATE_EPOCH=0)
[[ $dev ]] && envs+=(HOME="$HOME" ${RUSTUP_HOME:+RUSTUP_HOME=$RUSTUP_HOME} ${RUSTUP_TOOLCHAIN:+RUSTUP_TOOLCHAIN=$RUSTUP_TOOLCHAIN})
(cd "$tmp" && env -i "${envs[@]}" "$rustc" --edition 2024 --crate-type bin --crate-name lcu_panel_grab \
  -C opt-level=2 -C panic=abort -C codegen-units=1 -C strip=symbols -C debuginfo=0 \
  -C relocation-model=pie -C link-arg=-Wl,-z,relro,-z,now -C link-arg=-Wl,--build-id=none \
  --remap-path-prefix "$tmp=." -o "$tmp/lcu-panel-grab" lcu-panel-grab.rs)
# no RPATH/RUNPATH: the loader would honor an absolute one even in a privileged process
# (a shell match, not a pipe into grep/rg: a missing tool must not make the check pass)
dyn=$(readelf -d "$tmp/lcu-panel-grab") || { echo "build.sh: readelf failed (binutils)" >&2; exit 1; }
if [[ $dyn == *RPATH* || $dyn == *RUNPATH* ]]; then echo "build.sh: binary has an RPATH/RUNPATH" >&2; exit 1; fi
install -D -m 0755 "$tmp/lcu-panel-grab" "$out"
echo "$out $(sha256sum "$out" | cut -d' ' -f1) ($("$rustc" --version 2>/dev/null))"
