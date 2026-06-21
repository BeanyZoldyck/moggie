# Moggie — opt-in AI recap videos (fal.ai Pika v2.2 image-to-video)

All three games now offer an optional, post-game AI **recap video** — a dramatised highlight
clip of what just happened, generated from a camera frame taken at the end of the round,
with a result-aware prompt. Nothing is generated unless the player presses **G** on the
score-reveal screen, so no credits are spent by default.

---

## Games covered

| Game | Prompt style |
|------|-------------|
| **Mog Mirror** | Cinematic 1v1 face-off replay, names the winner and their aura score |
| **67 Challenge** | High-energy sports broadcast, names the winner and their rep count |
| **Emoji Face Match** | Fast meme-ready clip, names the winner and their points |

One video is generated per round (both players visible in the same frame, P1 left / P2 right).

---

## Setup

Config lives in `.env` (gitignored — never commit the key):

```bash
MOGGIE_ENABLE_PIKA=true                              # enables the G-key recap prompt on score reveal
MOGGIE_PIKA_PROVIDER=fal                             # fal.ai queue API
FAL_KEY=<your-fal-key>                               # format: <id>:<secret>
MOGGIE_PIKA_MODEL=fal-ai/pika/v2.2/image-to-video    # current model
MOGGIE_AI_TIMEOUT_SECONDS=120                         # image-to-video is slow; 45s default is too low
MOGGIE_AI_POLL_INTERVAL_SECONDS=3

# --- optional: save clips to disk ---
MOGGIE_SAVE_GENERATED_MEDIA=true          # copy each clip to MOGGIE_MEDIA_DIR
MOGGIE_MEDIA_DIR=./media                  # directory for saved clips (default: ./media)
```

Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

---

## How to use

1. Play any game to completion (Mog Mirror, 67 Challenge, Emoji Face Match).
2. On the **score-reveal screen**, a hint appears at the bottom: **`G — AI RECAP`**.
3. Press **G**. The screen dims with "GENERATING RECAP…" while fal.ai renders the clip
   (typically 30–90 seconds).
4. When ready the clip loops over the results. **ESC / ENTER** returns home.

If generation fails or the user doesn't press G, nothing is charged and the round ends normally.

---

## Retrieving the video

### Option A — copy the URL from the log

The generated video URL is logged when the clip arrives:

```
INFO  [app.ui.screens.score_reveal_screen] Recap: generated video https://v3.fal.media/files/...
INFO  [app.ui.screens.score_reveal_screen] Recap: ready — tmp=/tmp/moggie_avatar_xxx.mp4 ...
```

Copy the fal.media URL and open it in a browser or `curl` it down.

### Option B — auto-save to disk (recommended for sharing)

Set `MOGGIE_SAVE_GENERATED_MEDIA=true` in `.env`. After each replay is downloaded,
it is copied to `MOGGIE_MEDIA_DIR` with a name like:

```
./media/mog_mirror_recap_moggie_avatar_abc123.mp4
./media/sixty_seven_recap_moggie_avatar_def456.mp4
```

Files persist between sessions. The path is also logged:

```
INFO  [app.ui.screens.score_reveal_screen] Recap saved to media/mog_mirror_recap_....mp4
```

### Option C — query the database

Every saved clip is recorded in the SQLite database (`MOGGIE_DB_PATH`, default `./data/moggie.sqlite`)
in the `media_assets` table:

```sql
SELECT kind, uri, storage_mode, created_at, game_type
FROM media_assets
LEFT JOIN game_sessions ON media_assets.session_id = game_sessions.id
ORDER BY media_assets.created_at DESC
LIMIT 10;
```

`storage_mode` is `"local"` for files saved to `MOGGIE_MEDIA_DIR`, or `"remote"` for
fal.ai URLs only (when `MOGGIE_SAVE_GENERATED_MEDIA=false`).

The idle attract screen also shows recent generated media when `MOGGIE_SAVE_GENERATED_MEDIA=true`.

---

## How it works (internals)

### End-of-round (all three game screens)

`_finish_round()` now:
1. Grabs the final camera frame via `camera_service.latest_display_frame()`.
2. Stores it in `state.reveal_replay_image` (full both-sides frame).
3. Stores the session ID in `state.last_session_id` for DB recording.
4. Transitions to score reveal with `ai_job_ids = []` — no auto-generation.

### Score reveal (opt-in, `G` key)

`ScoreRevealScreen._start_replay()`:
1. Encodes `state.reveal_replay_image` as JPEG bytes.
2. Calls `build_recap_prompt(game_type, rows)` from `app/games/recap_prompts.py` to build a
   result-aware prompt from the actual scores, winner, and labels.
3. Submits a `{game_type}.recap_video` job to `AIJobService`.

When the job succeeds, `handle_app_event` receives the video URL, then `download_in_background`
fetches it off-thread into a temp file. `_drain_replay_queue` picks it up, opens a
`LoopingVideoPlayer`, and if `save_generated_media=True` calls `_save_replay()` to:
  - Copy the temp file to `MOGGIE_MEDIA_DIR`.
  - Call `leaderboard_service.record_media_asset()` to persist it to SQLite.

### `generate_video_from_image` (fal.ai)

`FalPikaClient.generate_video_from_image(image_bytes, mime, prompt, metadata)` base64-encodes
the JPEG into a `data:<mime>;base64,…` URI so fal never needs to fetch a URL from our side
(avoids the `422 file_download_error` that occurs when fal can't fetch an externally hosted file).

---

## Files changed

| File | Change |
|------|--------|
| `.env` (gitignored) | Enable Pika via fal, key, v2.2 model, 120s timeout, optional save flags |
| `.env.example` | Documents all Pika + save config vars |
| `app/games/recap_prompts.py` (new) | `build_recap_prompt(game_type, rows)` + `RECAP_NEGATIVE_PROMPT` for all three games |
| `app/ai/fal_pika_client.py` | `generate_video_from_image` (base64 data URI path) |
| `app/util/video_playback.py` (new) | Threaded download + `LoopingVideoPlayer` |
| `app/core/screen_manager.py` | `ScreenState.reveal_replay_image`, `ScreenState.last_session_id` |
| `app/services/leaderboard_service.py` | `record_media_asset(session_id, kind, uri, ...)` |
| `app/ui/screens/mog_mirror_screen.py` | `_finish_round` stashes frame + session ID; no auto-submit |
| `app/ui/screens/sixty_seven_screen.py` | Same — removed `_submit_replay_ai_job` auto-submit |
| `app/ui/screens/emoji_face_match_screen.py` | Same |
| `app/ui/screens/score_reveal_screen.py` | G-key opt-in for all games; save to disk + record in DB |
| `app/cv/hand_landmarks.py` | Graceful degradation when `mediapipe.solutions` absent (Python 3.13) |
| `tests/test_score_reveal.py` | All-game opt-in, game-typed kind, prompt tests |
| `tests/test_mog_mirror.py` | Finish-stash, replay prompt tests |

---

## Tests

```bash
.venv/bin/python -m pytest tests/test_score_reveal.py tests/test_mog_mirror.py tests/test_fal_pika_client.py -q
```

All mocked — no network, no camera. `tests/test_sixseven_rendering.py` is a pre-existing
broken import; exclude with `--ignore=tests/test_sixseven_rendering.py`.

---

## Known limitations

- **Latency.** Image-to-video takes 30–90 seconds. The loading state makes this visible.
- **One video per round.** Both players appear in the same clip (one fal.ai call).
- **Python 3.13 + mediapipe.** The only mediapipe wheel for Python 3.13 (0.10.35) drops the
  legacy `solutions` API. Face detection falls back to OpenCV's Haar cascade (bbox-based).
  Hand tracking is unavailable; this affects 67 Challenge's hand detection but not scoring
  or the recap generation.
