from __future__ import annotations

MAX_NAME_LENGTH = 24


def normalize_name(value: str, fallback: str = "Player") -> str:
    cleaned = " ".join(value.strip().split())
    return cleaned[:MAX_NAME_LENGTH] if cleaned else fallback


def is_printable_text(value: str) -> bool:
    return bool(value) and value.isprintable() and value not in {"\r", "\n", "\t"}
