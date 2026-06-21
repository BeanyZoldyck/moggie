#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.fal_pika_client import FalPikaClient, FalPikaError
from app.config import load_config


DEFAULT_IMAGE_URL = "https://storage.googleapis.com/falserverless/model_tests/pika/cat.png"
DEFAULT_PROMPT = "A dramatic arcade score reveal, camera push in, glossy neon energy, fast celebration."


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a live Fal/Pika image-to-video smoke test.")
    parser.add_argument("--image-url", default=DEFAULT_IMAGE_URL)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--model", default="")
    parser.add_argument("--duration", default="")
    parser.add_argument("--resolution", default="")
    parser.add_argument("--aspect-ratio", default="")
    args = parser.parse_args()

    config = load_config()
    api_key = config.fal_key
    if not api_key:
        print("Missing FAL_KEY. Add it to .env or export it before running this smoke test.", file=sys.stderr)
        return 2

    client = FalPikaClient(
        api_key=api_key,
        model=args.model or config.pika_model,
        timeout_seconds=config.ai_timeout_seconds,
        poll_interval_seconds=config.ai_poll_interval_seconds,
        on_status=_print_status,
    )
    metadata: dict[str, Any] = {"job_id": "pika_smoke", "kind": "pika.smoke_test"}
    for arg_name, metadata_key in (
        ("duration", "duration"),
        ("resolution", "resolution"),
        ("aspect_ratio", "aspect_ratio"),
    ):
        value = getattr(args, arg_name)
        if value:
            metadata[metadata_key] = value

    try:
        result = asyncio.run(client.generate_video(args.image_url, args.prompt, metadata))
    except FalPikaError as exc:
        print(f"Fal/Pika smoke test failed: {exc}", file=sys.stderr)
        return 1
    except TimeoutError as exc:
        print(f"Fal/Pika smoke test timed out: {exc}", file=sys.stderr)
        return 1

    print("Fal/Pika smoke test succeeded")
    print(f"model: {result['model']}")
    print(f"request_id: {result['request_id']}")
    print(f"video_url: {result['video_url']}")
    return 0


def _print_status(job_id: str, status: str, metadata: dict[str, Any]) -> None:
    fal_status = metadata.get("fal_status")
    queue_position = metadata.get("queue_position")
    suffix = f" fal_status={fal_status}" if fal_status else ""
    if queue_position is not None:
        suffix += f" queue_position={queue_position}"
    print(f"{job_id}: {status}{suffix}")


if __name__ == "__main__":
    raise SystemExit(main())
