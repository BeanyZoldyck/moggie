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

In development mode, `python -m app.main` runs a short placeholder loop and exits cleanly. Use `MOGGIE_PLACEHOLDER_FRAMES=0 ./scripts/run_game.sh` when you want the placeholder process to keep running like the kiosk service.

## Useful Scripts

```bash
./scripts/dev.sh
./scripts/init_db.sh
./scripts/smoke_test_camera.py
./scripts/run_game.sh
```

## Raspberry Pi Launch Notes

The primary target is Raspberry Pi OS 64-bit Lite with no desktop environment. The service unit in `systemd/moggie.service` launches:

```bash
python -m app.main
```

Install system dependencies with `scripts/install_pi_lite_deps.sh`, then install the service with `scripts/install_systemd_service.sh`. The service expects the repository at `/opt/moggie` by default; adjust the unit if the deploy path differs.

## Project Layout

- `app/main.py`: application entrypoint and placeholder loop
- `app/config.py`: typed environment configuration
- `app/db.py`: SQLite initialization
- `app/core/`: event bus, game registry, session/screen managers
- `app/services/`: camera, CV, leaderboard, storage, Redis, AI, sponsor integration boundaries
- `app/games/`: game modules
- `app/cv/`: local CV helpers and heuristics
- `app/ai/`: cloud/mock AI client interfaces
- `scripts/`: local, Pi, systemd, DB, and camera utilities
- `tests/`: foundation tests
