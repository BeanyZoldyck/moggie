# Mog Mirror — opt-in AI replay (fal.ai Pika v2.2 image-to-video)

This document covers the optional AI **replay** added to **Mog Mirror**: how to configure it,
run it, and how it works internally, plus the exact files that changed.

## What it does

Mog Mirror plays exactly as before — a live-camera 10-second mog-off. After the round, on the
**score-reveal screen**, the player can **opt in** to generate a single cinematic *replay* video
of the battle:

1. The battle runs normally on the live camera; the result (scores, winner) is computed.
2. On the score-reveal screen a prompt appears: **`G — GENERATE AI REPLAY`**.
3. Pressing **G** sends **one** image — a single frame spanning **both sides** of the camera
   (P1 left, P2 right) — to **fal.ai `fal-ai/pika/v2.2/image-to-video`** with a **result-aware
   prompt** ("…{winner} wins with a 90 mog score, defeating {loser} (70)…").
4. While it renders, the reveal screen shows **"GENERATING REPLAY…"**; when ready, the looping
   replay video plays over the results.

Design choices:
- **Opt-in** — nothing is generated unless the user presses G, so no credits are spent by default.
- **One video, both sides** — a single image-to-video call per battle (not one per player), to
  save API cost.
- **Result-aware** — the prompt narrates the actual outcome from the scoreboard.

If Pika is disabled, the prompt simply doesn't appear and Mog Mirror behaves exactly as before.

## Setup

Config lives in `.env` (gitignored — never commit the key):

```bash
MOGGIE_ENABLE_PIKA=true                              # enables the opt-in replay prompt
MOGGIE_PIKA_PROVIDER=fal                             # use the fal.ai queue API (not the MCP provider)
FAL_KEY=<your-fal-key>                               # format: <id>:<secret>
MOGGIE_PIKA_MODEL=fal-ai/pika/v2.2/image-to-video    # the image-to-video model
MOGGIE_AI_TIMEOUT_SECONDS=120                         # image-to-video is slow; 45s default is too low
MOGGIE_AI_POLL_INTERVAL_SECONDS=3
```

Install dependencies into the project environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Run

```bash
# Validate the fal.ai key + model without a camera (spends a small amount of credits):
.venv/bin/python scripts/smoke_test_pika.py

# Launch the app:
.venv/bin/python -m app.main
```

In the app: **Mog Mirror → center both faces → SPACE** to run the 10s battle. On the score
reveal, press **G** to generate the replay. **ESC/ENTER** = home · **L** = leaderboard.

## How it works (internals)

- **`app/ui/screens/mog_mirror_screen.py`** — the original live-camera round. `_finish_round`
  now also stashes the full both-sides snapshot in `state.reveal_replay_image` and no longer
  auto-submits any AI jobs.
- **`app/core/screen_manager.py`** — `ScreenState.reveal_replay_image` carries that frame to the
  reveal screen.
- **`app/ui/screens/score_reveal_screen.py`** — owns the opt-in replay:
  - `G` → `_start_replay`: encodes the combined frame, builds a result-aware prompt
    (`build_replay_prompt`), and submits one `mog_mirror.replay_video` job.
  - `handle_app_event` watches that job: `succeeded` → downloads the clip off-thread →
    `LoopingVideoPlayer`; `failed`/`timed_out` → shows a retry prompt.
  - `render` shows the `GENERATING REPLAY…` overlay, then the looping video when ready.
- **`app/games/mog_mirror.py`** — `build_replay_prompt(rows)` and `MOG_REPLAY_NEGATIVE_PROMPT`.
- **`app/ai/fal_pika_client.py`** — `generate_video_from_image` inlines the JPEG as a base64
  data URI (fal needs an `image_url`; inlining avoids a separate upload and the
  `422 file_download_error` you get when fal can't fetch a passed-in URL).
- **`app/util/video_playback.py`** — `download_in_background` + `LoopingVideoPlayer` (decode a
  local clip frame-by-frame, looping; returns BGR frames the existing renderer understands).

## Files changed

| File | Change |
|------|--------|
| `.env` (gitignored) | Enable Pika via fal, key, v2.2 model, 120s timeout |
| `.env.example` | Documents `MOGGIE_PIKA_PROVIDER` and the v2.2 / timeout guidance (no secret) |
| `app/ai/fal_pika_client.py` | `generate_video_from_image` (base64 data URI → `generate_video`) |
| `app/util/video_playback.py` (new) | Threaded download + `LoopingVideoPlayer` |
| `app/games/mog_mirror.py` | `build_replay_prompt` + `MOG_REPLAY_NEGATIVE_PROMPT` |
| `app/core/screen_manager.py` | `ScreenState.reveal_replay_image` |
| `app/ui/screens/mog_mirror_screen.py` | Stash both-sides snapshot at finish; no auto-submit |
| `app/ui/screens/score_reveal_screen.py` | Opt-in `G` replay: submit, generate/download/ready, looping playback |
| `app/cv/hand_landmarks.py` | Degrade gracefully when the legacy `mediapipe.solutions` API is absent (see below) |
| `tests/test_*` | `build_replay_prompt`, finish-stash, and score-reveal replay tests |

## Tests

All mocked — no network or camera required:

```bash
.venv/bin/python -m pytest tests/test_mog_mirror.py tests/test_fal_pika_client.py tests/test_score_reveal.py -q
```

> Note: `tests/test_sixseven_rendering.py` fails to import on a stale `ui.` module path. This is
> pre-existing and unrelated to this feature — run with `--ignore=tests/test_sixseven_rendering.py`.

## Environment notes

- **mediapipe / Python 3.13.** The only mediapipe with Python 3.13 wheels (0.10.35) ships just the
  Tasks API and drops the legacy `mediapipe.solutions` module the project used. `FaceDetectionService`
  already falls back to OpenCV's Haar cascade; `hand_landmarks.py` was made to degrade gracefully too
  (it was crashing the CV worker). Effect: face detection is bbox-based (no landmarks; scoring uses
  bbox geometry), and the **67 Challenge hand-tracking game won't detect hands**. Mog Mirror works.
- **Latency.** Image-to-video takes tens of seconds; the replay is opt-in and shows a loading state.
- **Cost.** One generation per battle, only when the user presses G.
