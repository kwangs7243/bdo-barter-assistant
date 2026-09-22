from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from PIL import Image


REFERENCE_WIDTH = 987
REFERENCE_ROW_HEIGHT = 70


@dataclass(frozen=True)
class LayoutProfile:
    """Pixel layout for one known barter-panel rendering."""

    name: str
    text_boxes: Mapping[str, tuple[int, int, int, int]]
    amount_boxes: Mapping[str, tuple[int, int, int, int]]
    amount_mode: str = "m1"
    coordinate_width: int = REFERENCE_WIDTH
    coordinate_height: int = REFERENCE_ROW_HEIGHT


REFERENCE_LAYOUT = LayoutProfile(
    name="m1_reference",
    text_boxes={
        "island": (45, 0, 260, 30),
        "remaining_count": (45, 24, 260, 63),
        "from_item": (320, 0, 637, 36),
        "to_item": (695, 0, 980, 42),
    },
    amount_boxes={
        "req_amount": (310, 40, 317, 52),
        "yield_amount": (684, 40, 694, 52),
    },
)


DETACHED_BARTER_LAYOUT = LayoutProfile(
    name="detached_barter_1023x713",
    text_boxes={
        # Measured from barter_detached_1023x713.png row overlays. The left
        # edge excludes the navigation icon and the right edge excludes the
        # row's collapse button without changing the semantic text area.
        "island": (70, 0, 230, 34),
        "remaining_count": (70, 24, 240, 68),
        "from_item": (340, 0, 660, 36),
        "to_item": (680, 0, 1015, 42),
    },
    amount_boxes={
        # Detached rows place the tiny stack glyphs at the lower-right of the
        # item icons. These boxes are intentionally narrow so item artwork is
        # not treated as a quantity.
        "req_amount": (326, 42, 335, 57),
        "yield_amount": (701, 42, 711, 57),
    },
    amount_mode="detached_glyph",
    coordinate_width=1023,
    coordinate_height=70,
)


@dataclass(frozen=True)
class SegmentedRow:
    index: int
    top: int
    bottom: int
    image: Image.Image


def _group_consecutive(values: Iterable[int]) -> list[tuple[int, int]]:
    groups: list[list[int]] = []
    for value in values:
        if not groups or value > groups[-1][-1] + 1:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [(group[0], group[-1]) for group in groups]


def detect_row_separator_bands(image: Image.Image) -> list[tuple[int, int]]:
    """Detect horizontal barter-row borders without sampling the scrollbar.

    A separator spans almost the entire row content area. Measuring a broad
    band makes the result independent of the scrollbar thumb and remains
    usable when a tooltip obscures part of a row.
    """
    grayscale = image.convert("L")
    content_left = max(8, round(grayscale.width * 0.01))
    content_right = max(content_left + 1, grayscale.width - 48)
    content_width = content_right - content_left
    separator_rows: list[int] = []
    for y in range(grayscale.height):
        pixels = list(
            grayscale.crop((content_left, y, content_right, y + 1)).getdata()
        )
        mean = sum(pixels) / content_width
        darkness_ratio = sum(pixel < 50 for pixel in pixels) / content_width
        if mean < 50.0 and darkness_ratio >= 0.90:
            separator_rows.append(y)
    return [
        band
        for band in _group_consecutive(separator_rows)
        if band[1] - band[0] >= 1
    ]


def segment_complete_rows(image: Image.Image) -> list[SegmentedRow]:
    """Find complete barter rows between the panel's dark horizontal separators."""
    bands = detect_row_separator_bands(image)

    rows: list[SegmentedRow] = []
    for before, after in zip(bands, bands[1:]):
        top = before[1] + 1
        bottom = after[0]
        height = bottom - top
        if 60 <= height <= 80:
            rows.append(
                SegmentedRow(
                    index=len(rows),
                    top=top,
                    bottom=bottom,
                    image=image.crop((0, top, image.width, bottom)),
                )
            )
    return rows


_TEXT_BOXES = REFERENCE_LAYOUT.text_boxes


def text_field_crops(
    row: SegmentedRow,
    scale: int = 4,
    *,
    profile: LayoutProfile = REFERENCE_LAYOUT,
) -> dict[str, Image.Image]:
    """Crop fixed semantic columns and enlarge them for the local OCR engine."""
    if scale < 1:
        raise ValueError("scale must be at least 1")
    width_scale = row.image.width / profile.coordinate_width
    height_scale = row.image.height / profile.coordinate_height
    result: dict[str, Image.Image] = {}
    for name, (left, top, right, bottom) in profile.text_boxes.items():
        box = (
            round(left * width_scale),
            round(top * height_scale),
            round(right * width_scale),
            round(bottom * height_scale),
        )
        crop = row.image.crop(box).convert("RGB")
        if scale > 1:
            crop = crop.resize(
                (crop.width * scale, crop.height * scale), Image.Resampling.BICUBIC
            )
        result[name] = crop
    return result
