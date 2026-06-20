from __future__ import annotations


def scale_to_fit(source_size: tuple[int, int], target_size: tuple[int, int]) -> tuple[int, int]:
    source_w, source_h = source_size
    target_w, target_h = target_size
    scale = min(target_w / source_w, target_h / source_h)
    return int(source_w * scale), int(source_h * scale)
