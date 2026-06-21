# Moggie

Moggie is a native Python kiosk game for Raspberry Pi OS 64-bit Lite. It is designed to boot directly into a Pygame/SDL2 shell, use one USB webcam for local CV gameplay, persist scores in SQLite, and treat cloud AI integrations as optional asynchronous polish.

## Local Development

Requirements:

- Python 3.10-3.12. Use Python 3.12 on macOS; MediaPipe is not available for newer Python versions in all environments.
- A virtual environment
- Optional: Redis for leaderboard cache development
- Optional: webcam for camera smoke tests

### MacBook Setup From Scratch

These steps are for a clean MacBook checkout with local webcam tracking, MediaPipe Hands, FaceMesh, and expression scoring enabled.

1. Install Python 3.12 and Git if needed:

```bash
brew install python@3.12 git
```

2. Clone the repo and use the Mac testing branch:

```bash
git clone git@github.com:BeanyZoldyck/moggie.git
cd moggie
git checkout macbook-testing
```

3. Create a Python 3.12 virtual environment. Do not use Python 3.13 or 3.14; current MediaPipe packages either do not install there or no longer expose the legacy `mp.solutions.face_mesh` / `mp.solutions.hands` API used by this app.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -c "import mediapipe as mp; print(mp.__version__, hasattr(mp, 'solutions'))"
```

The expected MediaPipe check is `0.10.14 True`.

4. Run the database initializer:

```bash
./scripts/init_db.sh
```

5. Grant camera access to the terminal app you use. On macOS, open System Settings -> Privacy & Security -> Camera and enable Terminal, iTerm, or VS Code. If OpenCV says camera access was denied, reset the prompt and rerun from the same terminal app:

```bash
tccutil reset Camera
```

6. Verify camera frames first:

```bash
python scripts/smoke_test_camera.py
```

7. Verify MediaPipe Hands and FaceMesh/expression tracking:

```bash
python scripts/smoke_test_cv.py
```

Successful output should show:

```text
MediaPipe: 0.10.14
hand_backend=mediapipe face_backend=mediapipe face_enabled=True
Hands: Hand landmark detector tracking up to 4 hands.
Frame 1: hands=... faces=...
```

8. Start the app:

```bash
python -m app.main
```

In development mode, `python -m app.main` opens the windowed native shell. Use `python -m app.main --frames 3` for a short startup smoke test that exits cleanly.

If you need a temporary non-MediaPipe fallback while debugging camera or install issues:

```bash
MOGGIE_HAND_TRACKING_BACKEND=simple MOGGIE_FACE_TRACKING_BACKEND=cascade python -m app.main
```

That fallback uses rough hand contours and face boxes only; it does not provide FaceMesh landmarks or expression scoring.

## Demo Fallback Presets

Preset files live in `config_presets/` and can be used directly on a laptop or copied into `/etc/moggie/moggie.env` for the Pi systemd service.

```bash
./scripts/run_with_preset.sh cloud_disabled -- --frames 3
./scripts/run_with_preset.sh booth_safe
./scripts/run_with_preset.sh sixty_seven_solo
./scripts/run_with_preset.sh emoji_alternating
./scripts/run_with_preset.sh emoji_solo
```

- `cloud_disabled`: turns off Redis, Midjourney, Pika/Fal, LLM labels, cloud expression validation, and generated media saving. Local camera gameplay and SQLite leaderboards still work.
- `booth_safe`: production fullscreen plus the cloud-disabled path and conservative 640x480 camera / 320x240 CV settings.
- `sixty_seven_solo`: reduces 67 Challenge to one player and two tracked hands.
- `emoji_alternating`: keeps Emoji Face Match as a two-player flow but detects one face at a time.
- `emoji_solo`: last-resort single-player Emoji Face Match.

Attract mode is enabled by default. After `MOGGIE_IDLE_TIMEOUT_SECONDS` on the home screen, the kiosk cycles game cards, top scores, and recent generated media when `MOGGIE_SAVE_GENERATED_MEDIA=true`.

## Useful Scripts

```bash
./scripts/dev.sh
./scripts/init_db.sh
./scripts/smoke_test_camera.py
./scripts/auth_midjourney.py
./scripts/run_game.sh
./scripts/run_with_preset.sh booth_safe
```

## Midjourney Setup

Mog Mirror can use Midjourney's MCP server for async caricatures when `MOGGIE_ENABLE_IMAGE_GENERATION=true` and `MOGGIE_ENABLE_MIDJOURNEY=true`. Run `scripts/auth_midjourney.py` during setup over SSH or an admin terminal, complete OAuth on a phone or laptop, and paste the final callback URL back into the script.

The script writes token state to `MOGGIE_MIDJOURNEY_TOKEN_STORE`, defaulting to `~/.config/moggie/midjourney_oauth.json`, with `0600` permissions. The kiosk service later uses that token store without opening a browser. Missing or expired auth only fails the AI job; the local score reveal still completes.

## Raspberry Pi Launch Notes

The primary target is Raspberry Pi OS 64-bit Lite with no desktop environment. The service unit in `systemd/moggie.service` launches:

```bash
python -m app.main
```

Install system dependencies with `scripts/install_pi_lite_deps.sh`, then install the service with `scripts/install_systemd_service.sh`. The installer renders `/etc/systemd/system/moggie.service` with the current clone path, the current virtualenv Python, and the invoking user/group.

Recommended Pi setup:

```bash
sudo apt-get update
sudo apt-get install -y git
sudo mkdir -p /opt
sudo chown "$USER":"$USER" /opt
git clone git@github.com:BeanyZoldyck/moggie.git /opt/moggie
cd /opt/moggie
./scripts/install_pi_lite_deps.sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
./scripts/init_db.sh
./scripts/smoke_test_camera.py
./scripts/install_systemd_service.sh
sudo systemctl start moggie.service
```

Systemd reads `/etc/moggie/moggie.env` if present. The installer creates it from `config_presets/booth_safe.env` on first install. To switch demo mode:

```bash
sudo cp config_presets/cloud_disabled.env /etc/moggie/moggie.env
sudo systemctl restart moggie.service
```

Check service status and logs:

```bash
sudo systemctl status moggie.service
journalctl -u moggie.service -f
```

## Camera Troubleshooting

The kiosk retries a missing camera every `MOGGIE_CAMERA_RETRY_SECONDS` and shows the diagnostic in the home preview. If a camera opens and then drops frames, Moggie keeps the last good frame and continues polling.

Use these checks before judging:

```bash
v4l2-ctl --list-devices
MOGGIE_CAMERA_INDEX=0 ./scripts/smoke_test_camera.py
MOGGIE_CAMERA_INDEX=1 ./scripts/smoke_test_camera.py
```

If the preview is blank, unplug/replug the webcam, rerun the smoke test with the discovered index, update `/etc/moggie/moggie.env`, and restart the service.

### QNX Raspberry Pi Camera Module 3

On the QNX Raspberry Pi 5 image, use the QNX CamAPI backend instead of `cv2.VideoCapture`:

```bash
gcc native/moggi_camgrab.c -o moggi_camgrab -lcamapi
./moggi_camgrab
MOGGIE_CAMERA_BACKEND=qnx ./scripts/smoke_test_camera.py
MOGGIE_CAMERA_BACKEND=qnx python -m app.main
```

The helper streams NV12 frames from the CamAPI viewfinder into Python. Pygame display still needs to run on the Pi HDMI console.

## Judging Day Runbook

1. Boot the Pi and confirm the idle attract screen appears after the home screen sits idle.
2. Run one Mog Mirror round and confirm scores land on the leaderboard.
3. Run 10 consecutive 67 Challenge rounds from home to score reveal and back. If tracking drops or FPS is poor, copy `config_presets/sixty_seven_solo.env` into `/etc/moggie/moggie.env` and restart.
4. Run Emoji Face Match. If two-face scoring is unreliable, switch to `emoji_alternating.env`; if that still fails, switch to `emoji_solo.env`.
5. If venue network or cloud auth is unstable, switch to `cloud_disabled.env` or `booth_safe.env`. The local demo path should still play and persist scores.
6. Keep `journalctl -u moggie.service -f` open on an SSH session during setup. During judging, leave the kiosk fullscreen.

Demo reset:

```bash
sudo systemctl stop moggie.service
rm -f data/moggie.sqlite
./scripts/init_db.sh
sudo systemctl start moggie.service
```

Generated media reset, when media saving has been enabled:

```bash
rm -rf media/*
```

Stress-test checklist:

- 10 back-to-back 67 Challenge rounds complete without a crash.
- 10 home -> game -> score reveal -> leaderboard -> home transitions complete without a crash.
- Camera unplug/replug shows a diagnostic, then recovers after restart or retry.
- Cloud-disabled preset completes all local games with Redis and cloud services unavailable.
- Text remains readable on 1080p HDMI from booth distance.

## Project Layout

- `app/main.py`: application entrypoint
- `app/core/moggie_app.py`: Pygame app loop
- `app/config.py`: typed environment configuration
- `app/db.py`: SQLite initialization
- `app/core/`: event bus, game registry, session/screen managers
- `app/services/`: camera, CV, leaderboard, storage, Redis, AI, sponsor integration boundaries
- `app/games/`: game modules
- `app/cv/`: local CV helpers and heuristics
- `app/ai/`: cloud/mock AI client interfaces
- `scripts/`: local, Pi, systemd, DB, and camera utilities
- `tests/`: foundation tests
