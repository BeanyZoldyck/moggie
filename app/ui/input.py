from __future__ import annotations


def normalize_name(value: str, fallback: str = "Player") -> str:
    cleaned = " ".join(value.strip().split())
    return cleaned[:24] if cleaned else fallback
