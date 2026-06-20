from __future__ import annotations

import logging


def setup_logging(env: str) -> None:
    level = logging.DEBUG if env == "development" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
