from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PIL import Image


REFERENCE_WIDTH = 987
REFERENCE_ROW_HEIGHT = 70


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


def segment_complete_rows(image: Image.Image) -> list[SegmentedRow]:
    """Find complete barter rows between the panel's dark horizontal separators."""
    grayscale = image.convert("L")
    # Use the quiet right edge instead of the content columns. A masked or very
    # dark field must not be mistaken for a horizontal row separator.
    strip_left = max(0, grayscale.width - 32)
    strip_width = grayscale.width - strip_left
    row_means = [
        sum(grayscale.crop((strip_left, y, grayscale.width, y + 1)).getdata())
        / strip_width
        for y in range(grayscale.height)
    ]
    separator_rows = [index for index, mean in enumerate(row_means) if mean < 45.0]
    bands = [band for band in _group_consecutive(separator_rows) if band[1] - band[0] >= 1]

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


_TEXT_BOXES = {
    "island": (45, 0, 260, 30),
    "remaining_count": (45, 24, 260, 63),
    "from_item": (320, 0, 637, 36),
    "to_item": (695, 0, 980, 42),
}


def text_field_crops(row: SegmentedRow, scale: int = 4) -> dict[str, Image.Image]:
    """Crop fixed semantic columns and enlarge them for the local OCR engine."""
    if scale < 1:
        raise ValueError("scale must be at least 1")
    width_scale = row.image.width / REFERENCE_WIDTH
    height_scale = row.image.height / REFERENCE_ROW_HEIGHT
    result: dict[str, Image.Image] = {}
    for name, (left, top, right, bottom) in _TEXT_BOXES.items():
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
