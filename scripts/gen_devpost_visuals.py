#!/usr/bin/env python3
"""
Generate Devpost visuals for moggie using fal.ai.

Produces:
  devpost/banner.png         — wide hero banner (1920×1080)
  devpost/kiosk_moment.png  — dramatic kiosk face-off still (1280×720)
  devpost/recap_still.png   — bowling-alley celebration moment (1280×720)
  devpost/recap_video.mp4   — animated recap clip from recap_still

Usage:
  .venv/bin/python scripts/gen_devpost_visuals.py

Requires FAL_KEY in .env or environment.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import load_config

OUT = ROOT / "devpost"
OUT.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# fal.ai helpers
# ---------------------------------------------------------------------------

def _req(url: str, *, method: str, key: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload else None
    req = Request(url, data=body, method=method, headers={
        "Authorization": f"Key {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _poll(status_url: str, key: str, *, interval: float = 3.0, timeout: float = 180.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(f"timed out polling {status_url}")
        result = _req(f"{status_url}?logs=1", method="GET", key=key)
        status = result.get("status", "")
        pos = result.get("queue_position")
        suffix = f" (queue {pos})" if pos is not None else ""
        print(f"  … {status}{suffix}")
        if status == "COMPLETED":
            return result
        if status in {"FAILED", "ERROR", "CANCELLED"}:
            raise RuntimeError(f"job {status}: {result.get('error')}")
        time.sleep(interval)


def _run_model(model: str, payload: dict, key: str, *, label: str) -> dict:
    base = "https://queue.fal.run"
    print(f"\n→ {label}")
    sub = _req(f"{base}/{model}", method="POST", key=key, payload=payload)
    rid = sub.get("request_id")
    status_url = sub.get("status_url") or f"{base}/{model}/requests/{rid}/status"
    response_url = sub.get("response_url") or f"{base}/{model}/requests/{rid}/response"
    _poll(status_url, key)
    return _req(response_url, method="GET", key=key)


def _extract_image_url(result: dict) -> str | None:
    for key in ("images", "image"):
        v = result.get(key)
        if isinstance(v, list) and v:
            item = v[0]
            return item.get("url") if isinstance(item, dict) else (item if isinstance(item, str) else None)
        if isinstance(v, dict):
            return v.get("url")
    for key in ("image_url", "url"):
        v = result.get(key)
        if isinstance(v, str):
            return v
    return None


def _extract_video_url(result: dict) -> str | None:
    for key in ("video", "output", "file"):
        v = result.get(key)
        if isinstance(v, dict):
            return v.get("url")
    for key in ("video_url", "url"):
        v = result.get(key)
        if isinstance(v, str):
            return v
    videos = result.get("videos")
    if isinstance(videos, list) and videos:
        item = videos[0]
        return item.get("url") if isinstance(item, dict) else item
    return None


def _download(url: str, dest: Path) -> None:
    with urlopen(url, timeout=60) as r:
        dest.write_bytes(r.read())
    print(f"  ✓ saved → {dest.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Image prompts
# ---------------------------------------------------------------------------

PROMPTS = {
    "banner": {
        "prompt": (
            "Wide cinematic still for an arcade kiosk called 'moggie'. "
            "Two people stand at a glowing neon arcade cabinet, faces illuminated by the screen, "
            "their facial features scanned by glowing green holographic laser lines. "
            "Between them a vertical dividing neon line splits their zones. "
            "Above them large arcade score panels show '91' and '74' in retro digital numerals. "
            "The cabinet is sleek and modern, set in a dark bowling alley with neon signs. "
            "Dramatic top-down spotlight. Deep blacks. Neon greens and electric pinks. "
            "Cinematic wide angle. Photorealistic. Film grain."
        ),
        "image_size": "landscape_16_9",
        "out": "banner.png",
    },
    "kiosk_moment": {
        "prompt": (
            "Close-up dramatic still: two friends facing an arcade screen, "
            "both staring forward with intense focus. "
            "Holographic scan lines sweep across their faces from the screen glow. "
            "Neon score meters climb in the foreground — '91 MOG SCORE' and '74 MOG SCORE' "
            "rendered in glowing arcade font with neon halos. "
            "Background: dark arcade hall, blurred neon bokeh. "
            "Cinematic lighting. Moody. Photorealistic faces. Shallow depth of field. "
            "The vibe: this is the most important thing that has ever happened."
        ),
        "image_size": "landscape_16_9",
        "out": "kiosk_moment.png",
    },
    "recap_still": {
        "prompt": (
            "Arcade celebration freeze-frame: a person's face frozen in pure shock and joy, "
            "a giant golden trophy materialising from thin air beside them. "
            "Confetti rains from above in the exact colours of neon green and electric pink. "
            "A divine beam of golden light descends from above onto their face. "
            "Behind them a massive cheesy scoreboard graphic reads 'BOOTH FINAL BOSS — 91'. "
            "Neon aura rings orbit their head. Lens flares streak across the frame. "
            "The aesthetic: bowling alley strike screen at 11pm — completely sincere, "
            "deeply committed to celebrating something mundane as if it were cosmic. "
            "Late-90s neon arcade aesthetic. Photorealistic face. Garish and glorious."
        ),
        "image_size": "landscape_16_9",
        "out": "recap_still.png",
    },
}

VIDEO_PROMPT = (
    "A single divine golden beam of light slams down from above onto the person's face. "
    "Their face slowly begins to glow. Neon aura rings orbit their head. "
    "Confetti in gold and green erupts from both sides. "
    "The scoreboard behind them pulses: 'BOOTH FINAL BOSS — 91'. "
    "Camera pushes in slowly — reverential, almost afraid. "
    "The energy of a bowling alley strike video at 11pm on a Tuesday. "
    "Hammy, sincere, deeply committed to the bit."
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    config = load_config()
    key = config.fal_key
    if not key:
        print("ERROR: FAL_KEY not set in .env", file=sys.stderr)
        return 1

    # --- Generate images via FLUX ---
    recap_url = None
    for name, spec in PROMPTS.items():
        dest = OUT / spec["out"]
        result = _run_model(
            "fal-ai/flux/schnell",
            {
                "prompt": spec["prompt"],
                "image_size": spec["image_size"],
                "num_images": 1,
                "num_inference_steps": 4,
                "enable_safety_checker": False,
            },
            key,
            label=f"{name} ({spec['out']})",
        )
        url = _extract_image_url(result)
        if not url:
            print(f"  ✗ no image URL in result: {result}")
            continue
        _download(url, dest)
        if name == "recap_still":
            recap_url = url

    # --- Animate the recap still into a video via Pika ---
    if recap_url:
        print(f"\n→ recap_video.mp4  (Pika image-to-video from recap_still)")
        model = config.pika_model  # fal-ai/pika/v2.2/image-to-video
        result = _run_model(
            model,
            {"image_url": recap_url, "prompt": VIDEO_PROMPT},
            key,
            label=f"recap_video ({model})",
        )
        url = _extract_video_url(result)
        if url:
            _download(url, OUT / "recap_video.mp4")
        else:
            print(f"  ✗ no video URL in result: {result}")
    else:
        print("\n⚠  skipping video — recap_still image URL not available")

    print(f"\n✓ done — assets in {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
