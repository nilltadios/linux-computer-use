//! lcu-panel-grab: hand out the buffer a monitor is really showing (its scanout buffer).
//!
//! Screen recorders get frames the compositor renders for them, which can differ from what
//! reaches the panel (stale regions when an app under-reports damage). The kernel gives out
//! the real scanout buffer only to a process with CAP_SYS_ADMIN, so this helper is installed
//! once by root with that one file capability (scripts/panel/setup.sh). It runs no other
//! program, reads no files and no environment; it opens only /dev/dri/cardN. All decoding
//! happens in the unprivileged caller.
//!
//!   lcu-panel-grab version                 protocol version (a number)
//!   lcu-panel-grab list                    connected monitors: NAME CARD CRTC_ID WIDTH HEIGHT
//!   lcu-panel-grab serve CARD FD           FD = an inherited AF_UNIX SOCK_SEQPACKET socket.
//!       Each request is one uint32 CRTC id. Each reply is a `Reply` (below) and, when
//!       status is 0, one dma-buf file descriptor per plane of the framebuffer that CRTC is
//!       scanning out right now (SCM_RIGHTS). Ends when the socket closes.
//!
//! Std only, no crates. `#![no_main]`: the C runtime calls `main` directly, so none of Rust's
//! own start-up code runs (no signal or stack-guard setup, no /proc reads).
//! Build: scripts/panel/build.sh OUT (the one command setup.sh and the audit both use).
//! Test:  scripts/panel/build.sh --test   (layouts, number(), SCM_RIGHTS framing; no privilege)
#![cfg_attr(not(test), no_main)]
#![deny(unsafe_op_in_unsafe_fn)]

use std::ffi::{c_char, c_int, CStr};
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::os::fd::{AsRawFd, RawFd};

const VERSION: u32 = 2;

/// eprintln! panics when stderr is closed; this ignores the error like C's fprintf.
macro_rules! say { ($($t:tt)*) => {{ let _ = writeln!(std::io::stderr(), $($t)*); }} }

/// Wire format shared with scripts/panel.py (struct.Struct("<6I4I4IQ")): keep byte-identical.
#[repr(C)]
#[derive(Default)]
struct Reply {
    status: u32, // 0 = ok, else an errno value
    fb_id: u32,  // changes when the compositor flips to another buffer
    width: u32,
    height: u32,
    fourcc: u32, // DRM_FORMAT_*
    planes: u32, // number of file descriptors attached
    pitches: [u32; 4],
    offsets: [u32; 4],
    modifier: u64,
}
const _: () = assert!(std::mem::size_of::<Reply>() == 64);

const TYPES: [&str; 21] = [
    "Unknown", "VGA", "DVI-I", "DVI-D", "DVI-A", "Composite", "SVIDEO", "LVDS", "Component", "DIN", "DP",
    "HDMI-A", "HDMI-B", "TV", "eDP", "Virtual", "DSI", "DPI", "Writeback", "SPI", "USB",
];

/// Kernel ABI (uapi drm.h / drm_mode.h) and the few libc calls std does not offer.
/// Layouts and ioctl numbers were taken from this machine's headers (probe.c, 2026-11-12) and are
/// pinned by the size asserts below: a mismatch fails the build instead of misreading memory.
mod sys {
    use std::ffi::{c_char, c_int, c_ulong, c_void};

    pub const GETRESOURCES: c_ulong = 0xc040_64a0;
    pub const GETCONNECTOR: c_ulong = 0xc050_64a7;
    pub const GETENCODER: c_ulong = 0xc014_64a6;
    pub const GETCRTC: c_ulong = 0xc068_64a1;
    pub const GETPLANERESOURCES: c_ulong = 0xc010_64b5;
    pub const GETPLANE: c_ulong = 0xc020_64b6;
    pub const GETFB2: c_ulong = 0xc068_64ce;
    pub const GEM_CLOSE: c_ulong = 0x4008_6409;
    pub const PRIME_HANDLE_TO_FD: c_ulong = 0xc00c_642d;
    pub const SET_CLIENT_CAP: c_ulong = 0x4010_640d;
    pub const CLIENT_CAP_UNIVERSAL_PLANES: u64 = 2;
    pub const MODE_FB_MODIFIERS: u32 = 2;
    pub const O_RDONLY_CLOEXEC: u32 = 0x8_0000; // O_RDONLY (0) | O_CLOEXEC
    pub const ENOENT: u32 = 2;
    pub const EPERM: u32 = 1;
    pub const EIO: u32 = 5;
    const SOL_SOCKET: c_int = 1;
    const SO_TYPE: c_int = 3;
    pub const SOCK_SEQPACKET: c_int = 5;
    const SCM_RIGHTS: c_int = 1;
    const MSG_NOSIGNAL: c_int = 0x4000;

    #[repr(C)] #[derive(Default)]
    pub struct CardRes { pub fb_id_ptr: u64, pub crtc_id_ptr: u64, pub connector_id_ptr: u64, pub encoder_id_ptr: u64,
        pub count_fbs: u32, pub count_crtcs: u32, pub count_connectors: u32, pub count_encoders: u32,
        pub min_width: u32, pub max_width: u32, pub min_height: u32, pub max_height: u32 }
    #[repr(C)] #[derive(Default, Clone, Copy)]
    pub struct ModeInfo { pub clock: u32, pub hdisplay: u16, pub hsync_start: u16, pub hsync_end: u16, pub htotal: u16,
        pub hskew: u16, pub vdisplay: u16, pub vsync_start: u16, pub vsync_end: u16, pub vtotal: u16, pub vscan: u16,
        pub vrefresh: u32, pub flags: u32, pub type_: u32, pub name: [u8; 32] }
    #[repr(C)] #[derive(Default)]
    pub struct GetConnector { pub encoders_ptr: u64, pub modes_ptr: u64, pub props_ptr: u64, pub prop_values_ptr: u64,
        pub count_modes: u32, pub count_props: u32, pub count_encoders: u32, pub encoder_id: u32, pub connector_id: u32,
        pub connector_type: u32, pub connector_type_id: u32, pub connection: u32, pub mm_width: u32, pub mm_height: u32,
        pub subpixel: u32, pub pad: u32 }
    #[repr(C)] #[derive(Default)]
    pub struct GetEncoder { pub encoder_id: u32, pub encoder_type: u32, pub crtc_id: u32, pub possible_crtcs: u32,
        pub possible_clones: u32 }
    #[repr(C)] #[derive(Default)]
    pub struct Crtc { pub set_connectors_ptr: u64, pub count_connectors: u32, pub crtc_id: u32, pub fb_id: u32,
        pub x: u32, pub y: u32, pub gamma_size: u32, pub mode_valid: u32, pub mode: ModeInfo }
    #[repr(C)] #[derive(Default)]
    pub struct PlaneRes { pub plane_id_ptr: u64, pub count_planes: u32 }
    #[repr(C)] #[derive(Default)]
    pub struct GetPlane { pub plane_id: u32, pub crtc_id: u32, pub fb_id: u32, pub possible_crtcs: u32,
        pub gamma_size: u32, pub count_format_types: u32, pub format_type_ptr: u64 }
    #[repr(C)] #[derive(Default, Clone, Copy)]
    pub struct FbCmd2 { pub fb_id: u32, pub width: u32, pub height: u32, pub pixel_format: u32, pub flags: u32,
        pub handles: [u32; 4], pub pitches: [u32; 4], pub offsets: [u32; 4], pub modifier: [u64; 4] }
    #[repr(C)] #[derive(Default)]
    pub struct GemClose { pub handle: u32, pub pad: u32 }
    #[repr(C)] #[derive(Default)]
    pub struct PrimeHandle { pub handle: u32, pub flags: u32, pub fd: i32 }
    #[repr(C)] #[derive(Default)]
    pub struct ClientCap { pub capability: u64, pub value: u64 }

    const _: () = {
        use std::mem::{offset_of, size_of};
        assert!(size_of::<CardRes>() == 64 && offset_of!(CardRes, count_connectors) == 40);
        assert!(size_of::<ModeInfo>() == 68 && offset_of!(ModeInfo, vdisplay) == 14);
        assert!(size_of::<GetConnector>() == 80 && offset_of!(GetConnector, connection) == 60);
        assert!(size_of::<GetEncoder>() == 20 && offset_of!(GetEncoder, crtc_id) == 8);
        assert!(size_of::<Crtc>() == 104 && offset_of!(Crtc, mode_valid) == 32 && offset_of!(Crtc, mode) == 36);
        assert!(size_of::<PlaneRes>() == 16 && offset_of!(PlaneRes, count_planes) == 8);
        assert!(size_of::<GetPlane>() == 32 && offset_of!(GetPlane, fb_id) == 8);
        assert!(size_of::<FbCmd2>() == 104 && offset_of!(FbCmd2, handles) == 20 && offset_of!(FbCmd2, modifier) == 72);
        assert!(size_of::<GemClose>() == 8 && size_of::<PrimeHandle>() == 12 && size_of::<ClientCap>() == 16);
    };

    #[repr(C)]
    struct IoVec { base: *mut c_void, len: usize }
    #[repr(C)]
    struct MsgHdr { name: *mut c_void, namelen: u32, iov: *mut IoVec, iovlen: usize, control: *mut c_void,
        controllen: usize, flags: c_int }
    #[repr(C)]
    struct CmsgHdr { len: usize, level: c_int, type_: c_int }
    const _: () = assert!(std::mem::size_of::<MsgHdr>() == 56 && std::mem::size_of::<CmsgHdr>() == 16);

    unsafe extern "C" {
        fn ioctl(fd: c_int, request: c_ulong, ...) -> c_int;
        fn getsockopt(fd: c_int, level: c_int, name: c_int, val: *mut c_void, len: *mut u32) -> c_int;
        fn recv(fd: c_int, buf: *mut c_void, len: usize, flags: c_int) -> isize;
        fn sendmsg(fd: c_int, msg: *const MsgHdr, flags: c_int) -> isize;
        fn close(fd: c_int) -> c_int;
        pub fn strerror(errnum: c_int) -> *const c_char;
    }

    pub fn errno() -> u32 {
        std::io::Error::last_os_error().raw_os_error().unwrap_or(0) as u32
    }

    /// One DRM ioctl on a plain-old-data argument; Err(errno) on failure.
    pub fn drm<T>(fd: c_int, request: c_ulong, arg: &mut T) -> Result<(), u32> {
        // SAFETY: every `request` above pairs with the argument type its callers pass, and the
        // asserts pin each type to the kernel's size, which is also encoded in the request number.
        if unsafe { ioctl(fd, request, arg as *mut T) } == 0 { Ok(()) } else { Err(errno()) }
    }

    pub fn socket_type(fd: c_int) -> Option<c_int> {
        let (mut t, mut len): (c_int, u32) = (0, 4);
        // SAFETY: t and len are valid for writes of the sizes given.
        let r = unsafe { getsockopt(fd, SOL_SOCKET, SO_TYPE, (&raw mut t).cast(), &mut len) };
        (r == 0).then_some(t)
    }

    /// recv() of one u32 request: Some(Ok(v)), Some(Err) on a short or failed read, None on EOF.
    pub fn recv_u32(fd: c_int) -> Option<Result<u32, ()>> {
        let mut v: u32 = 0;
        // SAFETY: v is valid for 4 bytes of writes.
        let got = unsafe { recv(fd, (&raw mut v).cast(), 4, 0) };
        match got { 0 => None, 4 => Some(Ok(v)), _ => Some(Err(())) }
    }

    /// sendmsg() of `data` with `fds` (at most 4) as SCM_RIGHTS; false when the peer is gone.
    pub fn send_with_fds(fd: c_int, data: &[u8], fds: &[c_int]) -> bool {
        // control buffer: CMSG_SPACE(4 * sizeof(int)) = 16 + 16, 8-aligned
        let mut ctl = [0u64; 4];
        let mut iov = IoVec { base: data.as_ptr() as *mut c_void, len: data.len() };
        let mut msg = MsgHdr { name: std::ptr::null_mut(), namelen: 0, iov: &mut iov, iovlen: 1,
            control: std::ptr::null_mut(), controllen: 0, flags: 0 };
        let n = fds.len().min(4);
        if n > 0 {
            let bytes = n * 4;
            let hdr = CmsgHdr { len: 16 + bytes, level: SOL_SOCKET, type_: SCM_RIGHTS }; // CMSG_LEN
            // SAFETY: ctl is 32 bytes and 8-aligned; the header takes 16 and the fds at most 16 after it.
            unsafe {
                let base = ctl.as_mut_ptr().cast::<u8>();
                std::ptr::write(base.cast::<CmsgHdr>(), hdr);
                std::ptr::copy_nonoverlapping(fds.as_ptr().cast::<u8>(), base.add(16), bytes);
            }
            msg.control = ctl.as_mut_ptr().cast();
            msg.controllen = 16 + bytes.div_ceil(8) * 8; // CMSG_SPACE
        }
        // SAFETY: msg points at live iov/data/ctl for the duration of the call.
        unsafe { sendmsg(fd, &msg, MSG_NOSIGNAL) >= 0 }
    }

    pub fn close_fd(fd: c_int) {
        // SAFETY: closes a descriptor this process owns (exported dma-buf).
        unsafe { close(fd) };
    }
}

fn open_card(card: u32) -> std::io::Result<File> {
    OpenOptions::new().read(true).write(true).open(format!("/dev/dri/card{card}")) // std adds O_CLOEXEC
}

fn strerror(e: u32) -> String {
    // SAFETY: strerror returns a valid NUL-terminated string for any errnum.
    unsafe { CStr::from_ptr(sys::strerror(e as c_int)) }.to_string_lossy().into_owned()
}

fn list() -> i32 {
    let mut out = std::io::stdout().lock();
    let mut found = 0;
    for card in 0..8 {
        let Ok(f) = open_card(card) else { continue };
        let fd = f.as_raw_fd();
        let mut res = sys::CardRes::default();
        if sys::drm(fd, sys::GETRESOURCES, &mut res).is_err() || res.count_connectors == 0 { continue; }
        let mut ids = vec![0u32; res.count_connectors as usize];
        let mut res2 = sys::CardRes { connector_id_ptr: ids.as_mut_ptr() as u64, count_connectors: res.count_connectors,
            ..Default::default() };
        if sys::drm(fd, sys::GETRESOURCES, &mut res2).is_err() { continue; }
        let n = (res2.count_connectors as usize).min(ids.len());
        for &id in &ids[..n] {
            let mut mode = sys::ModeInfo::default(); // count_modes = 1: never asks the kernel to re-probe the monitor
            let mut c = sys::GetConnector { connector_id: id, count_modes: 1, modes_ptr: (&raw mut mode) as u64,
                ..Default::default() };
            if sys::drm(fd, sys::GETCONNECTOR, &mut c).is_err() || c.connection != 1 || c.encoder_id == 0 { continue; }
            let mut e = sys::GetEncoder { encoder_id: c.encoder_id, ..Default::default() };
            if sys::drm(fd, sys::GETENCODER, &mut e).is_err() || e.crtc_id == 0 { continue; }
            let mut crtc = sys::Crtc { crtc_id: e.crtc_id, ..Default::default() };
            if sys::drm(fd, sys::GETCRTC, &mut crtc).is_err() || crtc.mode_valid == 0 { continue; }
            let ty = TYPES.get(c.connector_type as usize).copied().unwrap_or("Unknown");
            let _ = writeln!(out, "{}-{} {} {} {} {}", ty, c.connector_type_id, card, e.crtc_id,
                crtc.mode.hdisplay, crtc.mode.vdisplay);
            found += 1;
        }
    }
    let _ = out.flush();
    if found > 0 { 0 } else { 1 }
}

/// A plain decimal number within [lo, hi], or exit 2 (same rule as the C version: digits only).
fn number(s: &[u8], lo: i64, hi: i64, what: &str) -> i64 {
    let ok = !s.is_empty() && s.iter().all(u8::is_ascii_digit);
    match std::str::from_utf8(s).ok().filter(|_| ok).and_then(|t| t.parse::<i64>().ok()) {
        Some(v) if (lo..=hi).contains(&v) => v,
        _ => {
            say!("lcu-panel-grab: {what} must be a number from {lo} to {hi}");
            std::process::exit(2);
        }
    }
}

/// GEM_CLOSE each handle of `fb` that `keep(k)` selects.
fn gem_close(drm: RawFd, fb: &sys::FbCmd2, keep: impl Fn(usize) -> bool) {
    for k in 0..4 {
        if fb.handles[k] != 0 && keep(k) {
            let _ = sys::drm(drm, sys::GEM_CLOSE, &mut sys::GemClose { handle: fb.handles[k], pad: 0 });
        }
    }
}

/// Fill r and fds for the largest framebuffer on `crtc` (the primary plane; the cursor's is tiny).
fn scanout(drm: RawFd, crtc: u32, planes: &[u32], r: &mut Reply, fds: &mut Vec<c_int>) {
    let mut best = sys::FbCmd2::default();
    for &plane in planes {
        let mut p = sys::GetPlane { plane_id: plane, ..Default::default() };
        if sys::drm(drm, sys::GETPLANE, &mut p).is_err() || p.crtc_id != crtc || p.fb_id == 0 { continue; }
        let mut fb = sys::FbCmd2 { fb_id: p.fb_id, ..Default::default() };
        if sys::drm(drm, sys::GETFB2, &mut fb).is_err() { continue; }
        // drop the handles of whichever of the two we do not keep
        let loser = if fb.width as u64 * fb.height as u64 > best.width as u64 * best.height as u64 {
            std::mem::replace(&mut best, fb)
        } else { fb };
        gem_close(drm, &loser, |k| k == 0 || loser.handles[k] != loser.handles[0]);
    }
    if best.fb_id == 0 { r.status = sys::ENOENT; return; }
    if best.handles[0] == 0 { r.status = sys::EPERM; return; } // kernel withheld the buffer: no CAP_SYS_ADMIN
    r.fb_id = best.fb_id;
    r.width = best.width;
    r.height = best.height;
    r.fourcc = best.pixel_format;
    r.modifier = if best.flags & sys::MODE_FB_MODIFIERS != 0 { best.modifier[0] } else { 0x00ff_ffff_ffff_ffff }; // DRM_FORMAT_MOD_INVALID
    for k in 0..4 {
        if best.handles[k] == 0 { break; }
        let mut ph = sys::PrimeHandle { handle: best.handles[k], flags: sys::O_RDONLY_CLOEXEC, fd: -1 };
        if let Err(e) = sys::drm(drm, sys::PRIME_HANDLE_TO_FD, &mut ph) {
            r.status = if e != 0 { e } else { sys::EIO };
            break;
        }
        fds.push(ph.fd);
        r.pitches[k] = best.pitches[k];
        r.offsets[k] = best.offsets[k];
        r.planes = k as u32 + 1;
    }
    gem_close(drm, &best, |k| !best.handles[..k].contains(&best.handles[k])); // each distinct handle once
    if r.status != 0 {
        fds.drain(..).for_each(sys::close_fd);
        r.planes = 0;
    }
}

fn serve(card_arg: &[u8], fd_arg: &[u8]) -> i32 {
    let card = number(card_arg, 0, 7, "CARD") as u32;
    let sock = number(fd_arg, 3, 1023, "FD") as c_int;
    if sys::socket_type(sock) != Some(sys::SOCK_SEQPACKET) {
        say!("lcu-panel-grab: FD must be an inherited SOCK_SEQPACKET socket");
        return 2;
    }
    let file = match open_card(card) {
        Ok(f) => f,
        Err(e) => { say!("lcu-panel-grab: card: {}", strerror(e.raw_os_error().unwrap_or(0) as u32)); return 1; }
    };
    let drm = file.as_raw_fd();
    let _ = sys::drm(drm, sys::SET_CLIENT_CAP, &mut sys::ClientCap { capability: sys::CLIENT_CAP_UNIVERSAL_PLANES, value: 1 });
    let mut pr = sys::PlaneRes::default();
    if let Err(e) = sys::drm(drm, sys::GETPLANERESOURCES, &mut pr).and_then(|_| if pr.count_planes == 0 { Err(0) } else { Ok(()) }) {
        say!("lcu-panel-grab: planes: {}", strerror(e)); return 1;
    }
    let mut planes = vec![0u32; pr.count_planes as usize];
    let mut pr2 = sys::PlaneRes { plane_id_ptr: planes.as_mut_ptr() as u64, count_planes: pr.count_planes };
    if let Err(e) = sys::drm(drm, sys::GETPLANERESOURCES, &mut pr2) { say!("lcu-panel-grab: planes: {}", strerror(e)); return 1; }
    planes.truncate(pr2.count_planes as usize);

    loop {
        let crtc = match sys::recv_u32(sock) { None => return 0, Some(Err(())) => return 1, Some(Ok(v)) => v };
        let mut r = Reply::default();
        let mut fds = Vec::with_capacity(4);
        scanout(drm, crtc, &planes, &mut r, &mut fds);
        // SAFETY: Reply is repr(C) plain old data without padding (6+4+4 u32 then a u64 at offset 56).
        let bytes = unsafe { std::slice::from_raw_parts((&raw const r).cast::<u8>(), std::mem::size_of::<Reply>()) };
        let sent = sys::send_with_fds(sock, bytes, &fds);
        fds.into_iter().for_each(sys::close_fd);
        if !sent { return 0; }
    }
}

#[cfg(not(test))]
#[unsafe(no_mangle)]
pub extern "C" fn main(argc: c_int, argv: *const *const c_char) -> c_int {
    let args: Vec<&[u8]> = (0..argc.max(0) as usize)
        // SAFETY: the C runtime passes argc valid NUL-terminated strings in argv.
        .map(|i| unsafe { CStr::from_ptr(*argv.add(i)) }.to_bytes())
        .collect();
    match args.as_slice() {
        [_, b"version"] => { let _ = writeln!(std::io::stdout(), "{VERSION}"); 0 }
        [_, b"list"] => list(),
        [_, b"serve", card, fd] => serve(card, fd),
        _ => { say!("usage: lcu-panel-grab version | list | serve CARD FD"); 2 }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::fd::IntoRawFd;
    use std::os::unix::fs::MetadataExt;
    use std::os::unix::net::UnixDatagram;

    unsafe extern "C" {
        fn recvmsg(fd: c_int, msg: *mut RecvHdr, flags: c_int) -> isize;
        fn fstat(fd: c_int, st: *mut [u64; 18]) -> c_int;
    }
    #[repr(C)]
    struct Iov { base: *mut u8, len: usize }
    #[repr(C)]
    struct RecvHdr { name: *mut u8, namelen: u32, iov: *mut Iov, iovlen: usize, control: *mut u8, controllen: usize, flags: c_int }

    fn roundtrip(n: usize) -> (Vec<u8>, Vec<c_int>) {
        let (a, b) = UnixDatagram::pair().unwrap();
        let fds: Vec<c_int> = (0..n).map(|_| File::open("/dev/null").unwrap().into_raw_fd()).collect();
        let payload: Vec<u8> = (0..64u8).collect();
        assert!(sys::send_with_fds(a.as_raw_fd(), &payload, &fds));
        fds.iter().for_each(|&f| sys::close_fd(f));
        let (mut buf, mut ctl) = ([0u8; 128], [0u64; 16]);
        let mut iov = Iov { base: buf.as_mut_ptr(), len: buf.len() };
        let mut m = RecvHdr { name: std::ptr::null_mut(), namelen: 0, iov: &mut iov, iovlen: 1,
            control: ctl.as_mut_ptr().cast(), controllen: 128, flags: 0 };
        let got = unsafe { recvmsg(b.as_raw_fd(), &mut m, 0) };
        assert_eq!(got, 64);
        let mut out = Vec::new();
        if m.controllen > 0 {
            let len = ctl[0] as usize; // cmsg_len
            let (level, ty) = (ctl[1] as u32 as c_int, (ctl[1] >> 32) as u32 as c_int);
            assert_eq!((level, ty), (1, 1), "SOL_SOCKET / SCM_RIGHTS");
            assert_eq!(len, 16 + 4 * n, "CMSG_LEN");
            let base = unsafe { ctl.as_ptr().cast::<u8>().add(16) };
            for i in 0..n { out.push(unsafe { std::ptr::read_unaligned(base.add(4 * i).cast::<c_int>()) }); }
        }
        (buf[..64].to_vec(), out)
    }

    #[test]
    fn fds_arrive_and_are_dev_null() {
        let null_rdev = std::fs::metadata("/dev/null").unwrap().rdev();
        for n in 0..=4 {
            let (data, fds) = roundtrip(n);
            assert_eq!(data, (0..64u8).collect::<Vec<_>>());
            assert_eq!(fds.len(), n);
            for f in fds {
                let mut st = [0u64; 18];
                assert_eq!(unsafe { fstat(f, &mut st) }, 0);
                assert_eq!(st[5], null_rdev, "st_rdev of passed fd"); // x86_64 struct stat: st_rdev at word 5
                sys::close_fd(f);
            }
        }
    }

    #[test]
    fn reply_layout_matches_panel_py() {
        // struct.Struct("6I4I4IQ"): 14 u32 then a u64 at 56
        assert_eq!(std::mem::offset_of!(Reply, pitches), 24);
        assert_eq!(std::mem::offset_of!(Reply, offsets), 40);
        assert_eq!(std::mem::offset_of!(Reply, modifier), 56);
    }
}
