/* lcu-panel-grab: hand out the buffer a monitor is really showing (its scanout buffer).
 *
 * Screen recorders get frames the compositor renders for them, which can differ from what
 * reaches the panel (stale regions when an app under-reports damage). The kernel gives out
 * the real scanout buffer only to a process with CAP_SYS_ADMIN, so this helper is installed
 * once by root with that one file capability (scripts/panel/setup.sh). It runs no other
 * program and reads no files; all decoding happens in the unprivileged caller.
 *
 *   lcu-panel-grab version                 protocol version (a number)
 *   lcu-panel-grab list                    connected monitors: NAME CARD CRTC_ID WIDTH HEIGHT
 *   lcu-panel-grab serve CARD FD           FD = an inherited AF_UNIX SOCK_SEQPACKET socket.
 *       Each request is one uint32 CRTC id. Each reply is a struct reply (below) and, when
 *       status is 0, one dma-buf file descriptor per plane of the framebuffer that CRTC is
 *       scanning out right now (SCM_RIGHTS). Ends when the socket closes.
 *
 * Build: gcc -O2 -Wall -Wextra -o lcu-panel-grab lcu-panel-grab.c      (kernel headers only)
 */
#define _GNU_SOURCE
#include <drm/drm.h>
#include <drm/drm_mode.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

#define VERSION 2

struct reply {
    uint32_t status; /* 0 = ok, else an errno value */
    uint32_t fb_id;  /* changes when the compositor flips to another buffer */
    uint32_t width, height;
    uint32_t fourcc; /* DRM_FORMAT_* */
    uint32_t planes; /* number of file descriptors attached */
    uint32_t pitches[4], offsets[4];
    uint64_t modifier;
};

static const char *const TYPES[] = {"Unknown", "VGA", "DVI-I", "DVI-D", "DVI-A", "Composite", "SVIDEO", "LVDS",
                                    "Component", "DIN", "DP", "HDMI-A", "HDMI-B", "TV", "eDP", "Virtual", "DSI",
                                    "DPI", "Writeback", "SPI", "USB"};

static int open_card(long card) {
    char path[32];
    snprintf(path, sizeof path, "/dev/dri/card%ld", card);
    return open(path, O_RDWR | O_CLOEXEC);
}

static int list(void) {
    int found = 0;
    for (int card = 0; card < 8; card++) {
        int fd = open_card(card);
        if (fd < 0) continue;
        struct drm_mode_card_res res = {0};
        if (ioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &res) || !res.count_connectors) { close(fd); continue; }
        uint32_t n = res.count_connectors, *ids = calloc(n, sizeof *ids);
        struct drm_mode_card_res res2 = {.connector_id_ptr = (uintptr_t)ids, .count_connectors = n};
        if (!ids || ioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &res2)) { free(ids); close(fd); continue; }
        if (res2.count_connectors < n) n = res2.count_connectors;
        for (uint32_t i = 0; i < n; i++) {
            struct drm_mode_modeinfo mode; /* count_modes = 1: never asks the kernel to re-probe the monitor */
            struct drm_mode_get_connector c = {.connector_id = ids[i], .count_modes = 1, .modes_ptr = (uintptr_t)&mode};
            if (ioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, &c) || c.connection != 1 || !c.encoder_id) continue;
            struct drm_mode_get_encoder e = {.encoder_id = c.encoder_id};
            if (ioctl(fd, DRM_IOCTL_MODE_GETENCODER, &e) || !e.crtc_id) continue;
            struct drm_mode_crtc crtc = {.crtc_id = e.crtc_id};
            if (ioctl(fd, DRM_IOCTL_MODE_GETCRTC, &crtc) || !crtc.mode_valid) continue;
            const char *type = c.connector_type < sizeof TYPES / sizeof *TYPES ? TYPES[c.connector_type] : "Unknown";
            printf("%s-%u %d %u %u %u\n", type, c.connector_type_id, card, e.crtc_id, crtc.mode.hdisplay, crtc.mode.vdisplay);
            found++;
        }
        free(ids);
        close(fd);
    }
    return found ? 0 : 1;
}

/* a plain decimal number within [lo, hi], or exit */
static long number(const char *s, long lo, long hi, const char *what) {
    char *end;
    errno = 0;
    long v = strtol(s, &end, 10);
    if (errno || end == s || *end || strspn(s, "0123456789") != strlen(s) || v < lo || v > hi) {
        fprintf(stderr, "lcu-panel-grab: %s must be a number from %ld to %ld\n", what, lo, hi);
        exit(2);
    }
    return v;
}

/* Fill r and fds[] for the largest framebuffer on `crtc` (the primary plane; the cursor's is tiny). */
static void scanout(int drm, uint32_t crtc, const uint32_t *planes, uint32_t nplanes, struct reply *r, int *fds) {
    struct drm_mode_fb_cmd2 best = {0};
    for (uint32_t i = 0; i < nplanes; i++) {
        struct drm_mode_get_plane p = {.plane_id = planes[i]};
        if (ioctl(drm, DRM_IOCTL_MODE_GETPLANE, &p) || p.crtc_id != crtc || !p.fb_id) continue;
        struct drm_mode_fb_cmd2 fb = {.fb_id = p.fb_id};
        if (ioctl(drm, DRM_IOCTL_MODE_GETFB2, &fb)) continue;
        if ((uint64_t)fb.width * fb.height > (uint64_t)best.width * best.height) {
            for (int k = 0; k < 4; k++) /* drop the handles of the one we are replacing */
                if (best.handles[k] && (k == 0 || best.handles[k] != best.handles[0])) {
                    struct drm_gem_close gc = {.handle = best.handles[k]};
                    ioctl(drm, DRM_IOCTL_GEM_CLOSE, &gc);
                }
            best = fb;
        } else {
            for (int k = 0; k < 4; k++)
                if (fb.handles[k] && (k == 0 || fb.handles[k] != fb.handles[0])) {
                    struct drm_gem_close gc = {.handle = fb.handles[k]};
                    ioctl(drm, DRM_IOCTL_GEM_CLOSE, &gc);
                }
        }
    }
    if (!best.fb_id) { r->status = ENOENT; return; }
    if (!best.handles[0]) { r->status = EPERM; return; } /* kernel withheld the buffer: no CAP_SYS_ADMIN */
    r->fb_id = best.fb_id;
    r->width = best.width;
    r->height = best.height;
    r->fourcc = best.pixel_format;
    r->modifier = (best.flags & DRM_MODE_FB_MODIFIERS) ? best.modifier[0] : 0x00ffffffffffffffULL; /* DRM_FORMAT_MOD_INVALID */
    for (int k = 0; k < 4 && best.handles[k]; k++) {
        struct drm_prime_handle ph = {.handle = best.handles[k], .flags = O_RDONLY | O_CLOEXEC};
        if (ioctl(drm, DRM_IOCTL_PRIME_HANDLE_TO_FD, &ph)) { r->status = errno ? errno : EIO; break; }
        fds[k] = ph.fd;
        r->pitches[k] = best.pitches[k];
        r->offsets[k] = best.offsets[k];
        r->planes = k + 1;
    }
    for (int k = 0; k < 4; k++) { /* each distinct handle once */
        int seen = 0;
        for (int j = 0; j < k; j++) seen |= best.handles[j] == best.handles[k];
        if (best.handles[k] && !seen) {
            struct drm_gem_close gc = {.handle = best.handles[k]};
            ioctl(drm, DRM_IOCTL_GEM_CLOSE, &gc);
        }
    }
    if (r->status) {
        for (uint32_t k = 0; k < r->planes; k++) close(fds[k]);
        r->planes = 0;
    }
}

static int serve(char **a) {
    long card = number(a[0], 0, 7, "CARD");
    int sock = (int)number(a[1], 3, 1023, "FD"), type = 0;
    socklen_t len = sizeof type;
    if (getsockopt(sock, SOL_SOCKET, SO_TYPE, &type, &len) || type != SOCK_SEQPACKET) {
        fprintf(stderr, "lcu-panel-grab: FD must be an inherited SOCK_SEQPACKET socket\n");
        return 2;
    }
    int drm = open_card(card);
    if (drm < 0) { perror("lcu-panel-grab: card"); return 1; }
    struct drm_set_client_cap cap = {DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1};
    ioctl(drm, DRM_IOCTL_SET_CLIENT_CAP, &cap);
    struct drm_mode_get_plane_res pr = {0};
    if (ioctl(drm, DRM_IOCTL_MODE_GETPLANERESOURCES, &pr) || !pr.count_planes) { perror("lcu-panel-grab: planes"); return 1; }
    uint32_t nplanes = pr.count_planes, *planes = calloc(nplanes, sizeof *planes);
    struct drm_mode_get_plane_res pr2 = {.plane_id_ptr = (uintptr_t)planes, .count_planes = nplanes};
    if (!planes || ioctl(drm, DRM_IOCTL_MODE_GETPLANERESOURCES, &pr2)) { perror("lcu-panel-grab: planes"); return 1; }
    if (pr2.count_planes < nplanes) nplanes = pr2.count_planes;

    for (;;) {
        uint32_t crtc;
        ssize_t got = recv(sock, &crtc, sizeof crtc, 0);
        if (got == 0) return 0;
        if (got != sizeof crtc) return 1;
        struct reply r = {0};
        int fds[4] = {-1, -1, -1, -1};
        scanout(drm, crtc, planes, nplanes, &r, fds);
        struct iovec iov = {&r, sizeof r};
        union { char buf[CMSG_SPACE(sizeof fds)]; struct cmsghdr align; } u = {{0}};
        struct msghdr msg = {.msg_iov = &iov, .msg_iovlen = 1};
        if (r.planes) {
            msg.msg_control = u.buf;
            msg.msg_controllen = CMSG_SPACE(r.planes * sizeof(int));
            struct cmsghdr *c = CMSG_FIRSTHDR(&msg);
            c->cmsg_level = SOL_SOCKET;
            c->cmsg_type = SCM_RIGHTS;
            c->cmsg_len = CMSG_LEN(r.planes * sizeof(int));
            memcpy(CMSG_DATA(c), fds, r.planes * sizeof(int));
        }
        ssize_t sent = sendmsg(sock, &msg, MSG_NOSIGNAL);
        for (uint32_t k = 0; k < r.planes; k++) close(fds[k]);
        if (sent < 0) return 0;
    }
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "version")) { printf("%d\n", VERSION); return 0; }
    if (argc == 2 && !strcmp(argv[1], "list")) return list();
    if (argc == 4 && !strcmp(argv[1], "serve")) return serve(argv + 2);
    fprintf(stderr, "usage: lcu-panel-grab version | list | serve CARD FD\n");
    return 2;
}
