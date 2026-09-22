from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from .layout import (
    REFERENCE_LAYOUT,
    LayoutProfile,
    SegmentedRow,
)


@dataclass(frozen=True)
class AmountObservation:
    value: int | None
    confidence: float
    signature: tuple[int, ...]


_AMOUNT_BOXES = REFERENCE_LAYOUT.amount_boxes


def _mask_signature(image: Image.Image, threshold: int = 175) -> tuple[int, ...]:
    gray = image.convert("L")
    return tuple(
        sum(gray.getpixel((x, y)) >= threshold for x in range(gray.width))
        for y in range(gray.height)
    )


def _classify_small_digit(image: Image.Image) -> AmountObservation:
    """Classify the tiny white 1/2/3 glyphs present in the M1 sample.

    Other shapes deliberately remain unknown instead of being guessed. Windows OCR
    does not recognize these 3-pixel-wide icon-overlay numbers reliably.
    """
    gray = image.convert("L")
    pixels = [
        (x, y)
        for y in range(gray.height)
        for x in range(gray.width)
        if gray.getpixel((x, y)) >= 175
    ]
    signature = _mask_signature(gray)
    if not pixels:
        return AmountObservation(None, 0.0, signature)

    # The stable digit baseline occupies the lower ten rows. Item-art noise is
    # mostly attached to the crop edge, so width and stroke distribution are
    # measured only in this expected glyph band.
    active_rows = [index for index, count in enumerate(signature) if count]
    if len(active_rows) < 8:
        return AmountObservation(None, 0.0, signature)

    central_pixels = [(x, y) for x, y in pixels if 1 <= y <= 10]
    if not central_pixels:
        return AmountObservation(None, 0.0, signature)
    xs = [x for x, _ in central_pixels]
    width = max(xs) - min(xs) + 1
    bottom_stroke = signature[10] if len(signature) > 10 else 0
    middle_stroke = max(signature[5:8], default=0)

    # A one has a stable single-pixel lower stem and a three-pixel base. The
    # upper rows may contain item-art noise, so classify this signature first.
    if bottom_stroke == 3 and sum(signature[5:10]) <= 6:
        return AmountObservation(1, 0.99, signature)
    if width >= 5 and bottom_stroke >= 5:
        return AmountObservation(2, 0.96, signature)
    if width >= 5 and bottom_stroke >= 3 and middle_stroke >= 2:
        return AmountObservation(3, 0.94, signature)
    return AmountObservation(None, 0.0, signature)


def _classify_detached_glyph(image: Image.Image) -> AmountObservation:
    """Conservatively recognize only a clean single ``1`` glyph.

    The detached window renders stack counts at roughly 2-5 pixels wide and
    overlaps item artwork for multi-digit values. Guessing those values caused
    false confirmations, so anything wider than a narrow vertical stroke stays
    unknown and is sent to review.
    """
    gray = image.convert("L")
    threshold = 230
    mask = [
        (x, y)
        for y in range(gray.height)
        for x in range(gray.width)
        if gray.getpixel((x, y)) >= threshold
    ]
    signature = _mask_signature(gray, threshold=threshold)
    active_rows = [y for y, count in enumerate(signature) if count]
    active_columns = sorted({x for x, _ in mask})
    if not mask or len(active_rows) < 7:
        return AmountObservation(None, 0.0, signature)
    if len(active_columns) <= 2 and len(active_rows) >= 8:
        return AmountObservation(1, 0.93, signature)
    return AmountObservation(None, 0.0, signature)


def read_amount(
    row: SegmentedRow,
    field: str,
    *,
    profile: LayoutProfile = REFERENCE_LAYOUT,
) -> AmountObservation:
    left, top, right, bottom = profile.amount_boxes[field]
    width_scale = row.image.width / profile.coordinate_width
    height_scale = row.image.height / profile.coordinate_height
    crop = row.image.crop(
        (
            round(left * width_scale),
            round(top * height_scale),
            round(right * width_scale),
            round(bottom * height_scale),
        )
    )
    if profile.amount_mode == "detached_glyph":
        return _classify_detached_glyph(crop)
    return _classify_small_digit(crop)
