from __future__ import annotations


def split_zones(width: int, split_x: float = 0.5) -> tuple[tuple[int, int], tuple[int, int]]:
    split_px = int(width * split_x)
    return (0, split_px), (split_px, width)
