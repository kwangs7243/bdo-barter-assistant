from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from bdo_barter_assistant.barter.pipeline import scan_barter_image
from bdo_barter_assistant.capture.region import Region


FIELDS = (
    "island",
    "remaining_count",
    "from_item",
    "req_amount",
    "to_item",
    "yield_amount",
)


def _actual_value(row: dict[str, Any], field: str) -> Any:
    value = row[field]
    if field in {"island", "from_item", "to_item"}:
        return value["value"]
    return value


def evaluate_golden(
    image_path: Path,
    golden_path: Path,
    *,
    region: Region | None = None,
    scale: int = 4,
    repeat: int = 1,
) -> dict[str, Any]:
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    scans = [
        scan_barter_image(image_path, region=region, scale=scale) for _ in range(repeat)
    ]
    result = scans[-1]
    rows = result["rows"]

    exact = {field: 0 for field in FIELDS}
    wrong_auto_confirmed: list[dict[str, Any]] = []
    for index, expected in enumerate(golden):
        if index >= len(rows):
            continue
        actual = rows[index]
        for field in FIELDS:
            actual_value = _actual_value(actual, field)
            if actual_value == expected[field]:
                exact[field] += 1
            elif actual["field_auto_confirmed"][field]:
                wrong_auto_confirmed.append(
                    {
                        "row_index": index,
                        "field": field,
                        "expected": expected[field],
                        "actual": actual_value,
                    }
                )

    totals = [scan["timing_seconds"]["total"] for scan in scans]
    return {
        "engine": result["engine"],
        "preprocessing": result["preprocessing"],
        "golden_rows": len(golden),
        "detected_rows": len(rows),
        "exact": exact,
        "review_required_rows": sum(row["review_required"] for row in rows),
        "wrong_auto_confirmed_count": len(wrong_auto_confirmed),
        "wrong_auto_confirmed": wrong_auto_confirmed,
        "timing_seconds": {
            "runs": repeat,
            "sum_total": round(sum(totals), 4),
            "average_total": round(statistics.mean(totals), 4),
            "min_total": round(min(totals), 4),
            "max_total": round(max(totals), 4),
            "last_total": totals[-1],
        },
        "network_requests": 0,
        "rows": rows,
    }
