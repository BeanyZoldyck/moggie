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

DEFAULT_PROMPT = "A dramatic arcade score reveal, camera push in, glossy neon energy, fast celebration."


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Submit a live Fal/Pika image-to-video smoke test. "
            "By default sends an inline JPEG (same path as in-app recap generation). "
            "Use --image-url only when the URL is publicly reachable by fal.ai."
        )
    )
    parser.add_argument(
        "--image-file",
        type=Path,
        help="Local image file to inline as base64 (recommended for smoke tests).",
    )
    parser.add_argument(
        "--image-url",
        help="Remote image URL fal.ai must fetch. Omit unless you know the URL is public.",
    )
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
        if args.image_url:
            print("Using remote image URL (fal.ai must be able to download it)...")
            result = asyncio.run(client.generate_video(args.image_url, args.prompt, metadata))
        else:
            image_bytes, mime_type = _load_image_bytes(args.image_file)
            print(f"Using inline {mime_type} ({len(image_bytes)} bytes)...")
            result = asyncio.run(
                client.generate_video_from_image(image_bytes, mime_type, args.prompt, metadata)
            )
    except FalPikaError as exc:
        print(f"Fal/Pika smoke test failed: {exc}", file=sys.stderr)
        if "429" in str(exc):
            print(
                "HTTP 429 means fal.ai rate-limited this API key. Wait a minute and retry, "
                "or check usage/credits at https://fal.ai/dashboard.",
                file=sys.stderr,
            )
        if "file_download_error" in str(exc):
            print(
                "file_download_error means fal.ai could not fetch your image URL. "
                "Retry without --image-url so the smoke test inlines a local JPEG instead.",
                file=sys.stderr,
            )
        return 1
    except TimeoutError as exc:
        print(f"Fal/Pika smoke test timed out: {exc}", file=sys.stderr)
        return 1

    print("Fal/Pika smoke test succeeded")
    print(f"model: {result['model']}")
    print(f"request_id: {result['request_id']}")
    print(f"video_url: {result['video_url']}")
    return 0


def _load_image_bytes(image_file: Path | None) -> tuple[bytes, str]:
    if image_file is not None:
        data = image_file.read_bytes()
        suffix = image_file.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        if not data:
            raise FalPikaError(f"Image file is empty: {image_file}")
        return data, mime
    return _synthetic_jpeg_bytes(), "image/jpeg"


def _synthetic_jpeg_bytes() -> bytes:
    try:
        import cv2
        import numpy as np

        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :] = (28, 64, 120)
        cv2.putText(
            frame,
            "MOGGIE SMOKE",
            (24, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 220, 80),
            2,
            cv2.LINE_AA,
        )
        ok, encoded = cv2.imencode(".jpg", frame)
        if ok:
            return encoded.tobytes()
    except Exception:
        pass
    raise FalPikaError(
        "Could not build a synthetic JPEG for the smoke test. "
        "Install opencv-python or pass --image-file path/to/frame.jpg"
    )


def _print_status(job_id: str, status: str, metadata: dict[str, Any]) -> None:
    fal_status = metadata.get("fal_status")
    queue_position = metadata.get("queue_position")
    suffix = f" fal_status={fal_status}" if fal_status else ""
    if queue_position is not None:
        suffix += f" queue_position={queue_position}"
    print(f"{job_id}: {status}{suffix}")


if __name__ == "__main__":
    raise SystemExit(main())
