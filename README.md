# Moggie

Moggie is a native Python kiosk game for Raspberry Pi OS 64-bit Lite. It is designed to boot directly into a Pygame/SDL2 shell, use one USB webcam for local CV gameplay, persist scores in SQLite, and treat cloud AI integrations as optional asynchronous polish.

## Local Development

Requirements:

- Python 3.10+
- A virtual environment
- Optional: Redis for leaderboard cache development
- Optional: webcam for camera smoke tests

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
python -m app.main
```

In development mode, `python -m app.main` opens the windowed native shell. Use `python -m app.main --frames 3` for a short startup smoke test that exits cleanly.

## Useful Scripts

```bash
./scripts/dev.sh
./scripts/init_db.sh
./scripts/smoke_test_camera.py
./scripts/auth_midjourney.py
./scripts/run_game.sh
```

## Midjourney Setup

Mog Mirror can use Midjourney's MCP server for async caricatures when `MOGGIE_ENABLE_IMAGE_GENERATION=true` and `MOGGIE_ENABLE_MIDJOURNEY=true`. Run `scripts/auth_midjourney.py` during setup over SSH or an admin terminal, complete OAuth on a phone or laptop, and paste the final callback URL back into the script.

The script writes token state to `MOGGIE_MIDJOURNEY_TOKEN_STORE`, defaulting to `~/.config/moggie/midjourney_oauth.json`, with `0600` permissions. The kiosk service later uses that token store without opening a browser. Missing or expired auth only fails the AI job; the local score reveal still completes.

## Raspberry Pi Launch Notes

The primary target is Raspberry Pi OS 64-bit Lite with no desktop environment. The service unit in `systemd/moggie.service` launches:

```bash
python -m app.main
```

Install system dependencies with `scripts/install_pi_lite_deps.sh`, then install the service with `scripts/install_systemd_service.sh`. The service expects the repository at `/opt/moggie` by default; adjust the unit if the deploy path differs.

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
