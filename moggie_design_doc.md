# Moggie Design Document

## 0. Purpose of This Document

This document is the source-of-truth design brief for **Moggie**, a Berkeley AI Hackathon project. Use this document to generate concrete technical specification, repository structure, implementation plan, task breakdown, and code scaffolding.

If a detail is not explicitly specified, the implementation agent should prefer presenting options and asking for human verification rather than making assumptions and silently moving forward. The project is a hackathon build: prioritize speed, demo reliability, and visible polish over production-grade complexity. Remember to document all decisions and design choices for visibility and to keep the entire 4-person team on the same page.

---

## 1. Project Context and Product Summary

### 1.1 Project Name

**Moggie**

The name comes from "mogging," but the project should be a party game framed around comedic "aura," "mog energy," and social mechanics.

### 1.2 One-Sentence Description

Moggie is a Raspberry Pi OS Lite-powered AI party-game kiosk where players choose camera-based mini-games, compete using face/hand/expression computer vision, and get funny AI-generated scores, leaderboards, and media outputs.

### 1.3 Longer Product Description

Moggie is a single kiosk application, similar in spirit to a Jackbox-style party-game hub. It runs on a Raspberry Pi 4 connected to a USB webcam, HDMI display, and keyboard. Players walk up to the booth, enter their names, select a game, stand in front of the camera, and play short computer-vision/AI-driven games.

The first version supports three mini-games. The product should be designed as a **1v1 party-game kiosk by default**, with fixed left/right player zones and feature flags that allow rapid rollback to solo or alternating-turn modes if Raspberry Pi performance or CV reliability is insufficient.

1. **Mog Mirror**
   - Two players stand in front of the camera, one in the left half and one in the right half.
   - The system detects both faces and assigns them to Player 1 or Player 2 by x-coordinate.
   - It captures each player's face or full upper-body crop.
   - It generates a caricature or stylized AI image if cloud generation is available.
   - It assigns each player a comedic "aura score" out of 100.
   - It displays a winner and stores top 5 scores in a leaderboard.
    - If the user scores in the top 5, it should prompt them for a nickname, and store their name and score in the SQLite database.

2. **67 Challenge**
   - Two players stand side-by-side, Player 1 in the left half and Player 2 in the right half.
   - Both players perform the viral "six-seven" hand movement at the same time.
   - The system uses one webcam frame and one hand-tracking pipeline, allowing up to four hands.
   - It assigns detected hands to the left or right player zone based on normalized x-coordinate.
   - It displays a live green hand-landmark overlay for both players.
   - It counts approximate valid reps independently for each player.
   - It stores both final scores in the leaderboard. Again, top 5 scores should be stored. 
   - If four-hand tracking is too slow or noisy, a config flag can revert the game to solo mode.

3. **Emoji Face Match**
   - Two players stand side-by-side, Player 1 in the left half and Player 2 in the right half.
   - Each side has its own emoji lane and moji zone.
   - The players must make matching facial expressions when their emojis enter the scoring zone.
   - The system detects up to two faces and assigns each face to a player zone by x-coordinate.
   - It uses local face landmarks and/or cloud vision validation to determine whether each expression matches.
   - It scores hits/misses for each player and stores both final scores in the leaderboard.
   - If two-face expression scoring is unreliable, a config flag can revert to alternating-turn or solo mode.

The project should feel viral, funny, competitive, and immediately understandable at a hackathon booth. The technical story should emphasize embedded AI, local real-time CV, sponsor integrations, and a robust feature-flag strategy for rapid demo rollback.

---

## 2. Hackathon Goals and Priorities

### 2.1 Primary Goals

Moggie should optimize for:

1. **Polished booth demo**
   - The app should look like a coherent kiosk product.
   - Judges and attendees should understand how to play within seconds.
   - The UI should be clear from a few feet away.

2. **Viral social experience**
   - The games should be funny, quick, replayable, and easy to watch.
   - Leaderboards should encourage repeated attempts.
   - Generated media should create a strong "show your friends" moment.

3. **Sponsor explainability**
   - The team should be able to explain how sponsor technologies are used.
   - Sponsor integrations should be meaningful but should not make the demo fragile.
   - Each mini-game should have a plausible sponsor angle.

4. **Hackathon implementation speed**
   - Use common, well-documented technologies.
   - Do not reinvent CV models.
   - Use existing libraries and APIs.
   - Prefer simple, stable architecture over elaborate production design.
   - Basically, reuse existing technology as much as possible.

5. **Demo resilience**
   - Core gameplay should not depend on cloud APIs.
   - Cloud AI should enhance the experience but degrade gracefully.
   - The app should survive spotty eduroam, camera hiccups, and API latency.

### 2.2 Non-Goals

Do not attempt to build the following in the first hackathon version:

- custom-trained CV models;
- fully offline generative AI;
- mobile phone controllers;
- multiplayer over peer-to-peer networking;
- LAN discovery;
- production-grade user accounts;
- advanced data privacy infrastructure;
- arbitrary expression recognition;
- serious attractiveness prediction;
- QNX-first production deployment;
- real biometric identity tracking;
- long-term persistent photo storage by default.

---

## 3. Locked Product Decisions

The following decisions are already made and should be treated as fixed unless implementation proves impossible.

### 3.1 App Form Factor

Moggie is a **single kiosk app** where users choose one of three games from a home screen.

It is not three separate demos.

### 3.1.1 Primary Multiplayer Model

Moggie should be implemented as a **1v1 kiosk by default**.

Default player layout:

```text
+-----------------------------+-----------------------------+
| Player 1 Zone               | Player 2 Zone               |
| normalized x < 0.5          | normalized x >= 0.5         |
| left half of camera frame   | right half of camera frame  |
+-----------------------------+-----------------------------+
```

Every game should use fixed half-screen zones for assignment, scoring, and UI layout:

- Player 1 is assigned to the left half of the frame.
- Player 2 is assigned to the right half of the frame.
- Face, hand, and expression detections are assigned by the normalized x-coordinate of their center point.
- The UI should draw a clear vertical divider during calibration and gameplay.
- Players should be instructed to stay inside their assigned halves.

Fallback modes should be controlled by configuration flags, not by code rewrites. If simultaneous 1v1 is unstable on the Raspberry Pi 4, games should be able to switch to solo or alternating-turn mode quickly.


### 3.2 Hardware

Primary hardware target:

- Raspberry Pi 4;
- USB webcam;
- direct HDMI display;
- keyboard input;
- optional USB storage device.

### 3.3 Operating System

Default implementation target:

- **Raspberry Pi OS 64-bit Lite.**
- Do **not** use the standard desktop image for the primary demo build.
- Do **not** run Chromium, a desktop browser, X11 desktop session, Wayland desktop session, or full desktop environment for the MVP.
- The Pi should boot directly into the Moggie game shell using a `systemd` service.
- The game shell should render directly to the HDMI display through a lightweight native Python UI stack, preferably **Pygame / SDL2**.

Low-effort performance guidance:

- Use Raspberry Pi OS 64-bit Lite rather than Ubuntu, QNX, or a full desktop Raspberry Pi OS image for the main demo path.
- Use an active cooler or fan if available.
- Keep camera capture at 640x480 and CV inference at 320x240 or similar.
- Draw overlays inside the native game UI from landmark coordinates rather than encoding processed video.
- Disable unneeded services.
- Avoid desktop environments, browser tabs, and browser compositor overhead.
- Do not spend hackathon time switching to a niche OS for performance.
- Avoid aggressive overclocking unless cooling and power are known-good; thermal throttling during judging is worse than a modest FPS gain.

Primary boot/runtime model:

```text
Power on Pi
  -> Raspberry Pi OS 64-bit Lite
  -> systemd starts moggie.service
  -> Python app initializes config/db/camera/CV/UI
  -> Pygame/SDL2 opens fullscreen HDMI surface
  -> Moggie home screen appears directly
```

QNX should be treated as:

- a sponsor-facing stretch goal;
- an optional subsystem;
- a possible real-time control plane, timing loop, watchdog, or event broker;
- not the main dependency for the MVP.

Rationale: QNX is relevant to embedded/real-time systems, but QNX-first integration adds setup risk around camera, display, build tooling, and library support. Raspberry Pi OS 64-bit Lite gives the fastest low-overhead path for the Pi 4 while still supporting Python, OpenCV, MediaPipe or equivalent CV libraries, SDL2/Pygame display output, SQLite, and outbound local/internalS API calls.

### 3.4 Network Model

The venue network is expected to be **eduroam**.

Assume:

- outbound local/internalS works;
- inbound connections to the Pi may not work;
- peer-to-peer WebRTC may not work reliably;
- local network discovery should not be required.

Therefore:

- the primary game should run as a local native application, not as a browser/client-server web app;
- core gameplay should run locally inside the Pi process tree;
- external services should be called over outbound local/internalS only;
- no phone-controller requirement;
- no peer-to-peer architecture;
- no dependency on another laptop opening the Pi app over the network.

A local local/internal debug/admin API may be added if useful, but it is not part of the MVP requirement and should not be necessary to play the game.

### 3.5 Player Input

Players enter names using a keyboard connected to the kiosk.

Do not build mobile controller input for MVP.

### 3.6 Runtime and UI Stack

Preferred stack:

- Raspberry Pi OS 64-bit Lite;
- Python 3.10+;
- Pygame / SDL2 for fullscreen native HDMI rendering;
- OpenCV for camera capture and image processing;
- MediaPipe or equivalent for hands and face landmarks;
- SQLite for persistence;
- `asyncio`, threads, or multiprocessing for separating UI loop, CV loop, and AI jobs;
- feature flags for game mode, CV limits, AI integrations, and rollback behavior.

Do **not** use React, Vite, Chromium kiosk mode, or a desktop browser for the main demo path. The app should load directly into the game shell.

Rationale: the native Python/Pygame path reduces OS and browser overhead, works with Raspberry Pi OS Lite, keeps the full game in one language/runtime, and is fast enough for a polished hackathon kiosk. It also avoids desktop setup risk and eliminates local browser/server coordination.

### 3.7 CV Stack

Use existing CV libraries.

Preferred:

- OpenCV for camera capture and basic image processing;
- MediaPipe or equivalent for hands and face landmarks;
- native Pygame surfaces for camera preview and overlays;
- simple drawing primitives for landmarks, skeletons, boxes, timers, and score UI.

Do not build custom CV models.

Do not stream processed video through an internal web server unless it becomes necessary for debugging. The native game loop should draw the camera frame and overlays directly.

### 3.8 AI Integration Strategy

Cloud AI may be used, but should not be critical to basic gameplay.

Use cloud services for:

- caricature/stylized image generation;
- post-round video generation;
- semantic vision validation;
- humorous labels;
- host narration;
- loading-screen copy.

Core gameplay timing and scoring should remain local wherever possible.

### 3.9 Storage Policy

Default behavior:

- store player names and scores;
- do not persist photos/videos by default;
- process photos temporarily in memory or temp files;
- allow media storage through feature flags.

Supported storage modes:

- `none`: no persistent media storage;
- `local`: save media to local disk;
- `usb`: save media to mounted USB storage.

### 3.10 Track and Sponsor Orientation

The project is aimed at the hackathon's playful/experimental game-oriented track, referred to in discussion as **Ddoski's Playground**.

Sponsor technologies of interest include:

- Pika;
- Midjourney pre-release MCP server for image generation;
- Anthropic or equivalent LLM;
- Redis for leaderboard caching;
- Sentry, Runpod, Arize, Deepgram, or others if useful.
- QNX if possible

Pika should be integrated if possible -- We can feed short clips into the model and tell it to generate funny "replays" of the round.

---

## 4. Sponsor Integration Strategy

### 4.1 QNX - OPTIONAL STRETCH GOAL

QNX should be presented as an embedded real-time systems angle.

Possible integration levels:

1. **Minimum viable sponsor story**
   - Project is architected with a separable real-time control plane.
   - The deterministic timing/scoring loop could be moved to QNX.
   - The team can explain why QNX is relevant for embedded kiosks and real-time event processing.

2. **Better stretch goal**
   - Build a small QNX-compatible service that handles heartbeat, watchdog, or scoring events.
   - Linux native app sends events to this subsystem or mirrors the same interface.

3. **Highest effort**
   - Boot QNX on Pi 4 and demonstrate camera/display/control-plane logic.
   - This is not required for the main demo and should only be attempted if sponsor support makes it low-risk.

Do not make QNX required for playing the games.

### 4.2 Pika

Pika should be used for generated video/media payoff.

Best use cases:

- after Mog Mirror, animate the player's caricature or snapshot into a short "aura reveal" clip;
- after a 67 Challenge high score, generate a ridiculous victory clip;
- after Emoji Face Match, generate a transformation or reaction video;
- use generated content as attract-mode media if storage is enabled.

Pika generation should be asynchronous and non-blocking. The player should see their score immediately. The app may then display "generating aura clip..." and show the clip if ready.

### 4.4 Midjourney MCP Image Generation

Use Midjourney's pre-release MCP server for Mog Mirror caricatures.

Endpoint:

```text
https://mcp.midjourney.com/mcp
```

Implementation notes:

- integrate through an MCP client behind the internal `ImageGenerationClient` interface;
- do not depend on Codex's MCP OAuth session at runtime; the kiosk app must have its own Midjourney OAuth token store;
- add a setup-time `scripts/auth_midjourney.py` flow for headless Pi authorization;
- store Midjourney OAuth tokens outside the repo with `0600` permissions, owned by the service user;
- discover available MCP tools/capabilities at startup or first use because the server is pre-release;
- keep Midjourney jobs asynchronous and timeout-bound;
- do not block score reveal or leaderboard writes on image generation;
- store generated media only when storage flags allow it.

Headless Pi OAuth flow:

1. During setup, run `scripts/auth_midjourney.py` over SSH or from a kiosk admin/setup screen.
2. The script connects to the MCP endpoint with OAuth-aware Streamable HTTP client support.
3. The script prints an authorization URL and may display a QR code on the kiosk screen.
4. A teammate completes OAuth on a phone/laptop and pastes the final callback URL/code into the setup script if no local redirect is reachable.
5. The script writes token state to `~/.config/moggie/midjourney_oauth.json`.
6. Runtime generation uses the stored token and refreshes it when possible. If auth is missing or expired, the app skips Midjourney generation and uses local image fallback.

If Midjourney integration is too slow, unavailable, or operationally awkward, fall back to:

- original webcam crop;
- locally applied visual effects;
- LLM-generated label and score.

### 4.5 LLM Provider

Use an LLM for:

- aura labels;
- loading messages;
- fake analysis text;
- host narration;
- score explanations;
- category names.

LLM output should be cached or generated with timeouts so it does not block gameplay.

### 4.6 Redis

Redis is a locked sponsor integration for the leaderboard cache.

Use Redis for:

- top-10 leaderboard read-through cache;
- per-game leaderboard cache invalidation after score writes;
- optional live score pub/sub or event stream if time remains.

SQLite remains the source of truth. Redis failure should never prevent score persistence or gameplay.

### 4.7 Other Sponsors

Optional integrations:

- Sentry: kiosk error reporting.
- Runpod: hosted GPU backend for heavier CV/image/video tasks.
- Arize: evaluation/observability of AI outputs if sponsor track encourages it.
- Deepgram: voice announcer or speech interaction, only if time remains.

Do not over-integrate sponsors at the cost of core demo stability.

---

## 5. User Stories

### 5.1 Player User Stories

#### US-1: Choose a Game

As a player, I want to walk up to the kiosk and choose one of three games so I can start playing immediately.

Acceptance criteria:

- Home screen shows three game cards.
- Each card has name, short description, and start action.
- Player can use keyboard/mouse.
- Selecting a game advances to name entry.

#### US-2: Enter Player Names

As a player, I want to enter my name so my score appears on the leaderboard.

Acceptance criteria:

- One-player games ask for one name.
- Mog Mirror asks for two names.
- Empty names are rejected or replaced by generated aliases.
- Names are persisted with scores.
- Keyboard input works reliably.

#### US-3: Play Mog Mirror

As two players, we want to stand in front of the camera and get funny AI aura scores.

Acceptance criteria:

- App detects two faces.
- App shows visual face boxes or detection status.
- App captures a snapshot.
- App assigns each player an aura score out of 100.
- App displays humorous labels.
- App reveals winner.
- App updates leaderboard.
- If cloud image generation fails, fallback result still works.

#### US-4: Play 67 Challenge

As a player, I want to do the six-seven hand movement and see my reps counted in real time.

Acceptance criteria:

- App shows countdown.
- App shows live camera view.
- App shows green hand tracking overlay.
- App counts approximate valid reps.
- App shows timer and live score.
- App stores final score.
- App handles intermittent detection without crashing.

#### US-5: Play Emoji Face Match

As a player, I want to match emoji expressions as they enter a target zone.

Acceptance criteria:

- Emojis scroll into the moji zone.
- App evaluates expression at the scoring moment.
- App supports a fixed expression set.
- App gives hit/miss feedback.
- App tracks score and streak.
- App stores final score.

#### US-6: View Leaderboards

As a player, I want to see top scores so I can compete with others.

Acceptance criteria:

- Each game has separate leaderboard.
- Leaderboard shows name, score, and label.
- Leaderboard persists across restarts.
- Leaderboard appears after each round and optionally on home/idle screen.

### 5.2 Judge and Sponsor User Stories

#### US-7: Understand Technical System Quickly

As a judge, I want to understand the technical system without reading code.

Acceptance criteria:

- UI visibly shows face/hand/expression tracking.
- App clearly distinguishes local CV from cloud AI moments.
- Demo narrative can explain Raspberry Pi, local CV, AI APIs, and sponsor usage.

#### US-8: See Sponsor Relevance

As a sponsor judge, I want to see how sponsor products were used.

Acceptance criteria:

- Pika is used or clearly planned for generated video payoff.
- Emoji expression validation has local fallbacks and can accept a future cloud validator behind a feature flag.
- QNX is framed as embedded/control-plane architecture or demonstrated as a stretch subsystem.
- Sponsor dependencies have fallbacks.

### 5.3 Developer User Stories

#### US-9: Add or Modify Games Independently

As a developer, I want each game and sponsor integration to be isolated enough that four developers can work in parallel.

Acceptance criteria:

- Each game has its own native UI screen/component.
- Each game has its own game module.
- Shared camera, CV, leaderboard, storage, and AI clients are centralized.
- Game-specific logic does not fork the whole app.

#### US-10: Build Hackathon MVP Fast

As a developer, I want the implementation to avoid unnecessary abstractions while still staying organized.

Acceptance criteria:

- Simple repo layout.
- Explicit service boundaries.
- Minimal but real persistence.
- Clear local development setup.
- Easy fallback behavior.

---

## 6. System Architecture

### 6.1 High-Level Architecture

Moggie runs as a native local game shell on Raspberry Pi OS 64-bit Lite.

```text
+------------------------------------------------------------+
| HDMI Display                                                |
|                                                            |
| Native Fullscreen Moggie Game Shell                         |
| Python + Pygame / SDL2                                     |
| - Home screen                                              |
| - Player setup                                             |
| - Calibration screens                                      |
| - Game screens                                             |
| - Camera preview                                           |
| - Green CV overlays                                        |
| - Score reveal                                             |
| - Leaderboards                                             |
+---------------------------^--------------------------------+
                            |
                            | in-process event bus / queues
                            v
+------------------------------------------------------------+
| Application Services                                       |
|                                                            |
| - Game session manager                                     |
| - Game registry                                            |
| - Leaderboard service                                      |
| - Redis leaderboard cache                                  |
| - Storage service                                          |
| - AI job service                                           |
| - Sponsor integration service                              |
| - Config / feature flags                                   |
+---------------------------^--------------------------------+
                            |
                            | frames / structured CV events
                            v
+------------------------------------------------------------+
| Local CV Workers                                           |
|                                                            |
| - Camera capture                                           |
| - Face detection                                           |
| - Hand landmarks                                           |
| - Face landmarks                                           |
| - Expression heuristics                                    |
| - Gesture scoring                                          |
+---------------------------^--------------------------------+
                            |
                            | outbound local/internalS only
                            v
+------------------------------------------------------------+
| Optional Cloud AI Services                                 |
|                                                            |
| - Pika: generated video/media                              |
| - Midjourney MCP: caricature images                        |
| - LLM provider: labels, narration, loading text            |
+------------------------------------------------------------+
```

### 6.2 Runtime Processes

Recommended runtime model:

1. **Moggie native game process**
   - Main Python process.
   - Starts from `systemd` on boot.
   - Opens a fullscreen Pygame/SDL2 window on HDMI.
   - Owns navigation, rendering, keyboard input, score screens, and game UI.

2. **Camera/CV worker**
   - Runs in a thread or separate process.
   - Opens webcam.
   - Captures frames.
   - Downscales frames for CV.
   - Runs face/hand/landmark inference.
   - Emits structured events to the main game process.

3. **AI job worker**
   - Runs in a thread, process, or async task queue.
   - Handles outbound local/internalS calls to Pika, image-generation services, and LLM providers.
   - Publishes job status events.
   - Prevents cloud latency from blocking the game loop.

4. **Optional local debug/admin API**
   - Optional only.
   - May expose health, config, logs, or leaderboard state on `localhost`.
   - Must not be required for gameplay.

5. **Optional QNX service**
   - Stretch goal.
   - Handles timer, heartbeat, watchdog, or scoring-event validation.
   - Not required for MVP.

### 6.3 Local-First Principle

Critical gameplay must run locally:

- 67 timer;
- 67 rep counting;
- emoji scroll timing;
- expression snapshot timing;
- leaderboard writes;
- game state transitions;
- camera preview and overlays.

Cloud AI may be used for enhanced outputs, but core play must not fail if cloud APIs are slow or unavailable.

### 6.4 Structured Events and Direct Native Drawing

The CV layer should emit structured landmark and feature events. The native game UI should draw the camera frame and overlays directly using Pygame/SDL2 drawing primitives.

Example:

- CV worker detects hand landmarks;
- CV worker sends normalized landmark coordinates through an in-process queue;
- game state assigns landmarks to Player 1 or Player 2 zones;
- Pygame renderer draws green points/lines over the camera preview.

This avoids browser overhead and avoids repeatedly JPEG-encoding annotated frames.

### 6.5 Camera Ownership

The camera should be opened by exactly one component: the Camera/CV service.

The native UI should consume the latest frame from the Camera/CV service rather than opening the webcam independently.

Preferred pattern:

```text
CameraService owns webcam
  -> latest display frame
  -> latest CV frame
  -> latest landmarks/features
  -> GameRenderer draws preview and overlays
```

### 6.6 Failure Handling

Every external dependency should degrade gracefully.

Examples:

- no internet: local games still work;
- Pika failure: show static score screen;
- caricature failure: show original snapshot and aura score;
- cloud expression validation unavailable: use local expression heuristic;
- camera missing: show clear diagnostic;
- low CV confidence: show reposition instructions;
- SQLite write failure: show score but warn leaderboard unavailable.

## 7. Game Design Details

## 7.1 Mog Mirror

### 7.1.1 Concept

Two players compete for comedic "aura" or "mog energy." The system detects both faces, captures a snapshot, optionally generates stylized caricatures, assigns scores, and reveals a winner.

Avoid serious attractiveness language. Use absurd, humorous categories.

### 7.1.2 Player Count

- Minimum players: 2
- Maximum players: 2

### 7.1.3 Core Flow

```text
Home
  -> select Mog Mirror
  -> enter two names
  -> camera positioning screen
  -> wait for two faces
  -> countdown
  -> capture frame
  -> crop player faces
  -> calculate scores immediately
  -> generate labels/flavor text
  -> optionally request caricatures
  -> reveal results
  -> optionally request Pika clip
  -> save scores
  -> show leaderboard
```

### 7.1.4 Scoring

Score should be out of 100.

Suggested scoring approach:

- base random score within fun range, e.g. 65-98;
- add small deterministic modifiers from:
  - face detection confidence;
  - face centering;
  - smile/expression energy;
  - pose/framing;
- ensure results feel funny and not cruel;
- avoid low scores that make the demo uncomfortable unless obviously comedic.

Example labels:

- "Mall Final Boss"
- "LinkedIn Sigma"
- "Sleep-Deprived Rizzler"
- "Aura Merchant"
- "NPC Destroyer"
- "Caffeinated Main Character"
- "Berkeley Basement Maxxer"

### 7.1.5 AI Generation

Preferred:

- send each face crop/snapshot to image generation for caricature/stylized output;
- display generated images on reveal screen;
- optionally animate via Pika.

Fallback:

- display original crops;
- apply simple native UI filter or border;
- still display scores and labels.

### 7.1.6 UX Notes

Loading screen should be funny.

Example loading text:

- "Calibrating cheekbone liquidity..."
- "Measuring aura leakage..."
- "Consulting the mog oracle..."
- "Applying SPF 9000..."
- "Reconstructing final boss geometry..."

---

## 7.2 67 Challenge

### 7.2.1 Concept

The default 67 Challenge is a simultaneous **1v1 left-vs-right game**. Two players stand side-by-side in fixed screen halves and perform the "six-seven" hand movement as many times as possible in a fixed time window. The exact meme gesture does not need to be perfectly recognized. Approximate large alternating hand movement is sufficient.

The game should be implemented with one camera feed and one hand-landmark pipeline, not two independent camera or CV pipelines.

### 7.2.2 Player Count and Modes

Default:

- Minimum players: 2
- Maximum players: 2
- Mode: `versus`

Fallback:

- Solo mode should be available through config if four-hand tracking is too slow or unstable.

Configuration:

```bash
MOGGIE_67_MODE=versus        # versus | solo
MOGGIE_67_MAX_HANDS=4        # 4 for 1v1; 2 for solo/fallback
MOGGIE_67_ROUND_SECONDS=20
MOGGIE_67_REQUIRE_BOTH_HANDS=false
```

### 7.2.3 Fixed Half Zones

Use fixed camera-frame zones:

```text
P1 zone: normalized x < 0.5
P2 zone: normalized x >= 0.5
```

For every detected hand:

```text
palm_center = average(wrist, index_mcp, middle_mcp, ring_mcp, pinky_mcp)
zone = P1 if palm_center.x < 0.5 else P2
```

Each player owns an independent score counter and gesture state machine.

### 7.2.4 Core Flow

```text
Home
  -> select 67 Challenge
  -> enter two names
  -> camera positioning screen
  -> show fixed left/right zones
  -> ask both players to show hands
  -> countdown
  -> start timer
  -> track up to four hand landmarks from one frame
  -> assign hands to P1/P2 zones
  -> draw green hand overlays on both halves
  -> count valid reps independently
  -> end round
  -> show both scores + winner + labels
  -> save both scores
  -> show leaderboard
```

Solo fallback flow is the same but asks for one name, uses `MOGGIE_67_MAX_HANDS=2`, and only renders one score panel.

### 7.2.5 Performance Target

The green overlay is required and feasible. The expensive part is landmark inference, not drawing the overlay.

Target:

- camera capture: 640x480;
- CV processing resolution: 320x240 or similar;
- CV inference target: 10-15 FPS;
- Pygame renderer: as smooth as possible, target 30 FPS if feasible;
- hand detector max hands: 4 in versus mode, 2 in solo mode;
- overlay: green hand joints and skeleton lines.

Avoid:

- full hand segmentation masks;
- per-pixel effects;
- streaming fully annotated video if landmark events are enough;
- running hand tracking and face mesh simultaneously during the round;
- cloud validation inside the frame loop.

### 7.2.6 Hand Overlay

Native UI should draw:

- green circles for hand landmarks;
- green lines between hand joints;
- optional palm-center circle;
- left/right zone boundary;
- stale detection warning if no landmarks received recently;
- independent P1/P2 score panels.

CVService sends normalized coordinates in `[0, 1]` and includes the assigned player zone where possible.

Example event payload extension:

```json
{
  "hands": [
    {
      "handedness": "left",
      "assigned_player": "p1",
      "confidence": 0.89,
      "palm_center": { "x": 0.31, "y": 0.62 },
      "landmarks": []
    }
  ]
}
```

### 7.2.7 Rep Counting

Use approximate motion logic. Each player has an independent counter.

For each player, track:

- visible hands assigned to that player;
- palm centers;
- distance between the player's hands, if two are visible;
- horizontal movement;
- movement velocity;
- return to neutral.

Suggested state machine per player:

```text
NEUTRAL
  -> EXTENDING when hands move apart past threshold
  -> EXTENDED when max extension threshold reached
  -> RETURNING when hands move back toward neutral
  -> NEUTRAL when reset threshold reached; count +1
```

Anti-jitter rules:

- minimum confidence threshold;
- minimum extension distance;
- minimum velocity;
- cooldown after counted rep;
- ignore frames with stale landmarks;
- optionally require both hands visible for full confidence.

If only one hand is visible for a player, either pause that player's counting or use a lower-confidence fallback. Do not crash.

### 7.2.8 Round Duration

Default: 20 seconds.

Acceptable: 15-20 seconds if tuning shows 20 feels too long.

### 7.2.9 Labels

Example labels:

- "Certified 67 Technician"
- "Motion Blur Menace"
- "Berkeley Hand Physics Final Boss"
- "Insufficient Six, Excessive Seven"
- "Palm Velocity Demon"
- "Gesture Economy Major"

---

## 7.3 Emoji Face Match

### 7.3.1 Concept

The default Emoji Face Match mode is a simultaneous **1v1 expression game**. Two players stand side-by-side. Each player has an independent emoji lane and moji zone. When an emoji enters a player's moji zone, that player's face is evaluated against the target expression.

This mode is more fragile than 1v1 67 because it requires stable two-face detection and expression assignment. Therefore it must have a fast rollback path to alternating-turn or solo mode.

### 7.3.2 Player Count and Modes

Default:

- Minimum players: 2
- Maximum players: 2
- Mode: `versus`

Fallbacks:

- `alternating`: two players enter names, but only one player is active at a time.
- `solo`: one player plays the game.

Configuration:

```bash
MOGGIE_EMOJI_MODE=versus             # versus | alternating | solo
MOGGIE_EMOJI_MAX_FACES=2             # 2 for versus; 1 for solo/fallback
MOGGIE_EMOJI_ENABLE_TONGUE_OUT=false # tongue-out is harder; enable only if validation works
MOGGIE_EMOJI_USE_CLOUD_VALIDATION=false
MOGGIE_EMOJI_ROUND_SECONDS=30
```

### 7.3.3 Fixed Half Zones

Use fixed camera-frame zones:

```text
P1 zone: normalized x < 0.5
P2 zone: normalized x >= 0.5
```

For every detected face:

```text
face_center_x = bbox.x + bbox.w / 2
zone = P1 if face_center_x < 0.5 else P2
```

If two faces appear in the same zone, choose the largest/highest-confidence face for that zone and show a positioning warning.

### 7.3.4 Core Flow

```text
Home
  -> select Emoji Face Match
  -> enter two names
  -> camera positioning screen
  -> show fixed left/right zones
  -> detect one face per zone
  -> countdown
  -> spawn independent emoji sequences or mirrored sequence
  -> scroll emojis toward each player's moji zone
  -> evaluate each player's expression at scoring moments
  -> show hit/miss feedback per side
  -> update both scores and streaks
  -> end sequence
  -> show winner
  -> save both final scores
  -> show leaderboard
```

Alternating fallback uses the same scoring logic but activates one side at a time.

### 7.3.5 Supported Expressions

Use a fixed set that is feasible to detect.

Recommended initial set for 1v1:

1. Smile
2. Mouth open / surprised
3. Eyes closed
4. Wink
5. Neutral/deadpan

Stretch expressions:

6. Tongue out
7. Angry/frown

Expression detection strategies:

| Expression | Local heuristic | Cloud/VLM fallback | 1v1 reliability |
|---|---|---|---|
| Smile | mouth corner geometry | yes | good |
| Mouth open | mouth aspect ratio | yes | good |
| Eyes closed | eye aspect ratio | yes | good |
| Wink | one eye closed, one eye open | yes | medium |
| Neutral | low expression activation | yes | good |
| Tongue out | difficult locally | preferred | risky |
| Angry/frown | eyebrow/mouth heuristic if available | yes | medium/risky |

For MVP, use only smile, mouth open, eyes closed, wink, and neutral unless tongue-out validation is clearly working.

### 7.3.6 Scoring

Suggested:

- correct expression: +100;
- close expression: +50, optional;
- miss: +0;
- streak bonus: optional;
- final score: total points.

Each player has independent score and streak state.

### 7.3.7 Timing

Snapshot-based scoring is acceptable and preferred.

At the moment an emoji enters the moji zone:

- capture latest frame or face crop;
- assign face crop to player zone;
- compute local expression features;
- optionally send snapshot to vision-language API;
- determine hit/miss;
- show immediate feedback.

If cloud validation is too slow, local heuristic result should be shown immediately and cloud result can be ignored or used for debug/sponsor mode.

---

## 7.4 Shared 1v1 Zone Assignment Design

### 7.4.1 Fixed Half-Zone Rule

All simultaneous 1v1 games should use the same zone assignment rule:

```text
P1 zone: normalized x < MOGGIE_ZONE_SPLIT_X
P2 zone: normalized x >= MOGGIE_ZONE_SPLIT_X
```

Default:

```bash
MOGGIE_ZONE_SPLIT_X=0.5
```

This applies to:

- face boxes;
- hand landmarks;
- palm centers;
- face crops;
- expression scoring;
- UI overlays.

### 7.4.2 UI Zone Requirements

During calibration and gameplay, the UI should show:

- a vertical center divider;
- Player 1 name and score on the left;
- Player 2 name and score on the right;
- detection indicators per zone;
- warning if a player crosses zones or if both detected faces/hands are on one side.

### 7.4.3 CV Assignment Requirements

CV events should include assignment metadata where possible:

```json
{
  "assigned_player": "p1",
  "zone": "left",
  "assignment_confidence": 0.92
}
```

If assignment is ambiguous:

- keep the previous assignment for a short grace period if the tracked object is stable;
- otherwise mark it unassigned;
- do not count reps or expression hits for unassigned detections.

### 7.4.4 Feature-Flag Rollback Policy

Every simultaneous 1v1 feature should have a quick rollback flag.

Rollback examples:

```bash
# Make all games safer for demo
MOGGIE_DEFAULT_GAME_MODE=solo

# Keep Mog Mirror 1v1, but make 67 solo
MOGGIE_67_MODE=solo
MOGGIE_67_MAX_HANDS=2

# Keep Emoji Face Match two-player but alternate turns
MOGGIE_EMOJI_MODE=alternating
MOGGIE_EMOJI_MAX_FACES=1

# Disable expensive/cloud features
MOGGIE_ENABLE_PIKA=false
MOGGIE_EMOJI_USE_CLOUD_VALIDATION=false
```

Implementation agents should treat these flags as first-class product requirements, not optional polish.


## 8. Data Design

### 8.1 Persistence Strategy

Use SQLite as the durable source of truth and Redis as a read-through leaderboard cache.

Persist:

- players;
- game sessions;
- scores;
- leaderboard entries;
- optional media asset references.

Do not persist raw images/videos by default.

Redis should cache top leaderboard reads by game type. Score writes must update SQLite first and then invalidate the affected Redis cache key. If Redis is unavailable, the app should log the cache failure and fall back to SQLite without blocking gameplay.

Suggested Redis keys:

```text
leaderboard:mog_mirror:top10
leaderboard:sixty_seven:top10
leaderboard:emoji_face_match:top10
```

### 8.2 Environment Configuration

Suggested environment variables:

```bash
MOGGIE_ENV=development

MOGGIE_HOST=127.0.0.1
MOGGIE_PORT=8000

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

# Global 1v1 / rollback controls
MOGGIE_DEFAULT_GAME_MODE=versus          # versus | alternating | solo
MOGGIE_ENABLE_FIXED_HALF_ZONES=true
MOGGIE_ZONE_SPLIT_X=0.5
MOGGIE_SHOW_ZONE_DIVIDER=true
MOGGIE_ALLOW_MANUAL_START_OVERRIDE=true

# 67 Challenge controls
MOGGIE_67_MODE=versus                   # versus | solo
MOGGIE_67_MAX_HANDS=4                   # 4 for 1v1, 2 for solo
MOGGIE_67_ROUND_SECONDS=20
MOGGIE_67_REQUIRE_BOTH_HANDS=false
MOGGIE_67_MIN_CONFIDENCE=0.55
MOGGIE_67_REP_COOLDOWN_MS=350

# Emoji Face Match controls
MOGGIE_EMOJI_MODE=versus                # versus | alternating | solo
MOGGIE_EMOJI_MAX_FACES=2
MOGGIE_EMOJI_ROUND_SECONDS=30
MOGGIE_EMOJI_ENABLE_TONGUE_OUT=false
MOGGIE_EMOJI_USE_CLOUD_VALIDATION=false

MOGGIE_ENABLE_PIKA=false
MOGGIE_ENABLE_IMAGE_GENERATION=true
MOGGIE_ENABLE_MIDJOURNEY=true
MOGGIE_MIDJOURNEY_MCP_URL=https://mcp.midjourney.com/mcp
MOGGIE_MIDJOURNEY_TOKEN_STORE=~/.config/moggie/midjourney_oauth.json
MOGGIE_MIDJOURNEY_CLIENT_ID=
MOGGIE_MIDJOURNEY_CLIENT_SECRET=
MOGGIE_ENABLE_LLM_LABELS=false
MOGGIE_ENABLE_QNX_SUBSYSTEM=false
```

### 8.3 Database Tables

#### `players`

```sql
CREATE TABLE players (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

#### `game_sessions`

```sql
CREATE TABLE game_sessions (
    id TEXT PRIMARY KEY,
    game_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    metadata_json TEXT
);
```

Valid `game_type`:

- `mog_mirror`
- `sixty_seven`
- `emoji_face_match`

Valid `status`:

- `created`
- `calibrating`
- `countdown`
- `running`
- `scoring`
- `complete`
- `failed`
- `cancelled`

#### `scores`

```sql
CREATE TABLE scores (
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
```

#### `media_assets`

```sql
CREATE TABLE media_assets (
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

Valid `kind` examples:

- `snapshot`;
- `face_crop`;
- `caricature`;
- `pika_video`;
- `debug_frame`.

### 8.4 In-Memory Session State

Active game state should be kept in memory and persisted only at session milestones.

Example:

```json
{
  "session_id": "sess_123",
  "game_type": "sixty_seven",
  "status": "running",
  "players": [
    {
      "id": "player_1",
      "display_name": "Jonah"
    }
  ],
  "score": 12,
  "timer_remaining_ms": 8400,
  "cv_status": {
    "hands_detected": 2,
    "confidence": 0.81,
    "last_update_ms": 33
  }
}
```

### 8.5 Leaderboard Query

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

---

## 9. Interface Design

Because the main demo runs as a native Python/Pygame app on Raspberry Pi OS Lite, the primary interfaces are **internal Python service interfaces** and **in-process event schemas**, not HTTP/WebSocket interfaces.

A local debug/admin API may be added later, but the MVP should scaffold a native Python + Pygame/SDL2 fullscreen application. HTTP/WebSocket interfaces are optional debug/development tools only, not the runtime path.

## 9.1 Internal Event Bus

Use an in-process event bus or queue to move data between the CV worker, game session manager, renderer, and AI job worker.

Recommended primitives:

- `queue.Queue` for thread-based workers;
- `multiprocessing.Queue` if CV runs in a separate process;
- `asyncio.Queue` if the app uses an async architecture.

All events should use a consistent envelope.

### Event Envelope

```python
@dataclass
class AppEvent:
    type: str
    session_id: str | None
    timestamp_ms: int
    payload: dict
```

Equivalent JSON shape for logs/debugging:

```json
{
  "type": "event_type",
  "session_id": "sess_123",
  "timestamp_ms": 1780000000000,
  "payload": {}
}
```

## 9.2 Core Event Types

### `session_state`

```json
{
  "type": "session_state",
  "session_id": "sess_123",
  "timestamp_ms": 1780000000000,
  "payload": {
    "status": "running",
    "timer_remaining_ms": 14320,
    "scores": {
      "player_1": 9,
      "player_2": 7
    }
  }
}
```

### `cv.hand_landmarks`

```json
{
  "type": "cv.hand_landmarks",
  "session_id": "sess_123",
  "timestamp_ms": 1780000000000,
  "payload": {
    "frame_width": 640,
    "frame_height": 480,
    "hands": [
      {
        "handedness": "left",
        "assigned_zone": "p1_left",
        "confidence": 0.89,
        "landmarks": [
          { "id": 0, "x": 0.42, "y": 0.71, "z": 0.0 },
          { "id": 1, "x": 0.44, "y": 0.68, "z": 0.0 }
        ]
      }
    ]
  }
}
```

Coordinates should be normalized to `[0, 1]` relative to the camera frame.

### `cv.face_landmarks`

```json
{
  "type": "cv.face_landmarks",
  "session_id": "sess_123",
  "timestamp_ms": 1780000000000,
  "payload": {
    "faces": [
      {
        "face_id": "face_1",
        "assigned_zone": "p1_left",
        "confidence": 0.91,
        "bbox": {
          "x": 0.21,
          "y": 0.18,
          "w": 0.19,
          "h": 0.29
        },
        "expression_features": {
          "mouth_open": 0.12,
          "smile": 0.64,
          "left_eye_closed": 0.08,
          "right_eye_closed": 0.11
        }
      }
    ]
  }
}
```

### `score_update`

```json
{
  "type": "score_update",
  "session_id": "sess_123",
  "timestamp_ms": 1780000000000,
  "payload": {
    "player_zone": "p1_left",
    "score": 10,
    "delta": 1,
    "reason": "valid_rep"
  }
}
```

### `ai_job_update`

```json
{
  "type": "ai_job_update",
  "session_id": "sess_123",
  "timestamp_ms": 1780000000000,
  "payload": {
    "job_id": "job_456",
    "provider": "pika",
    "status": "running",
    "message": "Generating aura clip..."
  }
}
```

### `game_message`

```json
{
  "type": "game_message",
  "session_id": "sess_123",
  "timestamp_ms": 1780000000000,
  "payload": {
    "severity": "info",
    "message": "Show both hands"
  }
}
```

## 9.3 Internal Service Interfaces

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

### Image Generation Client

```python
class ImageGenerationClient:
    async def generate_caricature(
        self,
        image_bytes: bytes,
        prompt: str,
        metadata: dict
    ) -> "GeneratedImage":
        ...
```

### Video Generation Client

```python
class VideoGenerationClient:
    async def generate_reaction_video(
        self,
        image_bytes: bytes,
        prompt: str,
        metadata: dict
    ) -> "GeneratedVideo":
        ...
```

### Vision Validation Client

```python
class VisionValidationClient:
    async def classify_expression(
        self,
        image_bytes: bytes,
        target_expression: str,
        allowed_labels: list[str]
    ) -> "ExpressionValidationResult":
        ...
```

### Text Generation Client

```python
class TextGenerationClient:
    async def generate_label(
        self,
        game_type: str,
        score: int,
        context: dict
    ) -> str:
        ...
```

Implement mock/fallback clients first.

## 10. Component Design

## 10.1 Native UI Components

### `MoggieApp`

Top-level application object.

Responsibilities:

- initialize config, database, services, and Pygame;
- run the main game loop;
- route between screens;
- poll keyboard input;
- process events from CV and AI workers;
- render the active screen at target FPS;
- shut down workers cleanly.

### `ScreenManager`

Responsibilities:

- manage current screen;
- transition between home, setup, calibration, gameplay, score, leaderboard, and idle screens;
- centralize Escape/Home/back behavior.

### `HomeScreen`

Responsibilities:

- display Moggie title;
- show game cards;
- show leaderboard preview;
- route to player setup;
- optionally display sponsor/tech footer.

### `PlayerSetupScreen`

Responsibilities:

- render name input fields;
- validate player count;
- create local game session;
- navigate to calibration screen.

### `CalibrationScreen`

Responsibilities:

- show camera preview;
- show game-specific positioning instructions;
- show fixed left/right half zones;
- show face or hand detection status;
- allow start when detection is good enough;
- allow manual override if needed.

### `CameraPreviewRenderer`

Responsibilities:

- render latest camera frame to a Pygame surface;
- scale/crop to fit the HDMI layout;
- expose coordinate mapping for overlays.

### `HandOverlayRenderer`

Responsibilities:

- consume latest `cv.hand_landmarks` state;
- draw green hand skeletons;
- draw separate overlays for P1 and P2 zones;
- show stale-detection warning;
- scale normalized coordinates to the display area.

### `FaceOverlayRenderer`

Responsibilities:

- consume latest `cv.face_landmarks` state;
- draw face boxes;
- show assigned player zone;
- show expression/detection indicators.

### `GameShellRenderer`

Responsibilities:

- shared layout for game screens;
- timer display;
- score display;
- countdown overlay;
- zone divider line;
- cancel/back controls if needed.

### `MogMirrorScreen`

Responsibilities:

- show two-player detection;
- trigger capture/start;
- show loading/reveal;
- display generated or fallback images;
- show aura scores and winner.

### `SixtySevenScreen`

Responsibilities:

- show live preview;
- show fixed left/right zones;
- show green hand overlays for both players;
- show timer and both rep counts;
- show “valid rep” feedback per side;
- show final result.

### `EmojiFaceMatchScreen`

Responsibilities:

- render dual emoji lanes in versus mode;
- render one lane in solo/alternating fallback mode;
- render moji zones;
- show camera preview and face overlays;
- evaluate hit/miss events;
- show score and streak for each player.

### `ScoreRevealScreen`

Responsibilities:

- show final scores;
- show winner;
- show labels;
- show leaderboard rank;
- show generated media if available;
- provide “play again” and “home” actions.

### `LeaderboardScreen`

Responsibilities:

- fetch leaderboard from local service;
- render top scores;
- refresh after score submission.

### `IdleAttractScreen`

Optional but useful.

Responsibilities:

- cycle through game cards;
- show leaderboards;
- show generated clips if storage enabled;
- invite users to play.

## 10.2 Application Services

### `Config`

Responsibilities:

- parse environment variables;
- expose typed settings;
- provide defaults;
- own feature flags for rapid rollback.

### `GameRegistry`

Responsibilities:

- map game IDs to game classes;
- return game metadata;
- instantiate game sessions.

Example:

```python
GAME_REGISTRY = {
    "mog_mirror": MogMirrorGame,
    "sixty_seven": SixtySevenGame,
    "emoji_face_match": EmojiFaceMatchGame,
}
```

### `GameSessionManager`

Responsibilities:

- create sessions;
- manage in-memory state;
- start/cancel/complete sessions;
- process game events;
- persist final scores.

### `CameraService`

Responsibilities:

- open webcam;
- capture frames;
- expose latest display frame;
- expose downscaled CV frame;
- provide snapshots;
- handle camera errors.

### `CVService`

Responsibilities:

- run face detection;
- run hand landmark detection;
- run expression feature extraction;
- publish CV events;
- expose latest CV state to game modules.

### `LeaderboardService`

Responsibilities:

- create players;
- store scores;
- query leaderboards using Redis as a read-through cache;
- invalidate per-game Redis leaderboard cache keys after score writes;
- compute ranks.

### `RedisCacheService`

Responsibilities:

- connect to `MOGGIE_REDIS_URL`;
- provide JSON cache get/set/delete helpers;
- apply leaderboard cache TTLs;
- degrade gracefully when Redis is unavailable.

### `StorageService`

Responsibilities:

- decide whether to persist media;
- save images/videos when enabled;
- return media asset references;
- clean temp files.

### `AIJobService`

Responsibilities:

- execute cloud AI jobs asynchronously;
- track job status;
- publish AI job updates;
- enforce timeouts;
- fallback on failure.

### `SponsorIntegrationService`

Optional wrapper that reports which sponsor integrations are enabled and healthy.

Could expose this information inside an in-app diagnostics screen rather than an local/internal endpoint.

## 11. Suggested Repository Structure

Use a Python-first monorepo. Scaffold a native Python + Pygame/SDL2 fullscreen app for the MVP; do not scaffold a React/browser frontend.

```text
moggie/
  README.md
  .env.example
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
    main.py                         # starts native game shell
    config.py
    db.py
    models/
      player.py
      session.py
      score.py
      media_asset.py
    core/
      event_bus.py
      app_event.py
      screen_manager.py
      game_session_manager.py
      game_registry.py
    ui/
      theme.py
      layout.py
      fonts.py
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
      storage_service.py
      ai_job_service.py
      sponsor_integration_service.py
    games/
      base.py
      mog_mirror.py
      sixty_seven.py
      emoji_face_match.py
    cv/
      face_detection.py
      hand_landmarks.py
      expression_features.py
      sixty_seven_counter.py
      zone_assignment.py
    ai/
      base.py
      mock_clients.py
      pika_client.py
      image_generation_client.py
      text_generation_client.py
    util/
      ids.py
      time.py
      images.py
      logging.py
  tests/
    test_leaderboards.py
    test_sixty_seven_counter.py
    test_zone_assignment.py
    test_storage_service.py
    test_config.py
  docs/
    design.md
    implementation_plan.md
    sponsor_pitch.md
```

The `systemd/moggie.service` should boot directly into the game:

```ini
[Unit]
Description=Moggie native kiosk game
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/home/pi/moggie
ExecStart=/home/pi/moggie/.venv/bin/python -m app.main
Restart=always
RestartSec=2
EnvironmentFile=/home/pi/moggie/.env
User=pi

[Install]
WantedBy=multi-user.target
```

The service file may need display-related environment variables depending on the chosen SDL2 backend and Pi display configuration. The implementation agent should document the final working launch procedure in `README.md`.

## 12. User Interface Design

### 12.1 Visual Style

The UI should be:

- bold;
- high-contrast;
- readable from several feet away;
- playful;
- not too text-heavy;
- responsive to 1080p HDMI display;
- usable with keyboard and mouse.

Style direction:

- arcade/kiosk feel;
- big scores;
- large game cards;
- fast transitions;
- funny loading messages;
- visible CV overlays.

### 12.2 Screens

#### Home Screen

Shows:

- Moggie logo/title;
- three game cards;
- leaderboard preview;
- start prompt;
- optional sponsor/tech footer.

Game card copy:

- Mog Mirror: "Face off for maximum aura."
- 67 Challenge: "Hit the motion. Beat the clock."
- Emoji Face Match: "Make the face before it hits the zone."

#### Player Setup Screen

Shows:

- selected game name;
- one or two name fields;
- short game instructions;
- Start button.

Keyboard behavior:

- Enter advances;
- Escape returns home;
- Tab moves between fields.

#### Calibration Screen

Game-specific instructions:

Mog Mirror:

- "Stand shoulder-to-shoulder."
- "We need to see two faces."

67 Challenge:

- "Show both hands."
- "Keep your hands inside the frame."

Emoji Face Match:

- "Center your face."
- "Make sure your face is well lit."

Show detection indicators.

#### Countdown Screen

Large:

```text
3
2
1
GO
```

#### Mog Mirror Reveal

Show:

- two player panels;
- names;
- captured/generated images;
- aura scores;
- labels;
- winner banner;
- leaderboard update.

#### 67 Challenge Gameplay

Show:

- camera preview;
- green hand overlay;
- timer;
- live rep count;
- "valid rep" visual pulse;
- hands-not-detected warning.

#### Emoji Face Match Gameplay

Show:

- emoji lane;
- moji zone;
- camera preview;
- face overlay;
- current score;
- streak;
- hit/miss feedback.

#### Score Screen

Show:

- final score;
- label;
- rank if available;
- Play Again;
- Home.

#### Leaderboard

Show:

- top 10 per game;
- player name;
- score;
- label.

### 12.3 Idle Mode

When idle, cycle through:

- game cards;
- top leaderboards;
- generated videos if saved;
- "Step up and get mogged."

---

## 13. Assumptions and Dependencies

### 13.1 Hardware Assumptions

- Raspberry Pi 4.
- USB webcam.
- HDMI display.
- Keyboard.
- Optional mouse.
- Optional USB storage.

### 13.2 Software Assumptions

- Raspberry Pi OS 64-bit Lite is the locked primary target.
- Linux on Pi is primary target; QNX is a stretch/sponsor subsystem.
- Python 3.10+.
- Pygame / SDL2 for native fullscreen rendering.
- No standard desktop image for the primary demo build.
- No Chromium, browser kiosk mode, React, or Vite for the primary demo build.
- OpenCV available.
- MediaPipe or equivalent available; if MediaPipe install fails on Pi, use a fallback hand/face model or simpler OpenCV-based detection.
- SQLite available.

Recommended OS/performance choice:

- Use Raspberry Pi OS 64-bit Lite rather than switching to Ubuntu or another OS for the hackathon.
- Boot directly into the Moggie game with `systemd`.
- Focus performance effort on CV resolution, CV FPS, active cooling, and feature flags rather than OS replacement.

### 13.3 Internet Assumptions

- eduroam available.
- Outbound local/internalS works.
- P2P and inbound connections may fail.
- Cloud APIs can be slow or unavailable.

### 13.4 Performance Assumptions

Raspberry Pi 4 is constrained.

Targets:

- camera capture: 640x480;
- CV inference: 320x240 or similar;
- hand/face tracking: 10-15 FPS;
- native UI render loop: smooth enough for kiosk, target 30 FPS if possible;
- cloud calls: async and timeout-bound.

### 13.5 Privacy Assumptions

Default:

- store names and scores;
- do not store photos or videos;
- temporary images may be used for AI calls;
- media persistence is feature-flagged.

### 13.6 Development Assumptions

Team has four developers.

Recommended development split:

1. Initial shared platform:
   - repo setup;
   - native game shell/service event loop;
   - camera preview;
   - session management;
   - leaderboard.

2. Then one developer per game:
   - Mog Mirror;
   - 67 Challenge;
   - Emoji Face Match.

3. Dedicated sponsor/cache integration:
   - Redis leaderboard cache;
   - Midjourney MCP image generation;
   - Pika/Fal video generation;
   - AI job service and provider interfaces.

4. Shared integration/polish:
   - Pika;
   - QNX story;
   - UI polish;
   - demo script.

---

## 14. Implementation Priorities

### 14.1 MVP Order

Implement in this order:

1. Repo scaffold.
2. Raspberry Pi OS Lite launch path: `run_game.sh` and `systemd/moggie.service`.
3. Config and logging.
4. SQLite leaderboard.
5. Native Pygame app shell and home screen.
6. Player setup and keyboard input.
7. Camera preview inside native game shell.
8. Internal event bus between UI, game state, and CV worker.
9. 67 Challenge local hand tracking with green overlay.
10. 67 Challenge 1v1 versus scoring and leaderboard.
11. 67 Challenge solo fallback mode behind config flag.
12. Mog Mirror local face detection and fallback scoring.
13. Emoji Face Match basic UI and local expression heuristics.
14. Emoji Face Match 1v1 mode, with alternating-turn fallback behind config flag.
15. Sponsor integrations:
    - Redis;
    - Midjourney MCP;
    - Pika;
    - image generation;
    - LLM labels.
16. QNX stretch subsystem or sponsor-facing architecture notes.
17. Idle/attract mode and visual polish.

### 14.2 Definition of MVP Complete

MVP is complete when:

- native kiosk game launches locally from Raspberry Pi OS Lite;
- user can enter names;
- user can play all three games;
- leaderboards persist;
- 67 Challenge has live green hand overlay;
- Mog Mirror can produce scores even without generation;
- Emoji Face Match can score at least three expressions or uses a working fallback;
- app does not crash when cloud APIs are disabled;
- demo can run over localhost with outbound-only internet.

### 14.3 Definition of Polished Demo

Polished demo is complete when:

- UI looks cohesive;
- transitions are smooth enough;
- each game has clear instructions;
- generated labels are funny;
- at least one sponsor integration works visibly;
- app has fallback mode;
- leaderboard/idle mode makes booth feel alive;
- the team can explain architecture in under one minute.

---

## 15. Testing Strategy

### 15.1 Unit Tests

Prioritize tests for logic that can break silently:

- 67 rep-counting state machine;
- leaderboard sorting;
- storage modes;
- environment config;
- expression heuristic functions.

### 15.2 Manual Tests

Before demo, verify:

- camera opens on Pi;
- app launches in native fullscreen game shell;
- keyboard input works;
- each game can complete a round;
- leaderboard persists after restart;
- cloud APIs disabled still works;
- eduroam connection works for outbound local/internalS;
- no dependency requires inbound network access.

### 15.3 Stress Tests

Run:

- 10 consecutive 67 rounds;
- 10 leaderboard writes;
- repeated home/game transitions;
- camera unplug/replug if possible;
- cloud API timeout simulation.

---

## 16. Fallback Modes

### 16.1 No Internet

Available:

- home screen;
- name entry;
- camera preview;
- 67 Challenge;
- local Mog Mirror scores;
- local Emoji Face Match heuristics;
- SQLite leaderboards.

Unavailable or degraded:

- Pika clips;
- AI caricatures;
- cloud expression validation;
- LLM labels unless cached/fallback labels are used.

### 16.2 No Camera

Show diagnostic screen:

- "Camera not detected."
- Show configured camera index.
- Offer retry.
- Do not crash.

### 16.3 Low Pi Performance

Fallbacks:

- reduce CV resolution;
- reduce CV FPS;
- disable preview stream if needed;
- keep overlay but lower update rate;
- disable cloud polling while game is active.

### 16.4 AI API Failure

Fallbacks:

- show original image;
- use deterministic/random labels;
- skip generated video;
- show score immediately.

---

## 17. Glossary

### AI Job

A long-running request to an external AI provider, such as Pika video generation, image generation, or semantic vision validation.

### Aura Score

A comedic score out of 100 used in Mog Mirror. It should not be treated as a serious attractiveness or biometric score.

### CV

Computer vision. In this project, CV includes face detection, hand tracking, landmarks, expression heuristics, and gesture scoring.

### Face Crop

A cropped image region containing a player's face.

### Game Session

A single playthrough of one game, including players, state, timer, score, and final result.

### Kiosk Mode

A dedicated fullscreen game mode used for public booth interaction. In this design, kiosk mode means booting directly into the native Moggie game shell, not opening a desktop browser.

### Local-First Gameplay

The principle that core game logic works locally on the Raspberry Pi without requiring cloud services.

### Moji Zone

The scoring target area in Emoji Face Match.

### Mog Mirror

The two-player game that assigns comedic aura scores from camera snapshots.

### Moggie

The overall kiosk project.

### Pika Clip

A generated short video or animation created from a player image, caricature, or round result.

### QNX Subsystem

An optional real-time embedded subsystem used for sponsor relevance, timing, watchdog, or event control.

### Rep

One counted repetition in the 67 Challenge.

### Semantic Vision Validation

Using a vision-language model or API to answer high-level visual questions, such as whether the player is winking or sticking out their tongue.

### Storage Adapter

A service that decides whether media is discarded, saved locally, or saved to USB.

### internal event bus Event

A structured real-time message sent through the internal event bus to the native UI.

---

## 18. Instructions for Implementation-Planning Agent

Given this document, produce:

1. a concrete technical specification;
2. a repo/file implementation plan;
3. internal service interfaces and event schemas;
4. native UI component plan;
5. database migration/init plan;
6. game-specific task breakdown;
7. milestone order for a four-person hackathon team;
8. risk register with mitigations;
9. Codex-ready coding prompts or task tickets.

Do not ask clarifying questions unless the document contains a direct contradiction. Use the defaults specified here.

Prioritize:

1. working native kiosk game loop;
2. 67 Challenge with green hand overlay;
3. persistent leaderboards;
4. Mog Mirror fallback scoring;
5. Emoji Face Match basic expression scoring;
6. Pika/AI sponsor polish;
7. QNX stretch story or subsystem.

Use simple abstractions. Avoid overengineering. The final demo should be resilient, funny, and easy to explain.


---

## 19. Revision Notes for 1v1 Update

This revision changes Moggie from a mixed solo/1v1 kiosk into a **1v1-first party-game kiosk**.

Key changes:

- All three games are designed around simultaneous or near-simultaneous two-player competition.
- Players are assigned to fixed left/right camera zones.
- 67 Challenge supports simultaneous P1/P2 rep counting with up to four hands.
- Emoji Face Match supports simultaneous 1v1 with a fallback to alternating or solo mode.
- New config flags allow quick rollback during demo setup.
- Raspberry Pi OS 64-bit is the recommended default OS path; performance work should focus on resolution, frame rate, cooling, and feature flags rather than changing OS.

## 20. Revision Notes for Raspberry Pi OS Lite Native Runtime

This revision locks the main demo path to:

- Raspberry Pi OS 64-bit Lite;
- no standard desktop environment;
- no Chromium/browser kiosk mode;
- no React/Vite frontend;
- direct launch into the Moggie game shell using `systemd`;
- native Python/Pygame/SDL2 fullscreen rendering over HDMI;
- OpenCV/MediaPipe-style local CV in worker threads or processes;
- internal event bus instead of HTTP/WebSocket as the primary game interface.

The reason for this change is to reduce runtime overhead and setup complexity on the Pi 4. The project should feel like a dedicated appliance: power on the Pi and load directly into the Moggie game menu.
