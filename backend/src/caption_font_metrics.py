"""HarfBuzz-based text measurement for placing emojis above ASS caption lines.

libass renders fontsdir fonts at an *effective* size smaller than the ASS
``Fontsize``: it interprets the size as the Windows line box
(``usWinAscent + usWinDescent``) instead of the em square. To predict where
libass lays out each caption word we shape the text with HarfBuzz (uharfbuzz)
at that effective size, reusing the same advance math libass applies
(cumulative advances, space advances between words, line centred by the total
advance).

Returned y values use screen coordinates relative to the glyph baseline
(positive = down). Returned x values are relative to the line's pen origin
(positive = right).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from .font_registry import (
    FONTS_DIR,
    USER_FONTS_DIR,
    find_font_path,
    get_font_family_name,
)

try:
    import uharfbuzz as _hb
    from fontTools.ttLib import TTFont as _TTFont

    HB_AVAILABLE = True
except Exception:  # pragma: no cover - fallback when deps missing
    _hb = None
    _TTFont = None
    HB_AVAILABLE = False


class ShapedText:
    """Shaped string at a given pixel size."""

    def __init__(self, advance: float, ink_left: float, ink_right: float,
                 ink_top: float, ink_bottom: float, ascender: float,
                 descender: float):
        self.advance = advance
        self.ink_left = ink_left
        self.ink_right = ink_right
        self.ink_top = ink_top
        self.ink_bottom = ink_bottom
        self.ascender = ascender
        self.descender = descender

    @property
    def ink_center(self) -> float:
        return (self.ink_left + self.ink_right) / 2.0

    @property
    def ink_center_y(self) -> float:
        return (self.ink_top + self.ink_bottom) / 2.0

    @property
    def advance_center(self) -> float:
        return self.advance / 2.0

    @property
    def advance_center_y(self) -> float:
        return -(self.ascender + self.descender) / 2.0


def resolve_caption_font_path(font_family: Optional[str], font_name: str) -> Optional[Path]:
    """Resolve the TTF/OTF path for a caption font.

    ``font_family`` is the template/user stem (e.g. "THEBOLDFONT"); ``font_name``
    is the ASS font name (internal family like "THE BOLD FONT (FREE VERSION)").
    """
    if not HB_AVAILABLE:
        return None
    path = find_font_path(font_family, allow_all_user_fonts=True) if font_family else None
    if path and path.exists():
        return Path(path)
    for search_dir in (FONTS_DIR, USER_FONTS_DIR):
        if not search_dir.exists():
            continue
        for extension in (".ttf", ".otf"):
            for candidate in sorted(search_dir.glob(f"*{extension}")):
                if get_font_family_name(candidate) == font_name:
                    return candidate
    return None


def effective_font_size(font_px: float, font_path: Path) -> float:
    """libass treats Fontsize as the Windows line box, not the em square."""
    if not HB_AVAILABLE:
        return font_px
    try:
        font = _TTFont(str(font_path))
        upem = font["head"].unitsPerEm
        os2 = font["OS/2"]
        box = os2.usWinAscent + os2.usWinDescent
        if box <= 0:
            return font_px
        return font_px * upem / box
    except Exception:
        return font_px


def _hb_shape(text: str, font_path: Path, size_px: float) -> Optional[ShapedText]:
    try:
        blob = _hb.Blob.from_file_path(str(font_path))
        face = _hb.Face(blob)
        font = _hb.Font(face)
        font.scale = (int(round(size_px)), int(round(size_px)))
        buf = _hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        _hb.shape(font, buf)
        ascender, descender, _line_gap = font.get_font_extents("ltr")
        cursor = 0.0
        ink_left = ink_right = None
        ink_top = ink_bottom = None
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            ext = font.get_glyph_extents(info.codepoint)
            if ext is not None:
                left = cursor + pos.x_offset + ext.x_bearing
                right = left + ext.width
                # y_bearing points up from the baseline; height may be negative
                # when the font uses an inverted y axis. Screen y grows downward.
                top = -pos.y_offset - ext.y_bearing
                bottom = -pos.y_offset - (ext.y_bearing + ext.height)
                ink_left = left if ink_left is None else min(ink_left, left)
                ink_right = right if ink_right is None else max(ink_right, right)
                ink_top = top if ink_top is None else min(ink_top, top)
                ink_bottom = bottom if ink_bottom is None else max(ink_bottom, bottom)
            cursor += pos.x_advance
        return ShapedText(
            advance=cursor,
            ink_left=0.0 if ink_left is None else ink_left,
            ink_right=0.0 if ink_right is None else ink_right,
            ink_top=0.0 if ink_top is None else ink_top,
            ink_bottom=0.0 if ink_bottom is None else ink_bottom,
            ascender=ascender,
            descender=descender,
        )
    except Exception:
        return None


def shape_text(text: str, font_path: Optional[Path], size_px: float) -> Optional[ShapedText]:
    if not HB_AVAILABLE or font_path is None:
        return None
    return _hb_shape(text, font_path, size_px)


class CaptionLayout:
    """Per-word layout of a caption line under libass's rendering rules."""

    def __init__(self, words: Sequence[str], font_path: Path, size_px: float,
                 total_advance: float, line_ink_top: float, ascender: float,
                 descender: float, positions: Sequence[tuple[float, float]]):
        self.words = words
        self.font_path = font_path
        self.size_px = size_px
        self.total_advance = total_advance
        self.line_ink_top = line_ink_top
        self.ascender = ascender
        self.descender = descender
        self.positions = positions  # (pen_x_from_line_origin, word_ink_center_x_from_line_origin)

    def word_center_x(self, index: int) -> float:
        return self.positions[index][1]

    def word_pen_x(self, index: int) -> float:
        return self.positions[index][0]

    def line_center_offset(self) -> float:
        """Offset to add to video coords so the line's advance is centred."""
        return -self.total_advance / 2.0


def measure_caption_line(
    words: Sequence[str],
    font_path: Optional[Path],
    font_px: float,
) -> Optional[CaptionLayout]:
    """Measure a caption line the way libass lays it out.

    Returns None when the font can't be shaped (caller falls back to centering
    the emoji over the whole line).
    """
    if not HB_AVAILABLE or font_path is None or not words:
        return None
    eff = effective_font_size(font_px, font_path)
    space = shape_text(" ", font_path, eff)
    if space is None:
        return None
    space_adv = space.advance
    shaped_words = [shape_text(word, font_path, eff) for word in words]
    if any(s is None for s in shaped_words):
        return None

    total = sum(s.advance for s in shaped_words) + space_adv * (len(shaped_words) - 1)
    line_ink_top = 0.0
    ascender = shaped_words[0].ascender
    descender = shaped_words[0].descender
    positions: list[tuple[float, float]] = []
    cursor = 0.0
    for shaped in shaped_words:
        positions.append((cursor, cursor + shaped.ink_center))
        line_ink_top = min(line_ink_top, shaped.ink_top)
        ascender = max(ascender, shaped.ascender)
        descender = min(descender, shaped.descender)
        cursor += shaped.advance + space_adv
    return CaptionLayout(
        words=list(words),
        font_path=font_path,
        size_px=eff,
        total_advance=total,
        line_ink_top=line_ink_top,
        ascender=ascender,
        descender=descender,
        positions=positions,
    )
