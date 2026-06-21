# Mog Mirror — "Mog Avatar" mode (fal.ai Pika v2.2 image-to-video)

This document covers the Mog Avatar feature added to **Mog Mirror**: how to configure it,
run it, and how it works internally, plus the exact files that changed.

## What it does

When Pika is enabled, the Mog Mirror round is reordered:

1. At the **start** of the round (SPACE with both faces locked), a photo of each player is captured.
2. Each photo is sent to **fal.ai `fal-ai/pika/v2.2/image-to-video`** with a prompt that "mogs"
   the player (perfect jawline, hunter eyes, ideal facial thirds).
3. While the two clips render, the screen **dims** and shows **"LOADING MOG AVATAR"**.
4. Once both clips are ready, the normal 10-second scoring round runs — but the UI **shows the
   generated avatar videos instead of the camera**, and the MOG SCORE is computed from the
   **face detected in the generated video**.

If Pika is disabled, Mog Mirror behaves exactly as before (live-camera scoring).

## Setup

Config lives in `.env` (gitignored — never commit the key). The relevant keys:

```bash
MOGGIE_ENABLE_PIKA=true                              # turns the avatar flow on
MOGGIE_PIKA_PROVIDER=fal                             # use the fal.ai queue API (not the MCP provider)
FAL_KEY=<your-fal-key>                               # format: <id>:<secret>
MOGGIE_PIKA_MODEL=fal-ai/pika/v2.2/image-to-video    # the image-to-video model
MOGGIE_AI_TIMEOUT_SECONDS=120                         # image-to-video is slow; 45s default is too low
MOGGIE_AI_POLL_INTERVAL_SECONDS=3
```

Install dependencies (pygame / opencv / mediapipe) into the project environment:

```bash
python3 -m pip install -e ".[dev]"
```

## Run

```bash
# 1) Validate the fal.ai key + model without a camera (spends a small amount of credits):
python3 scripts/smoke_test_pika.py

# 2) Launch the app and play Mog Mirror:
python3 -m app.main
```

In the app: **Mog Mirror → center both faces → SPACE.** Expect:
capture → dimmed **LOADING MOG AVATAR** → both mog videos play in the P1/P2 panes →
10s scoring on the generated faces → score reveal showing the avatar frame.

## Fallback behaviour

The round never gets stuck. It falls back to the **live camera** for the whole round if:

- any avatar job **fails** or **times out**, or
- the generation **deadline** passes (`MOGGIE_AI_TIMEOUT_SECONDS` × number of lanes + 15s buffer —
  the two jobs run sequentially through the single AI worker), or
- no job could be submitted (e.g. empty capture).

To exercise the fallback manually, set `MOGGIE_AI_TIMEOUT_SECONDS=1` (or an invalid `FAL_KEY`).

## How it works (internals)

### Phase model (`app/ui/screens/mog_mirror_screen.py`)

`READY → GENERATING → SCORING`

- **READY** — faces come from `cv_service` (camera), as before.
- **SPACE** (`_capture_and_request_avatars`) — snapshots the camera, crops each lane
  (`crop_upper_body`), caches the crop + camera face as a fallback, and submits one
  `mog_mirror.avatar_video` job per lane carrying `image_bytes`, `MOG_AVATAR_PROMPT`, and
  `MOG_AVATAR_NEGATIVE_PROMPT`. Enters GENERATING.
- **GENERATING** — `handle_app_event` listens for `EVENT_AI_JOB_UPDATE`. On a job's `succeeded`
  it pulls the video URL and downloads the clip off-thread; on `failed`/`timed_out` it marks the
  lane failed. `update()` drains finished downloads into `LoopingVideoPlayer`s; when both lanes
  are ready it starts SCORING, otherwise falls back on failure/deadline.
- **SCORING** — each tick advances the players, runs a **screen-owned** `FaceDetectionService`
  on the current video frame per lane to build `lane.face` (falling back to the cached photo
  face if a frame isn't detectable), then the existing `score_aura` scoring runs unchanged. The
  display composites the two players' frames side-by-side and feeds them into the existing
  `CameraPreviewRenderer`. After 10s, `_finish_round` reuses the avatar frame for the reveal
  portrait and the avatar job id for the reveal — it does **not** spend a second generation.

### Key design decisions

- **Base64 data URIs, not uploads.** fal's image-to-video needs an `image_url`. Rather than host
  the capture somewhere, `FalPikaClient.generate_video_from_image` inlines the JPEG bytes as a
  `data:image/jpeg;base64,…` URI. (The live smoke test confirmed why: fal returns
  `422 file_download_error` when it can't fetch a passed-in URL — inlining sidesteps that.)
- **Screen-owned face detector.** mediapipe FaceMesh is not thread-safe, so the screen uses its
  own `FaceDetectionService` instance for video-frame detection rather than sharing
  `cv_service`'s instance (which runs on a worker thread).
- **No double spend.** The avatar generated at the start is reused for the score reveal.

## Files changed

| File | Change |
|------|--------|
| `.env` (gitignored) | Enable Pika via fal, key, v2.2 model, 120s timeout |
| `.env.example` | Documents `MOGGIE_PIKA_PROVIDER` and the v2.2 / timeout guidance (no secret) |
| `app/ai/fal_pika_client.py` | New `generate_video_from_image` (base64 data URI → `generate_video`); also fixes the latent FAL victory-video path that couldn't run from raw bytes |
| `app/util/video_playback.py` (new) | `download_to_tempfile` / `download_in_background` + `LoopingVideoPlayer` |
| `app/games/mog_mirror.py` | `MOG_AVATAR_PROMPT` and `MOG_AVATAR_NEGATIVE_PROMPT` constants |
| `app/ui/screens/mog_mirror_screen.py` | Phase model, capture-at-start, avatar job submission, loading overlay, video-frame scoring, side-by-side composite, camera fallback |
| `tests/test_fal_pika_client.py` | Data-URI path + requires-bytes cases |
| `tests/test_mog_mirror.py` | Avatar-flow cases: capture/submit, both-ready→scoring, failure & deadline→fallback, event-ignored guard |

## Tests

All mocked — no network or camera required:

```bash
python3 -m unittest tests.test_mog_mirror tests.test_fal_pika_client -v
```

> Note: `tests/test_sixseven_rendering.py` fails to import on a stale `ui.` module path. This is
> pre-existing and unrelated to this feature.

## Known limitations / notes

- **Latency.** Image-to-video takes tens of seconds per clip and the two jobs run sequentially,
  so the loading screen can persist for a while with two players. The deadline + camera fallback
  bound the wait.
- **Score-reveal label.** Because avatar jobs succeed *while* the Mog Mirror screen is active, the
  reveal screen may briefly show "AI MEDIA RUNNING" — cosmetic only; the avatar frame is still
  shown as the portrait.
- **Generated-face detection** can intermittently miss; the cached start-photo face keeps scoring
  stable when that happens.
