from __future__ import annotations

from copy import deepcopy
from typing import Any

from PIL import Image


PRIMARY_FIELDS = ("island", "from_item", "to_item")
NUMERIC_FIELDS = ("remaining_count", "req_amount", "yield_amount")
_DETACHED_ROW_WIDTH = 1023
_DETACHED_ROW_HEIGHT = 70
_VISUAL_IDENTITY_BOXES = (
    (70, 0, 240, 34),
    (340, 0, 660, 38),
    (710, 0, 1010, 42),
)


def _confirmed_value(row: dict[str, Any], field: str) -> object | None:
    payload = row.get(field)
    if not isinstance(payload, dict) or not payload.get("auto_confirmed"):
        return None
    return payload.get("value")


def rows_likely_same(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Conservatively identify one trade seen in two overlapping viewports."""
    primary_matches = 0
    for field in PRIMARY_FIELDS:
        left_value = _confirmed_value(left, field)
        right_value = _confirmed_value(right, field)
        if left_value is not None and right_value is not None:
            if left_value != right_value:
                return False
            primary_matches += 1

    numeric_matches = 0
    for field in NUMERIC_FIELDS:
        left_value = left.get(field)
        right_value = right.get(field)
        if left_value is not None and right_value is not None:
            if left_value != right_value:
                return False
            numeric_matches += 1

    # A pair of confirmed names plus a numeric agreement is strong enough to
    # improve a null field. Three confirmed names can stand on their own.
    return primary_matches == 3 or (
        primary_matches >= 2 and numeric_matches >= 1
    )


def _row_quality(row: dict[str, Any]) -> tuple[int, float]:
    statuses = row.get("field_auto_confirmed", {})
    confirmed = sum(
        bool(statuses.get(field)) for field in (*PRIMARY_FIELDS, *NUMERIC_FIELDS)
    )
    confidence = row.get("confidence", {})
    score = sum(float(confidence.get(field, 0.0)) for field in PRIMARY_FIELDS)
    return confirmed, score


def _observation(row: dict[str, Any], viewport_index: int) -> dict[str, Any]:
    return {
        "viewport_index": viewport_index,
        "source_row_index": row.get("row_index"),
        "review_required": bool(row.get("review_required")),
        "confidence": deepcopy(row.get("confidence", {})),
        "raw": deepcopy(row.get("raw", {})),
    }


def prepare_observed_row(row: dict[str, Any], viewport_index: int) -> dict[str, Any]:
    prepared = deepcopy(row)
    prepared["collection_provenance"] = [_observation(row, viewport_index)]
    return prepared


def _field_rank(payload: object) -> tuple[int, int, float]:
    if not isinstance(payload, dict):
        return (0, 0, 0.0)
    return (
        int(bool(payload.get("auto_confirmed"))),
        int(payload.get("value") is not None),
        float(payload.get("match_confidence", 0.0)),
    )


def _merge_row_observations(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    viewport_index: int,
    *,
    require_ocr_identity: bool,
) -> dict[str, Any]:
    if require_ocr_identity and not rows_likely_same(existing, incoming):
        raise ValueError("cannot merge rows without sufficient matching evidence")

    merged = deepcopy(
        existing if _row_quality(existing) >= _row_quality(incoming) else incoming
    )
    merged_raw = deepcopy(merged.get("raw", {}))
    merged_alternatives = deepcopy(merged.get("alternatives", {}))

    for field in PRIMARY_FIELDS:
        left_payload = existing.get(field)
        right_payload = incoming.get(field)
        if _field_rank(right_payload) > _field_rank(left_payload):
            merged[field] = deepcopy(right_payload)
            merged_raw[field] = deepcopy(incoming.get("raw", {}).get(field))
            merged_alternatives[field] = deepcopy(
                incoming.get("alternatives", {}).get(field, [])
            )
        else:
            merged[field] = deepcopy(left_payload)
            merged_raw[field] = deepcopy(existing.get("raw", {}).get(field))
            merged_alternatives[field] = deepcopy(
                existing.get("alternatives", {}).get(field, [])
            )

    for field in NUMERIC_FIELDS:
        left_value = existing.get(field)
        right_value = incoming.get(field)
        if left_value is None and right_value is not None:
            merged[field] = right_value
            merged_raw[field] = deepcopy(incoming.get("raw", {}).get(field))
        else:
            merged[field] = left_value
            merged_raw[field] = deepcopy(existing.get("raw", {}).get(field))

    merged["raw"] = merged_raw
    merged["alternatives"] = merged_alternatives
    merged["confidence"] = {
        field: float(merged[field].get("match_confidence", 0.0))
        for field in PRIMARY_FIELDS
    }
    merged["field_auto_confirmed"] = {
        **{
            field: bool(
                isinstance(merged.get(field), dict)
                and merged[field].get("auto_confirmed")
            )
            for field in PRIMARY_FIELDS
        },
        **{field: merged.get(field) is not None for field in NUMERIC_FIELDS},
    }
    review_required = not all(merged["field_auto_confirmed"].values())
    merged["review_required"] = review_required
    merged["review_status"] = (
        "review_required" if review_required else "auto_confirmed"
    )
    provenance = deepcopy(existing.get("collection_provenance", []))
    provenance.append(_observation(incoming, viewport_index))
    merged["collection_provenance"] = provenance
    return merged


def merge_row_observations(
    existing: dict[str, Any], incoming: dict[str, Any], viewport_index: int
) -> dict[str, Any]:
    return _merge_row_observations(
        existing,
        incoming,
        viewport_index,
        require_ocr_identity=True,
    )


def row_visual_fingerprint(image: Image.Image) -> tuple[int, ...]:
    """Hash the three row identity columns without using OCR text."""
    width_scale = image.width / _DETACHED_ROW_WIDTH
    height_scale = image.height / _DETACHED_ROW_HEIGHT
    bits: list[int] = []
    for left, top, right, bottom in _VISUAL_IDENTITY_BOXES:
        crop = image.crop(
            (
                round(left * width_scale),
                round(top * height_scale),
                round(right * width_scale),
                round(bottom * height_scale),
            )
        )
        sample = crop.convert("L").resize((65, 12), Image.Resampling.BILINEAR)
        bits.extend(
            int(sample.getpixel((x, y)) > sample.getpixel((x + 1, y)))
            for y in range(sample.height)
            for x in range(sample.width - 1)
        )
    return tuple(bits)


def visual_fingerprint_difference(
    left: tuple[int, ...], right: tuple[int, ...]
) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("row visual fingerprints must have the same non-zero length")
    return sum(a != b for a, b in zip(left, right)) / len(left)


def visual_overlap_length(
    collected: list[tuple[int, ...]],
    incoming: list[tuple[int, ...]],
    *,
    threshold: float = 0.02,
) -> int:
    """Find a conservative suffix/prefix overlap from segmented row pixels."""
    for length in range(min(len(collected), len(incoming)), 0, -1):
        if all(
            visual_fingerprint_difference(left, right) <= threshold
            for left, right in zip(collected[-length:], incoming[:length])
        ):
            return length
    return 0


def overlap_length(
    collected: list[dict[str, Any]], incoming: list[dict[str, Any]]
) -> int:
    """Find the largest safe suffix/prefix overlap without fuzzy guessing."""
    for length in range(min(len(collected), len(incoming)), 0, -1):
        if all(
            rows_likely_same(left, right)
            for left, right in zip(collected[-length:], incoming[:length])
        ):
            return length
    return 0


def merge_viewport_rows(
    collected: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    viewport_index: int,
) -> list[dict[str, Any]]:
    """Merge a downward-scrolled viewport while preserving top-to-bottom order."""
    if not collected:
        return [prepare_observed_row(row, viewport_index) for row in incoming]

    merged = deepcopy(collected)
    overlap = overlap_length(merged, incoming)
    if overlap:
        start = len(merged) - overlap
        for offset in range(overlap):
            merged[start + offset] = merge_row_observations(
                merged[start + offset], incoming[offset], viewport_index
            )
    merged.extend(
        prepare_observed_row(row, viewport_index) for row in incoming[overlap:]
    )
    return merged


def merge_viewport_rows_by_visual_overlap(
    collected: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    viewport_index: int,
    overlap: int,
) -> list[dict[str, Any]]:
    """Merge rows whose identity was already proven from row-image overlap."""
    if overlap < 0 or overlap > min(len(collected), len(incoming)):
        raise ValueError("visual overlap is outside the available row range")
    if not collected:
        if overlap:
            raise ValueError("the first viewport cannot have an overlap")
        return [prepare_observed_row(row, viewport_index) for row in incoming]

    merged = deepcopy(collected)
    if overlap:
        start = len(merged) - overlap
        for offset in range(overlap):
            merged[start + offset] = _merge_row_observations(
                merged[start + offset],
                incoming[offset],
                viewport_index,
                require_ocr_identity=False,
            )
    merged.extend(
        prepare_observed_row(row, viewport_index) for row in incoming[overlap:]
    )
    return merged


def finalize_collected_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    finalized = deepcopy(rows)
    for index, row in enumerate(finalized):
        row["barter_row_id"] = f"barter_collected_{index + 1}"
        row["row_index"] = index
    return finalized
