from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from PIL import Image

from bdo_barter_assistant.barter.trade_contract import normalize_trade_observation
from bdo_barter_assistant.capture.region import Region, crop_region
from bdo_barter_assistant.matching.dictionary import DictionaryMatch, match_dictionary
from bdo_barter_assistant.ocr.amount import AmountObservation, read_amount
from bdo_barter_assistant.ocr.layout import (
    REFERENCE_LAYOUT,
    LayoutProfile,
    segment_complete_rows,
    text_field_crops,
)
from bdo_barter_assistant.ocr.windows import OcrText, WindowsOcrAdapter
from bdo_barter_assistant.reference_data import OcrDictionary, load_ocr_dictionary


_REMAINING_COUNT = re.compile(r"(?<!\d)(\d{1,2})\s*회")


def _match_payload(match: DictionaryMatch) -> dict[str, Any]:
    return {
        "raw": match.raw,
        "value": match.value,
        "reference_id": None,
        "match_confidence": round(match.confidence, 4),
        "match_margin": round(match.margin, 4),
        "auto_confirmed": match.auto_confirmed,
    }


def _alternatives(match: DictionaryMatch) -> list[dict[str, Any]]:
    return [
        {
            "value": alternative.value,
            "source_value": alternative.source_value,
            "confidence": round(alternative.confidence, 4),
        }
        for alternative in match.alternatives
    ]


def _parse_remaining_count(observation: OcrText) -> int | None:
    match = _REMAINING_COUNT.search(observation.text)
    return int(match.group(1)) if match else None


def _amount_payload(observation: AmountObservation) -> dict[str, Any]:
    return {
        "value": observation.value,
        "confidence": observation.confidence,
        "signature": list(observation.signature),
        "method": "fixed_glyph_1_2_3",
    }


def scan_barter_image(
    image_path: Path,
    *,
    region: Region | None = None,
    dictionary: OcrDictionary | None = None,
    ocr_adapter: WindowsOcrAdapter | None = None,
    scale: int = 4,
    layout_profile: LayoutProfile = REFERENCE_LAYOUT,
) -> dict[str, Any]:
    """Run the M1 fixed-sample pipeline and return normalized rows plus timings."""
    started = time.perf_counter()
    with Image.open(image_path) as source:
        frame = source.convert("RGB")
    return scan_barter_frame(
        frame,
        source_label=str(image_path),
        region=region,
        dictionary=dictionary,
        ocr_adapter=ocr_adapter,
        scale=scale,
        layout_profile=layout_profile,
        _started_at=started,
    )


def scan_barter_frame(
    frame: Image.Image,
    *,
    source_label: str = "memory",
    region: Region | None = None,
    dictionary: OcrDictionary | None = None,
    ocr_adapter: WindowsOcrAdapter | None = None,
    scale: int = 4,
    layout_profile: LayoutProfile = REFERENCE_LAYOUT,
    _started_at: float | None = None,
) -> dict[str, Any]:
    """Run the unchanged M1 OCR stages on an in-memory image frame."""
    started = _started_at if _started_at is not None else time.perf_counter()
    dictionary = dictionary or load_ocr_dictionary()
    ocr_adapter = ocr_adapter or WindowsOcrAdapter()

    barter_area = crop_region(frame.convert("RGB"), region)
    rows = segment_complete_rows(barter_area)
    segmented_at = time.perf_counter()

    fields: dict[str, Image.Image] = {}
    for row in rows:
        for field, crop in text_field_crops(
            row, scale=scale, profile=layout_profile
        ).items():
            fields[f"{row.index:03d}_{field}"] = crop
    observations = ocr_adapter.recognize_many(fields)
    ocr_finished = time.perf_counter()

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        prefix = f"{row.index:03d}_"
        island_raw = observations[prefix + "island"].text
        from_raw = observations[prefix + "from_item"].text
        to_raw = observations[prefix + "to_item"].text
        island = match_dictionary(island_raw, dictionary.islands, kind="island")
        from_item = match_dictionary(from_raw, dictionary.items, kind="item")
        to_item = match_dictionary(to_raw, dictionary.items, kind="item")
        remaining_observation = observations[prefix + "remaining_count"]
        remaining_count = _parse_remaining_count(remaining_observation)
        req_amount = read_amount(row, "req_amount", profile=layout_profile)
        yield_amount = read_amount(row, "yield_amount", profile=layout_profile)

        field_status = {
            "island": island.auto_confirmed,
            "remaining_count": remaining_count is not None,
            "from_item": from_item.auto_confirmed,
            "req_amount": req_amount.value is not None,
            "to_item": to_item.auto_confirmed,
            "yield_amount": yield_amount.value is not None,
        }
        review_required = not all(field_status.values())
        normalized_rows.append(
            normalize_trade_observation(
                {
                "barter_row_id": f"barter_sample_{row.index + 1}",
                "row_index": row.index,
                "bounding_box": [0, row.top, barter_area.width, row.bottom],
                "island": _match_payload(island),
                "remaining_count": remaining_count,
                "from_item": _match_payload(from_item),
                "req_amount": req_amount.value,
                "to_item": _match_payload(to_item),
                "yield_amount": yield_amount.value,
                "review_status": "review_required" if review_required else "auto_confirmed",
                "review_required": review_required,
                "confidence": {
                    "island": round(island.confidence, 4),
                    "from_item": round(from_item.confidence, 4),
                    "to_item": round(to_item.confidence, 4),
                },
                "field_auto_confirmed": field_status,
                "alternatives": {
                    "island": _alternatives(island),
                    "from_item": _alternatives(from_item),
                    "to_item": _alternatives(to_item),
                },
                "raw": {
                    "island": island_raw,
                    "remaining_count": remaining_observation.text,
                    "from_item": from_raw,
                    "req_amount": _amount_payload(req_amount),
                    "to_item": to_raw,
                    "yield_amount": _amount_payload(yield_amount),
                    "ocr_confidence": None,
                },
                },
                dictionary,
            )
        )

    finished = time.perf_counter()
    return {
        "engine": "Windows.Media.Ocr/OcrEngine (ko)",
        "preprocessing": f"fixed field crop + {scale}x bicubic upscale",
        "layout_profile": layout_profile.name,
        "source_image": source_label,
        "manual_region": (
            [region.x, region.y, region.width, region.height] if region else None
        ),
        "coverage": {
            "complete_rows_detected": len(rows),
            "barter_area_size": list(barter_area.size),
        },
        "rows": normalized_rows,
        "timing_seconds": {
            "segmentation": round(segmented_at - started, 4),
            "ocr": round(ocr_finished - segmented_at, 4),
            "normalization": round(finished - ocr_finished, 4),
            "total": round(finished - started, 4),
        },
        "network_requests": 0,
    }
