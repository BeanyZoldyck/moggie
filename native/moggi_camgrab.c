/*
 * moggi_camgrab.c - QNX CamAPI viewfinder frame grabber for Moggie (RPi5 / IMX708).
 *
 * Requires the sensor service to be running with the external-platform hardware
 * capture path enabled (sensor ... -b external ... camera_module3.conf).  The
 * camera delivers NV12 frames via the viewfinder callback (CREATEWINDOW=0, so
 * no Screen window is needed - works headless).
 *
 *   diagnostic mode (default): print caps + per-frame info to stderr
 *   stream mode ("stream"):    write framed NV12 to stdout for the Python bridge
 *
 * Stream protocol (little-endian), repeated per frame:
 *   magic "MGF1" (4) | uint32 width | uint32 height | uint32 datalen
 *   then <datalen> bytes tightly-packed NV12 (Y plane, then interleaved UV)
 *
 * Build (on device):  gcc moggi_camgrab.c -o moggi_camgrab -lcamapi
 * Usage:  moggi_camgrab [stream] [width] [height] [unit]
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <signal.h>
#include <inttypes.h>
#include <camera/camera_api.h>

static volatile sig_atomic_t g_stop = 0;
static long g_frames = 0;
static int  g_stream = 0;
static uint32_t g_decim = 1;        /* integer downscale factor for stream mode */
static uint8_t  g_line[8192];       /* scratch row buffer for decimation */

static void on_signal(int s) { (void)s; g_stop = 1; }

static const char *fmt_name(camera_frametype_t t) {
    switch (t) {
        case CAMERA_FRAMETYPE_NV12: return "NV12";
        case CAMERA_FRAMETYPE_RGB888: return "RGB888";
        case CAMERA_FRAMETYPE_YCBYCR: return "YCBYCR";
        case CAMERA_FRAMETYPE_GRAY8: return "GRAY8";
        default: return "other";
    }
}

static void status_cb(camera_handle_t h, camera_devstatus_t st,
                      uint16_t extra, void *arg) {
    (void)h; (void)arg;
    if (g_frames < 5) fprintf(stderr, "[status] devstatus=%d extra=%u\n", (int)st, extra);
}

static void vf_cb(camera_handle_t h, camera_buffer_t *buf, void *arg) {
    (void)h; (void)arg;
    if (!buf) return;
    if (buf->frametype != CAMERA_FRAMETYPE_NV12) {
        if (g_frames < 3)
            fprintf(stderr, "[frame] non-NV12 frametype=%d (%s)\n",
                    buf->frametype, fmt_name(buf->frametype));
        g_frames++;
        return;
    }
    camera_frame_nv12_t *d = &buf->framedesc.nv12;
    g_frames++;
    if (g_stream) {
        uint32_t f = g_decim ? g_decim : 1;
        /* output dims (kept even for NV12 chroma) */
        uint32_t ow = (d->width / f) & ~1u;
        uint32_t oh = (d->height / f) & ~1u;
        uint32_t datalen = ow * oh + ow * (oh / 2);
        uint8_t hdr[16];
        memcpy(hdr, "MGF1", 4);
        memcpy(hdr + 4, &ow, 4);
        memcpy(hdr + 8, &oh, 4);
        memcpy(hdr + 12, &datalen, 4);
        fwrite(hdr, 1, 16, stdout);
        uint8_t *base = buf->framebuf;
        uint32_t oy, ox;
        if (f == 1) {
            for (oy = 0; oy < oh; oy++)
                fwrite(base + (size_t)oy * d->stride, 1, ow, stdout);
            uint8_t *uv = base + d->uv_offset;
            for (oy = 0; oy < oh / 2; oy++)
                fwrite(uv + (size_t)oy * d->uv_stride, 1, ow, stdout);
        } else {
            /* Y plane: sample every f-th row/column */
            for (oy = 0; oy < oh; oy++) {
                uint8_t *srow = base + (size_t)(oy * f) * d->stride;
                for (ox = 0; ox < ow; ox++) g_line[ox] = srow[ox * f];
                fwrite(g_line, 1, ow, stdout);
            }
            /* UV plane: interleaved U,V pairs; decimate in pair units */
            uint8_t *uv = base + d->uv_offset;
            uint32_t opairs = ow / 2;
            for (oy = 0; oy < oh / 2; oy++) {
                uint8_t *srow = uv + (size_t)(oy * f) * d->uv_stride;
                for (ox = 0; ox < opairs; ox++) {
                    g_line[ox * 2]     = srow[(ox * f) * 2];
                    g_line[ox * 2 + 1] = srow[(ox * f) * 2 + 1];
                }
                fwrite(g_line, 1, ow, stdout);
            }
        }
        fflush(stdout);
    } else if (g_frames <= 3 || (g_frames % 30) == 0) {
        fprintf(stderr, "[frame %ld] %ux%u stride=%u uv_off=%lld uv_stride=%lld\n",
            g_frames, d->width, d->height, d->stride,
            (long long)d->uv_offset, (long long)d->uv_stride);
    }
}

int main(int argc, char **argv) {
    if (argc > 1 && strcmp(argv[1], "stream") == 0) g_stream = 1;
    if (argc > 2) g_decim = (uint32_t)atoi(argv[2]);
    camera_unit_t unit = CAMERA_UNIT_1;
    if (argc > 3) unit = (camera_unit_t)atoi(argv[3]);

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    signal(SIGPIPE, on_signal);

    /* Follow QNX's headless example camera-dump-frame-no-screen exactly:
     * open RO, QUERY the format (do NOT set vf properties or query supported
     * lists - the external_camera plugin doesn't implement those and returns
     * ENOTTY), then start the viewfinder with a frame callback. */
    camera_handle_t handle = CAMERA_HANDLE_INVALID;
    camera_error_t err = camera_open(unit, CAMERA_MODE_RO, &handle);
    fprintf(stderr, "camera_open(unit=%d,RO) -> err=%d handle=%d\n", (int)unit, err, handle);
    if (err != CAMERA_EOK) return 2;

    camera_frametype_t ft = CAMERA_FRAMETYPE_UNSPECIFIED;
    err = camera_get_vf_property(handle, CAMERA_IMGPROP_FORMAT, &ft);
    fprintf(stderr, "get_vf_property(FORMAT) -> err=%d frametype=%d(%s)\n",
            err, ft, fmt_name(ft));

    err = camera_start_viewfinder(handle, vf_cb, status_cb, NULL);
    fprintf(stderr, "start_viewfinder() -> err=%d\n", err);
    if (err != CAMERA_EOK) { camera_close(handle); return 4; }

    fprintf(stderr, "running (stream=%d)...\n", g_stream);
    long max_frames = g_stream ? 0 : 60;
    while (!g_stop) { usleep(50 * 1000); if (max_frames && g_frames >= max_frames) break; }

    fprintf(stderr, "stopping after %ld frames\n", g_frames);
    camera_stop_viewfinder(handle);
    camera_close(handle);
    return 0;
}
