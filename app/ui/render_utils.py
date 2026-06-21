from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ui import theme


ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets"
_IMAGE_CACHE: dict[str, Any] = {}
_SCALED_IMAGE_CACHE: dict[tuple[str, tuple[int, int]], Any] = {}


def scale_to_fit(source_size: tuple[int, int], target_size: tuple[int, int]) -> tuple[int, int]:
    source_w, source_h = source_size
    target_w, target_h = target_size
    scale = min(target_w / source_w, target_h / source_h)
    return int(source_w * scale), int(source_h * scale)


def load_asset_image(pygame: Any, filename: str) -> Any | None:
    if filename in _IMAGE_CACHE:
        return _IMAGE_CACHE[filename]

    path = ASSET_ROOT / filename
    if not path.exists():
        return None

    image = pygame.image.load(str(path))
    try:
        image = image.convert_alpha()
    except pygame.error:
        image = image.convert()
    _IMAGE_CACHE[filename] = image
    return image


def scaled_asset_image(pygame: Any, filename: str, size: tuple[int, int]) -> Any | None:
    if size[0] <= 0 or size[1] <= 0:
        return None
    key = (filename, size)
    if key in _SCALED_IMAGE_CACHE:
        return _SCALED_IMAGE_CACHE[key]

    image = load_asset_image(pygame, filename)
    if image is None:
        return None
    scaled = pygame.transform.smoothscale(image, size)
    _SCALED_IMAGE_CACHE[key] = scaled
    return scaled


def draw_centered_asset(
    pygame: Any,
    surface: Any,
    filename: str,
    center: tuple[int, int],
    size: tuple[int, int],
) -> Any | None:
    image = scaled_asset_image(pygame, filename, size)
    if image is None:
        return None
    rect = image.get_rect(center=center)
    surface.blit(image, rect)
    return rect


@dataclass(frozen=True)
class FontSet:
    masthead: Any
    title: Any
    card_title: Any
    body: Any
    small: Any
    mono: Any


def build_fonts(pygame: Any) -> FontSet:
    pygame.font.init()
    title_font = pygame.font.match_font("impact")
    body_font = pygame.font.match_font("freesansbold") or pygame.font.get_default_font()
    mono_font = pygame.font.match_font("menlo") or pygame.font.match_font("dejavusansmono")
    return FontSet(
        masthead=pygame.font.Font(title_font, 86),
        title=pygame.font.Font(title_font, 54),
        card_title=pygame.font.Font(title_font, 36),
        body=pygame.font.Font(body_font, 24),
        small=pygame.font.Font(body_font, 17),
        mono=pygame.font.Font(mono_font or body_font, 20),
    )


def inset_rect(rect: Any, dx: int, dy: int | None = None) -> Any:
    if dy is None:
        dy = dx
    return rect.inflate(-2 * dx, -2 * dy)


def draw_text(
    surface: Any,
    text: str,
    font: Any,
    color: tuple[int, int, int],
    position: tuple[int, int],
    *,
    anchor: str = "topleft",
    max_width: int | None = None,
) -> Any:
    rendered_text = _fit_text(text, font, max_width) if max_width else text
    image = font.render(rendered_text, True, color)
    rect = image.get_rect()
    setattr(rect, anchor, position)
    surface.blit(image, rect)
    return rect


def draw_wrapped_text(
    surface: Any,
    text: str,
    font: Any,
    color: tuple[int, int, int],
    rect: Any,
    *,
    line_gap: int = 7,
    max_lines: int = 3,
) -> Any:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join([*current, word])
        if font.size(candidate)[0] <= rect.width:
            current.append(word)
            continue
        if current:
            lines.append(" ".join(current))
        current = [word]
        if len(lines) == max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(" ".join(current))

    y = rect.top
    last_rect = rect.copy()
    for index, line in enumerate(lines[:max_lines]):
        line_text = _fit_text(line, font, rect.width)
        image = font.render(line_text, True, color)
        line_rect = image.get_rect(topleft=(rect.left, y))
        surface.blit(image, line_rect)
        last_rect = line_rect
        y += font.get_linesize() + line_gap
        if index == max_lines - 1:
            break
    return last_rect


def draw_panel(
    pygame: Any,
    surface: Any,
    rect: Any,
    *,
    fill: tuple[int, int, int] = theme.SURFACE,
    border: tuple[int, int, int] = theme.BORDER,
    width: int = 2,
    radius: int = 8,
) -> None:
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    pygame.draw.rect(surface, border, rect, width, border_radius=radius)


def draw_button(
    pygame: Any,
    surface: Any,
    rect: Any,
    label: str,
    font: Any,
    *,
    selected: bool,
    accent: tuple[int, int, int] = theme.ACCENT,
) -> None:
    fill = accent if selected else theme.SURFACE_DARK
    border = theme.TEXT if selected else theme.BORDER
    text_color = theme.INK if selected else theme.TEXT
    pygame.draw.rect(surface, fill, rect, border_radius=8)
    pygame.draw.rect(surface, border, rect, 2, border_radius=8)
    draw_text(
        surface,
        label,
        font,
        text_color,
        rect.center,
        anchor="center",
        max_width=rect.width - 24,
    )


def draw_badge(
    pygame: Any,
    surface: Any,
    rect: Any,
    label: str,
    font: Any,
    *,
    accent: tuple[int, int, int],
) -> None:
    pygame.draw.rect(surface, accent, rect, border_radius=6)
    draw_text(surface, label, font, theme.INK, rect.center, anchor="center", max_width=rect.width - 12)


def draw_bottom_rule(pygame: Any, surface: Any, y: int, width: int) -> None:
    pygame.draw.line(surface, theme.DIM_BORDER, (42, y), (width - 42, y), 1)


def _fit_text(text: str, font: Any, max_width: int | None) -> str:
    if max_width is None or font.size(text)[0] <= max_width:
        return text
    marker = "..."
    available = max(1, max_width - font.size(marker)[0])
    trimmed = text
    while trimmed and font.size(trimmed)[0] > available:
        trimmed = trimmed[:-1]
    return f"{trimmed.rstrip()}{marker}" if trimmed else marker
