from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from bdo_barter_assistant.barter.pipeline import scan_barter_image
from bdo_barter_assistant.capture.region import Region
from bdo_barter_assistant.evaluation import evaluate_golden


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows local OCR test")

ROOT = Path(__file__).resolve().parents[1]
CROPPED = ROOT / "reference" / "samples" / "barter_cropped.png"
FULLSCREEN = ROOT / "reference" / "samples" / "barter_fullscreen.png"
GOLDEN = ROOT / "tests" / "fixtures" / "golden_rows.json"


def _values(row: dict[str, object]) -> dict[str, object]:
    return {
        "island": row["island"]["value"],
        "remaining_count": row["remaining_count"],
        "from_item": row["from_item"]["value"],
        "req_amount": row["req_amount"],
        "to_item": row["to_item"]["value"],
        "yield_amount": row["yield_amount"],
    }


def test_cropped_sample_matches_all_golden_fields() -> None:
    report = evaluate_golden(CROPPED, GOLDEN)

    assert report["detected_rows"] == 6
    assert report["exact"] == {
        "island": 6,
        "remaining_count": 6,
        "from_item": 6,
        "req_amount": 6,
        "to_item": 6,
        "yield_amount": 6,
    }
    assert report["review_required_rows"] == 0
    assert report["wrong_auto_confirmed_count"] == 0


def test_fullscreen_manual_region_has_same_normalized_rows() -> None:
    result = scan_barter_image(
        FULLSCREEN, region=Region(464, 404, 987, 490), scale=4
    )
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert result["coverage"]["complete_rows_detected"] == 6
    assert [_values(row) for row in result["rows"]] == golden


def test_masked_field_requires_review_instead_of_wrong_confirmation(
    tmp_path: Path,
) -> None:
    with Image.open(CROPPED) as source:
        damaged = source.convert("RGB")
    ImageDraw.Draw(damaged).rectangle((320, 3, 637, 39), fill=(0, 0, 0))
    damaged_path = tmp_path / "masked-from-item.png"
    damaged.save(damaged_path)

    result = scan_barter_image(damaged_path)
    first = result["rows"][0]

    assert first["from_item"]["value"] is None
    assert not first["field_auto_confirmed"]["from_item"]
    assert first["review_status"] == "review_required"

