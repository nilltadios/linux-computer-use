#!/usr/bin/env bash
# Build lcu-panel-grab from lcu-panel-grab.rs: the one build command setup.sh and audits share.
#   build.sh OUT            build with the root-owned system compiler (/usr/bin/rustc, Fedora `rust`)
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
dev=; [[ ${1:-} == --dev ]] && { dev=1; shift; }
out=${1:?usage: build.sh [--dev] OUT}
out=$(realpath -m "$out")

if [[ $dev ]]; then
  rustc=$(command -v rustc)
else
  rustc=/usr/bin/rustc
  [[ -x $rustc ]] || { echo "build.sh: $rustc missing: install Fedora's compiler first: sudo dnf install rust" >&2; exit 1; }
  # the compiler, its sysroot (std) and the linker must not be writable by anyone but root
  sysroot=$(env -i PATH=/usr/bin:/bin "$rustc" --print sysroot)
  for f in "$(readlink -f "$rustc")" "$sysroot/lib/rustlib" /usr/bin/cc "$(readlink -f /usr/bin/cc)" /usr/bin/ld "$(readlink -f /usr/bin/ld)"; do
    read -r owner mode <<<"$(stat -L -c '%U %a' "$f")"   # -L: a symlink's own mode is always 777
    [[ $owner == root && $(( 8#$mode & 8#022 )) == 0 ]] || { echo "build.sh: $f is not root-owned and protected ($owner $mode)" >&2; exit 1; }
  done
  [[ $(find "$sysroot/lib/rustlib" ! -user root -print -quit) == "" ]] || { echo "build.sh: non-root files in $sysroot/lib/rustlib" >&2; exit 1; }
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
if readelf -d "$tmp/lcu-panel-grab" | rg -q 'RPATH|RUNPATH'; then echo "build.sh: binary has an RPATH/RUNPATH" >&2; exit 1; fi
install -D -m 0755 "$tmp/lcu-panel-grab" "$out"
echo "$out $(sha256sum "$out" | cut -d' ' -f1) ($("$rustc" --version 2>/dev/null))"
