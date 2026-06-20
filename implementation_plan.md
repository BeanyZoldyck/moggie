# Moggie Implementation Plan

## 1. Summary

Moggie is a greenfield Python native kiosk app for Raspberry Pi OS 64-bit Lite. It should boot directly into a fullscreen Pygame/SDL2 shell, own one USB webcam, run local CV for core gameplay, persist scores in SQLite, cache leaderboard reads in Redis, and treat cloud AI as optional async polish.

The first implementation must prioritize demo reliability:

1. Native app shell, config, database, and launch path.
2. Camera preview and internal event bus.
3. 67 Challenge with green hand overlay and persistent leaderboard.
4. Mog Mirror with local face detection, fallback scoring, and leaderboard.
5. Emoji Face Match with local expression heuristics and fallback modes.
6. Mock-first sponsor/cloud clients, with Redis, Midjourney MCP, and Pika/Fal adapters built from the start behind stable interfaces.

## 2. Locked Decisions

- Runtime: Python 3.10+, Pygame/SDL2, OpenCV, MediaPipe or equivalent, SQLite, Redis.
- Primary target: Raspberry Pi OS 64-bit Lite, no desktop environment, no Chromium kiosk mode.
- Launch model: `systemd` starts `python -m app.main`.
- Core gameplay: local-first and playable without internet.
- Camera ownership: exactly one `CameraService` owns the webcam.
- Multiplayer model: 1v1 by default with fixed left/right camera zones.
- P1 assignment: normalized `x < MOGGIE_ZONE_SPLIT_X`.
- P2 assignment: normalized `x >= MOGGIE_ZONE_SPLIT_X`.
- Default storage: persist names and scores only; do not persist photos/videos unless feature flags enable it.
- Leaderboards: SQLite is the source of truth; Redis caches leaderboard reads and must fall back to SQLite if unavailable.
- Sponsor integrations locked for MVP scaffolding: Redis leaderboard cache, Midjourney MCP image generation, and Pika/Fal video generation.
- Cloud integrations: async, timeout-bound, mock-first, never blocking the game loop.

## 3. Repository Structure

Create a Python-first repo:

```text
moggie/
  README.md
  .env.example
  pyproject.toml
  implementation_plan.md
  scripts/
    dev.sh
    run_game.sh
    install_pi_lite_deps.sh
    install_systemd_service.sh
    init_db.sh
    smoke_test_camera.py
  systemd/
    moggie.service
  app/
    __init__.py
    main.py
    config.py
    db.py
    models/
      player.py
      session.py
      score.py
      media_asset.py
    core/
      app_event.py
      event_bus.py
      game_registry.py
      game_session_manager.py
      screen_manager.py
    ui/
      theme.py
      layout.py
      input.py
      render_utils.py
      screens/
        home_screen.py
        player_setup_screen.py
        calibration_screen.py
        mog_mirror_screen.py
        sixty_seven_screen.py
        emoji_face_match_screen.py
        score_reveal_screen.py
        leaderboard_screen.py
        idle_attract_screen.py
      renderers/
        camera_preview_renderer.py
        hand_overlay_renderer.py
        face_overlay_renderer.py
        game_shell_renderer.py
    services/
      camera_service.py
      cv_service.py
      leaderboard_service.py
      redis_cache_service.py
      storage_service.py
      ai_job_service.py
      sponsor_integration_service.py
    games/
      base.py
      mog_mirror.py
      sixty_seven.py
      emoji_face_match.py
    cv/
      zone_assignment.py
      face_detection.py
      hand_landmarks.py
      expression_features.py
      sixty_seven_counter.py
    ai/
      base.py
      mock_clients.py
      midjourney_mcp_client.py
      fal_pika_client.py
      overshoot_client.py
      image_generation_client.py
      text_generation_client.py
    util/
      ids.py
      time.py
      images.py
      logging.py
  tests/
    test_config.py
    test_leaderboards.py
    test_storage_service.py
    test_zone_assignment.py
    test_sixty_seven_counter.py
    test_expression_features.py
```

Do not add a React/Vite/browser app for MVP.

## 4. Configuration

Implement typed environment config in `app/config.py`. Defaults should work on a laptop in windowed development mode and on the Pi in fullscreen mode.

Required settings:

```bash
MOGGIE_ENV=development
MOGGIE_FULLSCREEN=false
MOGGIE_WINDOW_WIDTH=1280
MOGGIE_WINDOW_HEIGHT=720

MOGGIE_DB_PATH=./data/moggie.sqlite
MOGGIE_ENABLE_REDIS_LEADERBOARD_CACHE=true
MOGGIE_REDIS_URL=redis://localhost:6379/0
MOGGIE_REDIS_LEADERBOARD_TTL_SECONDS=30

MOGGIE_STORAGE_MODE=none
MOGGIE_MEDIA_DIR=./media
MOGGIE_SAVE_SNAPSHOTS=false
MOGGIE_SAVE_GENERATED_MEDIA=false

MOGGIE_CAMERA_INDEX=0
MOGGIE_CAMERA_WIDTH=640
MOGGIE_CAMERA_HEIGHT=480
MOGGIE_CV_WIDTH=320
MOGGIE_CV_HEIGHT=240
MOGGIE_CV_FPS=15

MOGGIE_DEFAULT_GAME_MODE=versus
MOGGIE_ENABLE_FIXED_HALF_ZONES=true
MOGGIE_ZONE_SPLIT_X=0.5
MOGGIE_SHOW_ZONE_DIVIDER=true
MOGGIE_ALLOW_MANUAL_START_OVERRIDE=true

MOGGIE_67_MODE=versus
MOGGIE_67_MAX_HANDS=4
MOGGIE_67_ROUND_SECONDS=20
MOGGIE_67_REQUIRE_BOTH_HANDS=false
MOGGIE_67_MIN_CONFIDENCE=0.55
MOGGIE_67_REP_COOLDOWN_MS=350

MOGGIE_EMOJI_MODE=versus
MOGGIE_EMOJI_MAX_FACES=2
MOGGIE_EMOJI_ROUND_SECONDS=30
MOGGIE_EMOJI_ENABLE_TONGUE_OUT=false
MOGGIE_EMOJI_USE_CLOUD_VALIDATION=false

MOGGIE_ENABLE_PIKA=false
MOGGIE_ENABLE_OVERSHOOT=false
MOGGIE_ENABLE_IMAGE_GENERATION=true
MOGGIE_ENABLE_MIDJOURNEY=true
MOGGIE_MIDJOURNEY_MCP_URL=https://mcp.midjourney.com/mcp
MOGGIE_MIDJOURNEY_TOKEN_STORE=~/.config/moggie/midjourney_oauth.json
MOGGIE_MIDJOURNEY_CLIENT_ID=
MOGGIE_MIDJOURNEY_CLIENT_SECRET=
MOGGIE_ENABLE_LLM_LABELS=false
MOGGIE_ENABLE_QNX_SUBSYSTEM=false

FAL_KEY=
MOGGIE_PIKA_MODEL=fal-ai/pika/v2/turbo/image-to-video
MOGGIE_AI_TIMEOUT_SECONDS=45
MOGGIE_AI_POLL_INTERVAL_SECONDS=2
```

Config parsing should validate enum-like values and clamp numeric values to safe ranges. Invalid config should fail early in development and show a clear diagnostic screen in kiosk mode.

## 5. Data Design

Use SQLite with simple migration/init logic in `app/db.py` and `scripts/init_db.sh`. SQLite is the durable source of truth for players, sessions, scores, and media references.

Use Redis as the leaderboard cache. Leaderboard reads should check Redis first, fall back to SQLite on cache miss or Redis failure, then refresh the cache. Score writes should update SQLite first and invalidate the affected leaderboard cache key. Redis failure must never block gameplay or score persistence.

Suggested cache keys:

```text
leaderboard:mog_mirror:top10
leaderboard:sixty_seven:top10
leaderboard:emoji_face_match:top10
```

Cached values should be compact JSON lists matching the leaderboard query result shape. Use `MOGGIE_REDIS_LEADERBOARD_TTL_SECONDS` as a safety TTL even though writes also invalidate keys.

Tables:

```sql
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_sessions (
    id TEXT PRIMARY KEY,
    game_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    game_type TEXT NOT NULL,
    score INTEGER NOT NULL,
    rank INTEGER,
    label TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES game_sessions(id),
    FOREIGN KEY(player_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    player_id TEXT,
    kind TEXT NOT NULL,
    storage_mode TEXT NOT NULL,
    uri TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES game_sessions(id),
    FOREIGN KEY(player_id) REFERENCES players(id)
);
```

Leaderboard query:

```sql
SELECT
    players.display_name,
    scores.score,
    scores.label,
    scores.created_at
FROM scores
JOIN players ON scores.player_id = players.id
WHERE scores.game_type = ?
ORDER BY scores.score DESC, scores.created_at ASC
LIMIT 10;
```

Persist scores at session completion. Do not require leaderboard rank to be precomputed; it can be computed from the sorted query after insertion.

Redis cache policy:

- On score write: write SQLite transaction first, then delete `leaderboard:{game_type}:top10`.
- On leaderboard read: return Redis value when present and valid.
- On cache miss: query SQLite, write JSON result to Redis with TTL, return SQLite result.
- On Redis connection/error: log once, bypass cache for that operation, and continue with SQLite.

## 6. Internal Interfaces

### Event Envelope

All cross-service messages use this envelope:

```python
from dataclasses import dataclass

@dataclass
class AppEvent:
    type: str
    session_id: str | None
    timestamp_ms: int
    payload: dict
```

Core event types:

- `session_state`
- `cv.hand_landmarks`
- `cv.face_landmarks`
- `score_update`
- `ai_job_update`
- `game_message`

Normalized CV coordinates are always in `[0, 1]` relative to the source camera frame.

### Game Interface

```python
class Game:
    game_type: str
    min_players: int
    max_players: int

    def start(self, session: "GameSession") -> None:
        ...

    def handle_event(self, event: "AppEvent") -> list["AppEvent"]:
        ...

    def update(self, now_ms: int) -> list["AppEvent"]:
        ...

    def render(self, surface: "pygame.Surface", state: "RenderState") -> None:
        ...
```

Each game owns its own gameplay state. Shared concerns such as camera frames, overlays, config, storage, and leaderboard writes stay in services.

## 7. Core Services

### `MoggieApp`

- Initialize config, logging, DB, services, Pygame, and screen manager.
- Run the main loop at target 30 FPS.
- Poll keyboard/mouse events.
- Drain app event queues.
- Update active screen/game.
- Render the active screen.
- Shut down camera/CV/AI workers cleanly.

### `ScreenManager`

- Route between home, setup, calibration, game, score reveal, leaderboard, and idle screens.
- Centralize Escape/Home/back behavior.
- Preserve current session context through transitions.

### `CameraService`

- Open `MOGGIE_CAMERA_INDEX`.
- Capture 640x480 display frames.
- Produce 320x240 CV frames.
- Expose latest display frame, latest CV frame, and snapshots.
- Handle missing camera with a diagnostic state rather than crashing.

### `CVService`

- Run face detection, hand landmarks, and expression feature extraction.
- Publish structured CV events.
- Avoid running expensive unrelated models at the same time during gameplay.
- In 67 Challenge, prioritize hand tracking only.
- In Mog Mirror and Emoji Face Match, prioritize face detection/landmarks.

### `LeaderboardService`

- Create/reuse player rows by display name per session.
- Store scores.
- Query top 10 per game.
- Use Redis for leaderboard read-through caching.
- Invalidate the per-game leaderboard cache after score writes.
- Provide rank after write.

### `RedisCacheService`

- Connect to `MOGGIE_REDIS_URL`.
- Provide `get_json`, `set_json`, and `delete` helpers.
- Enforce TTL for leaderboard cache entries.
- Degrade gracefully when Redis is unavailable.

### `StorageService`

- Implement `none`, `local`, and `usb` modes.
- In `none`, discard media after processing and return no persistent URI.
- In `local`, save under `MOGGIE_MEDIA_DIR`.
- In `usb`, save under a configured/mounted USB path once added.

### `AIJobService`

- Run cloud jobs in a worker thread or async task queue.
- Emit `ai_job_update` events.
- Enforce timeouts.
- Use mock clients until real provider keys and endpoint details are available.
- Never block score reveal or leaderboard writes on cloud jobs.

## 8. Native UI Plan

Use a bold, high-contrast arcade style readable from several feet away. Keep text short, scores large, and game controls obvious. Use keyboard-first navigation.

Screens:

- `HomeScreen`: title, three game cards, leaderboard preview, sponsor/tech footer.
- `PlayerSetupScreen`: selected game, one/two name fields, Enter/Tab/Escape behavior.
- `CalibrationScreen`: camera preview, zone divider, detection status, manual override if enabled.
- `MogMirrorScreen`: two-player detection, capture, local scoring, reveal.
- `SixtySevenScreen`: live preview, green hand overlays, timer, live rep counts, valid-rep pulse.
- `EmojiFaceMatchScreen`: emoji lanes, moji zones, camera/face overlay, hit/miss/streak feedback.
- `ScoreRevealScreen`: final scores, winner, labels, rank, generated media if ready.
- `LeaderboardScreen`: top 10 for selected game.
- `IdleAttractScreen`: optional cycle of game cards, leaderboards, and saved generated clips.

Renderers:

- `CameraPreviewRenderer`: scale/crop latest frame and provide coordinate mapping.
- `HandOverlayRenderer`: draw green joints, skeleton lines, palm centers, stale warnings.
- `FaceOverlayRenderer`: draw face boxes, assigned zones, expression indicators.
- `GameShellRenderer`: shared divider, timer, score panels, countdown overlay.

## 9. Game Implementation Details

### 9.1 67 Challenge

Default mode: simultaneous 1v1 versus.

Core flow:

1. Enter two names.
2. Calibrate with both players in fixed halves.
3. Show hands and start countdown.
4. Track up to four hands from one webcam frame.
5. Assign hands to P1/P2 by palm center x-coordinate.
6. Draw green hand overlays.
7. Count valid reps independently for each player.
8. End after `MOGGIE_67_ROUND_SECONDS`.
9. Show final scores, winner, labels, and leaderboard.

Rep counting state per player:

```text
NEUTRAL
  -> EXTENDING when hands move apart past threshold
  -> EXTENDED when max extension threshold reached
  -> RETURNING when hands move back toward neutral
  -> NEUTRAL when reset threshold reached; count +1
```

Anti-jitter rules:

- Ignore landmarks below `MOGGIE_67_MIN_CONFIDENCE`.
- Ignore stale landmarks.
- Require minimum distance delta and movement velocity.
- Enforce `MOGGIE_67_REP_COOLDOWN_MS`.
- If only one hand is visible, pause counting unless fallback logic is explicitly enabled later.

Solo fallback:

- `MOGGIE_67_MODE=solo`
- `MOGGIE_67_MAX_HANDS=2`
- One player name and one score panel.

### 9.2 Mog Mirror

Default mode: 1v1.

Core flow:

1. Enter two names.
2. Detect one face per zone.
3. Countdown and capture frame.
4. Crop each face or upper body region.
5. Generate local aura score immediately.
6. Generate local fallback labels.
7. Optionally submit caricature/video AI jobs.
8. Reveal scores and winner immediately.
9. Save both scores.
10. Show leaderboard.

Scoring:

- Score range should feel playful, usually 65-98.
- Use a deterministic random seed from session/player plus small local modifiers for centering, face size, smile/expression energy, and detection confidence.
- Avoid cruel or serious attractiveness framing.

Fallback behavior:

- If no cloud generation: show original crop with styled border/filter.
- If face detection is imperfect: allow manual override if `MOGGIE_ALLOW_MANUAL_START_OVERRIDE=true`.

### 9.3 Emoji Face Match

Default mode: simultaneous 1v1 versus.

Supported MVP expressions:

- Smile
- Mouth open / surprised
- Eyes closed
- Wink
- Neutral / deadpan

Core flow:

1. Enter two names.
2. Detect one face per zone.
3. Countdown.
4. Spawn emoji sequences in each player lane.
5. Evaluate local expression features when an emoji enters the moji zone.
6. Award +100 for correct, +0 for miss.
7. Track streaks visually.
8. End after `MOGGIE_EMOJI_ROUND_SECONDS`.
9. Save both scores and show leaderboard.

Fallback modes:

- `MOGGIE_EMOJI_MODE=alternating`: two names, one active player at a time, max faces 1.
- `MOGGIE_EMOJI_MODE=solo`: one name, one lane, max faces 1.

Cloud validation:

- Only enabled when `MOGGIE_EMOJI_USE_CLOUD_VALIDATION=true`.
- Local result is shown immediately.
- Cloud result may be logged or used for sponsor diagnostics; it should not delay score feedback.

## 10. Sponsor And Cloud Integration Plan

Build all cloud integrations behind interfaces first. Mock clients must produce realistic statuses and results so the UI and game flow can be developed without credentials. Redis, Midjourney MCP, and Pika/Fal are locked sponsor paths and should be included in the initial scaffolding, even if their real clients are disabled in local development.

### Redis Leaderboard Cache

Redis is the locked caching layer for leaderboards. The team has credits for Redis, so the implementation should assume Redis will be available for the demo path while still treating SQLite as the source of truth.

Implementation rules:

- Use Redis only as cache, not durable storage.
- Cache top-10 leaderboard reads per game type.
- Invalidate the per-game cache key after score writes.
- Fall back to SQLite on Redis errors.
- Keep Redis connection/config in `RedisCacheService`, not scattered through game code.

### Midjourney MCP Image Generation

Midjourney is the locked image-generation provider for Mog Mirror caricatures via the pre-release MCP endpoint:

```text
https://mcp.midjourney.com/mcp
```

The endpoint is an MCP server, not a normal REST docs page. The app should integrate it through a Python MCP client behind `ImageGenerationClient`, not by hard-coding a browser workflow.

Implementation rules:

- Implement `MidjourneyMCPClient` behind `MOGGIE_ENABLE_MIDJOURNEY`.
- Use `MOGGIE_MIDJOURNEY_MCP_URL` for the endpoint.
- Do not depend on Codex's MCP OAuth session at runtime; Codex is only a development client.
- Add `scripts/auth_midjourney.py` to perform setup-time OAuth for the Pi and write tokens to `MOGGIE_MIDJOURNEY_TOKEN_STORE`.
- Store OAuth tokens outside the repo, with `0600` permissions, owned by the `pi` service user.
- Runtime should load the stored token, refresh it when possible, and skip Midjourney generation if auth is missing/expired.
- Discover available MCP tools/capabilities at startup or first use; do not assume final pre-release tool names until confirmed.
- Expose a stable internal method: `generate_caricature(image_bytes, prompt, metadata)`.
- Run Midjourney jobs through `AIJobService` with status events and timeouts.
- Store generated media only when storage flags allow it.
- Fall back to original face crops/local effects if MCP auth, tool discovery, generation, or network fails.

Headless Pi OAuth flow:

1. During setup, run `scripts/auth_midjourney.py` over SSH or from a kiosk admin/setup screen.
2. The script uses the MCP Python SDK OAuth client support with Streamable HTTP.
3. The redirect handler prints an authorization URL and optionally shows a QR code on the kiosk display.
4. A teammate opens the URL on a phone/laptop, completes Midjourney OAuth, then pastes the final callback URL/code back into the setup script if a local callback cannot be reached.
5. The script stores access/refresh token state in `~/.config/moggie/midjourney_oauth.json`.
6. `moggie.service` starts later with no browser and no human interaction; `MidjourneyMCPClient` uses the token store.

If the Midjourney OAuth server supports a true device-code flow, prefer that for the Pi because it is cleaner for a headless kiosk. If it only supports authorization-code redirect, use the manual copy/paste callback flow above.

### Pika via Fal

Current public Pika API page points developers to Fal.ai for Pika video models. Fal currently exposes Pika image-to-video models including:

- `fal-ai/pika/v2/turbo/image-to-video`
- `fal-ai/pika/v2.2/image-to-video`

Default implementation choice:

- Use `fal-ai/pika/v2/turbo/image-to-video` first for demo latency.
- Allow override with `MOGGIE_PIKA_MODEL`.
- Submit jobs asynchronously through Fal queue APIs or `fal_client`.
- Store `request_id`, poll status, and emit `ai_job_update`.
- Do not use webhooks for MVP because inbound eduroam access may fail.
- Return a `GeneratedVideo` with a downloadable/public video URL when complete.

Expected minimal input:

```python
{
    "image_url": "...",
    "prompt": "A ridiculous victory aura reveal for a hackathon party game"
}
```

Expected useful output:

```python
{
    "video": {
        "url": "..."
    }
}
```

### Overshoot

No stable public Overshoot API documentation was found during planning. Implement a provider-neutral `VisionValidationClient` and an `OvershootVisionClient` skeleton with env-configured endpoint/key, but keep it disabled by default until sponsor docs are available.

The client contract should support:

```python
class VisionValidationClient:
    async def classify_expression(
        self,
        image_bytes: bytes,
        target_expression: str,
        allowed_labels: list[str],
    ) -> "ExpressionValidationResult":
        ...
```

### LLM Labels

- Implement provider-neutral text-generation interfaces first.
- Use fallback deterministic/random labels immediately.
- Add real clients only after core gameplay is stable.
- Cache generated labels/media where storage policy allows.

## 11. Milestones

### Milestone 1: Platform Scaffold

- Add repo structure, `pyproject.toml`, `.env.example`, README, scripts, and systemd unit.
- Implement typed config and logging.
- Implement SQLite init, Redis cache config/service, and leaderboard service.
- Add unit tests for config and leaderboard.

### Milestone 2: Native Shell

- Implement Pygame app startup in windowed dev mode and fullscreen Pi mode.
- Add home screen, game cards, player setup, and screen routing.
- Add shared theme/layout/render utilities.
- Add placeholder score reveal and leaderboard screens.

### Milestone 3: Camera And CV Base

- Implement camera smoke test.
- Implement `CameraService` and camera preview renderer.
- Implement event bus and worker lifecycle.
- Add diagnostic screen for missing camera.
- Add zone divider and normalized coordinate mapping.

### Milestone 4: 67 Challenge MVP

- Add MediaPipe or equivalent hand tracking.
- Draw green hand landmark overlay.
- Implement zone assignment and independent player state machines.
- Persist scores and show leaderboard.
- Add solo fallback config.
- Add unit tests for zone assignment and rep counter.

### Milestone 5: Mog Mirror MVP

- Add face detection and calibration.
- Capture snapshot/crops.
- Compute aura scores and labels locally.
- Reveal winner and persist both scores.
- Add AI job hooks for caricature/video without requiring real cloud calls.

### Milestone 6: Emoji Face Match MVP

- Add face landmark/expression feature extraction.
- Add emoji lanes and scoring zones.
- Implement smile, mouth-open, eyes-closed, wink, neutral.
- Add versus, alternating, and solo modes.
- Persist scores and show leaderboard.

### Milestone 7: Sponsor Polish

- Add Midjourney MCP real client behind `MOGGIE_ENABLE_MIDJOURNEY`.
- Add Fal/Pika real client behind `MOGGIE_ENABLE_PIKA`.
- Add mock/real status display for generated media.
- Add sponsor diagnostics/health screen if time allows.
- Add architecture notes for QNX control-plane stretch story.

### Milestone 8: Demo Hardening

- Add idle/attract mode.
- Tune UI for 1080p HDMI and camera lighting.
- Add fallback config presets.
- Run stress tests.
- Document Pi setup, service install, and demo reset procedure.

## 12. Four-Person Hackathon Split

### Developer A: Platform And UI Shell

- Repo scaffold, config, DB, services.
- Pygame app loop and screen manager.
- Home/setup/calibration/leaderboard/score screens.
- Pi scripts and systemd launch path.

### Developer B: Camera/CV And 67 Challenge

- Camera service, CV service, frame/event schemas.
- Hand landmarks and overlay renderer.
- Zone assignment and 67 rep counter.
- 67 game screen, fallback mode, tests.

### Developer C: Mog Mirror, Emoji, AI Polish

- Face detection and expression features.
- Mog Mirror scoring/reveal.
- Emoji lanes and expression scoring.
- Midjourney/Pika hooks in game reveal flows.

### Developer D: Sponsor Integrations And Cache

- Redis cache service and leaderboard cache tests.
- Mock AI job service and provider-neutral interfaces.
- Midjourney MCP adapter.
- Pika/Fal adapter if credentials are ready.
- Sponsor diagnostics/health display.

All developers share UI polish and demo hardening near the end.

## 13. Risk Register

| Risk | Impact | Mitigation |
|---|---:|---|
| MediaPipe install/performance on Pi is poor | High | Keep CV resolution low, support solo fallback, test early on target Pi, use simpler OpenCV fallback where needed. |
| Four-hand tracking is noisy | High | Keep `MOGGIE_67_MODE=solo` and `MOGGIE_67_MAX_HANDS=2` rollback ready. |
| Two-face expression scoring is unreliable | High | Use alternating/solo fallback and start with only five feasible expressions. |
| Cloud APIs are slow/unavailable | Medium | Mock-first clients, async jobs, local scoring, timeout-bound workers. |
| Webcam missing or wrong index | Medium | Camera diagnostic screen, configurable index, smoke test script. |
| SQLite write failure | Medium | Show final score anyway, surface leaderboard unavailable warning, log details. |
| Redis unavailable | Low | Treat Redis as cache only; log and fall back to SQLite leaderboard queries. |
| Midjourney MCP pre-release changes | Medium | Discover MCP tools dynamically, keep mock fallback, and isolate provider specifics in `MidjourneyMCPClient`. |
| Midjourney auth/credential issue | Medium | Keep `MOGGIE_ENABLE_MIDJOURNEY` feature flag and fallback to original crops/local effects. |
| Pi thermal throttling | Medium | Active cooling, lower CV FPS/resolution, avoid desktop/browser compositor. |
| Sponsor API docs arrive late | Medium | Provider-neutral interfaces and mocks; wire concrete adapters only after stable docs/keys. |
| UI unreadable at booth distance | Medium | Large type, high contrast, minimal copy, 1080p manual check. |

## 14. Test Plan

Unit tests:

- `test_config.py`: defaults, env overrides, invalid enum values.
- `test_leaderboards.py`: insertion, ordering, ties by earliest timestamp, per-game separation.
- `test_leaderboards.py`: Redis cache hit, cache miss refresh, invalidation after score write, Redis-down fallback.
- `test_storage_service.py`: `none`, `local`, disabled media persistence.
- `test_zone_assignment.py`: left/right boundary, custom split, ambiguous values.
- `test_sixty_seven_counter.py`: valid rep sequence, jitter ignored, cooldown, stale landmarks.
- `test_expression_features.py`: heuristic thresholds for supported expressions.

Integration tests:

- DB init and repeated init are idempotent.
- Session lifecycle writes `created -> running -> complete`.
- Mock AI job emits queued/running/complete/failure statuses.
- Mock Midjourney MCP client maps image-generation requests to AI job updates.
- Camera service handles mocked open failure.

Manual Pi tests:

- Boot to `moggie.service`.
- Camera opens at configured resolution.
- Keyboard input works from home through score screen.
- All three games complete one round.
- Leaderboard persists after restart.
- Cloud flags disabled still allow all games.
- 10 consecutive 67 rounds do not crash.
- Camera unplug/retry path does not crash.

## 15. External API References

- Midjourney MCP endpoint: https://mcp.midjourney.com/mcp
- Pika API page: https://pika.art/api
- Fal Pika v2 Turbo image-to-video model: https://fal.ai/models/fal-ai/pika/v2/turbo/image-to-video
- Fal Pika v2.2 image-to-video model: https://fal.ai/models/fal-ai/pika/v2.2/image-to-video
- Fal asynchronous inference docs: https://fal.ai/docs/documentation/model-apis/inference/queue
