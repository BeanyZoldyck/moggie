from __future__ import annotations

import argparse
import logging
import time

from app.config import ConfigError, MoggieConfig, load_config
from app.db import initialize_database
from app.util.logging import setup_logging

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the Moggie kiosk application.")
    parser.add_argument(
        "--frames",
        type=int,
        default=None,
        help="Override placeholder loop frame count. Use 0 to run until interrupted.",
    )
    return parser


def run_placeholder_loop(config: MoggieConfig, frames: int | None = None) -> None:
    target_frames = config.placeholder_frames if frames is None else max(0, frames)
    LOGGER.info(
        "Starting Moggie placeholder loop env=%s fullscreen=%s size=%sx%s db=%s",
        config.env,
        config.fullscreen,
        config.window_width,
        config.window_height,
        config.db_path,
    )

    frame = 0
    while target_frames == 0 or frame < target_frames:
        frame += 1
        LOGGER.debug("Placeholder frame %s", frame)
        time.sleep(1 / 30)

    LOGGER.info("Moggie placeholder loop exited after %s frame(s)", frame)


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config()
    except ConfigError as exc:
        setup_logging("development")
        LOGGER.error("Invalid Moggie configuration: %s", exc)
        return 2

    setup_logging(config.env)
    initialize_database(config.db_path)
    run_placeholder_loop(config, frames=args.frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
