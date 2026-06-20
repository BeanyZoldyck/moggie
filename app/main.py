from __future__ import annotations

import argparse
import logging

from app.config import ConfigError, MoggieConfig, load_config
from app.core.moggie_app import MoggieApp
from app.db import initialize_database
from app.util.logging import setup_logging

LOGGER = logging.getLogger(__name__)


class RuntimeDependencyError(RuntimeError):
    """Raised when a required runtime package is missing."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the Moggie kiosk application.")
    parser.add_argument(
        "--frames",
        type=int,
        default=None,
        help="Override app frame count for smoke tests. Use 0 to run until interrupted.",
    )
    return parser


def run_app(config: MoggieConfig, frames: int | None = None) -> None:
    try:
        MoggieApp(config).run(frames=frames)
    except ModuleNotFoundError as exc:
        if exc.name == "pygame":
            raise RuntimeDependencyError(
                "pygame is not installed; run `python3 -m pip install -e \".[dev]\"` "
                "inside the project environment."
            ) from exc
        raise


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
    try:
        run_app(config, frames=args.frames)
    except RuntimeDependencyError as exc:
        LOGGER.error("%s", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
