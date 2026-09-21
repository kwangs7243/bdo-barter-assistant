from __future__ import annotations

from copy import deepcopy

import pytest
from PIL import Image

from bdo_barter_assistant.barter.collection import (
    merge_row_observations,
    merge_viewport_rows,
    rows_likely_same,
)
from bdo_barter_assistant.barter.scroll_scan import (
    ScrollScanConfig,
    collect_scroll_session,
)
from bdo_barter_assistant.capture.change import (
    ViewportChangeConfig,
    viewport_changed,
    viewport_difference,
    viewport_fingerprint,
)
from bdo_barter_assistant import cli


def _field(value: str | None, confidence: float = 1.0) -> dict[str, object]:
    return {
        "raw": value or "unreadable",
        "value": value,
        "reference_id": None,
        "match_confidence": confidence,
        "match_margin": 0.2 if value else 0.0,
        "auto_confirmed": value is not None,
    }


def _row(name: str, *, confidence: float = 1.0) -> dict[str, object]:
    row = {
        "barter_row_id": f"source_{name}",
        "row_index": 0,
        "bounding_box": [0, 0, 987, 70],
        "island": _field(f"섬-{name}", confidence),
        "remaining_count": 10,
        "from_item": _field(f"소모-{name}", confidence),
        "req_amount": 1,
        "to_item": _field(f"획득-{name}", confidence),
        "yield_amount": 2,
        "review_status": "auto_confirmed",
        "review_required": False,
        "confidence": {
            "island": confidence,
            "from_item": confidence,
            "to_item": confidence,
        },
        "field_auto_confirmed": {
            "island": True,
            "remaining_count": True,
            "from_item": True,
            "req_amount": True,
            "to_item": True,
            "yield_amount": True,
        },
        "alternatives": {"island": [], "from_item": [], "to_item": []},
        "raw": {
            "island": f"섬-{name}",
            "remaining_count": "10회",
            "from_item": f"소모-{name}",
            "req_amount": {"value": 1, "confidence": 0.99},
            "to_item": f"획득-{name}",
            "yield_amount": {"value": 2, "confidence": 0.96},
            "ocr_confidence": None,
        },
    }
    return row


def test_identical_viewport_is_not_changed() -> None:
    config = ViewportChangeConfig(threshold=0.02)
    image = Image.new("RGB", (987, 490), "white")
    fingerprint = viewport_fingerprint(image, config)
    assert viewport_difference(fingerprint, fingerprint.copy()) == 0.0
    assert not viewport_changed(fingerprint, fingerprint.copy(), config)


def test_different_viewport_is_changed() -> None:
    config = ViewportChangeConfig(threshold=0.02)
    black = viewport_fingerprint(Image.new("RGB", (987, 490), "black"), config)
    white = viewport_fingerprint(Image.new("RGB", (987, 490), "white"), config)
    assert viewport_difference(black, white) == 1.0
    assert viewport_changed(black, white, config)


def test_overlapping_rows_are_merged() -> None:
    first = [_row(name) for name in "ABCDEF"]
    second = [_row(name) for name in "DEFGHI"]
    collected = merge_viewport_rows([], first, viewport_index=0)
    collected = merge_viewport_rows(collected, second, viewport_index=1)
    assert len(collected) == 9


def test_overlap_merge_preserves_top_to_bottom_order() -> None:
    first = [_row(name) for name in "ABCDEF"]
    second = [_row(name) for name in "DEFGHI"]
    collected = merge_viewport_rows([], first, viewport_index=0)
    collected = merge_viewport_rows(collected, second, viewport_index=1)
    assert [row["island"]["value"] for row in collected] == [
        f"섬-{name}" for name in "ABCDEFGHI"
    ]


def test_review_null_field_can_be_improved_by_matching_observation() -> None:
    uncertain = _row("A")
    uncertain["to_item"] = _field(None, 0.3)
    uncertain["confidence"]["to_item"] = 0.3
    uncertain["field_auto_confirmed"]["to_item"] = False
    uncertain["review_required"] = True
    uncertain["review_status"] = "review_required"
    certain = _row("A", confidence=0.95)

    merged = merge_row_observations(uncertain, certain, viewport_index=1)
    assert merged["to_item"]["value"] == "획득-A"
    assert merged["review_required"] is False
    assert len(merged["collection_provenance"]) == 1


def test_higher_confidence_observation_wins() -> None:
    low = _row("A", confidence=0.8)
    high = _row("A", confidence=0.98)
    high["raw"]["from_item"] = "더 선명한 소모-A"
    merged = merge_row_observations(low, high, viewport_index=2)
    assert merged["from_item"]["match_confidence"] == 0.98
    assert merged["raw"]["from_item"] == "더 선명한 소모-A"


def test_conflicting_confirmed_field_prevents_false_merge() -> None:
    left = _row("A")
    right = deepcopy(left)
    right["to_item"] = _field("다른 획득품")
    right["raw"]["to_item"] = "다른 획득품"
    assert not rows_likely_same(left, right)
    collected = merge_viewport_rows([], [left], viewport_index=0)
    collected = merge_viewport_rows(collected, [right], viewport_index=1)
    assert len(collected) == 2


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_idle_timeout_stops_session_and_skips_duplicate_frames() -> None:
    clock = _FakeClock()
    image = Image.new("RGB", (100, 50), "white")
    calls = 0

    def scanner(_image: Image.Image) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "rows": [_row("A")],
            "timing_seconds": {"ocr": 1.7, "total": 1.8},
        }

    result = collect_scroll_session(
        lambda: image.copy(),
        scanner,
        config=ScrollScanConfig(
            idle_timeout=1.0,
            poll_interval=0.1,
            debounce=0.2,
            change_threshold=0.02,
        ),
        clock=clock,
        sleeper=clock.sleep,
    )
    assert calls == 1
    assert result["session"]["stop_reason"] == "idle_timeout"
    assert result["session"]["duplicate_viewports_skipped"] > 0
    assert result["session"]["ocr_frames"] == 1
    assert result["session"]["average_ocr_seconds"] == 1.7


def test_final_output_collects_changed_viewports_in_normalized_order() -> None:
    clock = _FakeClock()
    first = Image.new("RGB", (100, 50), "black")
    second = Image.new("RGB", (100, 50), "white")
    captures = 0

    def capture() -> Image.Image:
        nonlocal captures
        captures += 1
        return (first if captures <= 3 else second).copy()

    def scanner(image: Image.Image) -> dict[str, object]:
        names = "ABCDEF" if image.getpixel((0, 0)) == (0, 0, 0) else "DEFGHI"
        return {
            "rows": [_row(name) for name in names],
            "timing_seconds": {"ocr": 1.7, "total": 1.8},
        }

    result = collect_scroll_session(
        capture,
        scanner,
        config=ScrollScanConfig(
            idle_timeout=1.0,
            poll_interval=0.1,
            debounce=0.2,
            change_threshold=0.02,
        ),
        clock=clock,
        sleeper=clock.sleep,
    )
    assert result["session"]["ocr_frames"] == 2
    assert result["session"]["unique_rows"] == 9
    assert result["session"]["review_required_rows"] == 0
    assert [row["island"]["value"] for row in result["rows"]] == [
        f"섬-{name}" for name in "ABCDEFGHI"
    ]
    assert [row["barter_row_id"] for row in result["rows"]] == [
        f"barter_collected_{index}" for index in range(1, 10)
    ]


def test_scan_window_cli_keeps_m2_result_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"rows": [], "capture": {"capture_size": [1920, 1080]}}
    monkeypatch.setattr(cli, "scan_window", lambda **_kwargs: payload)
    written: list[object] = []
    monkeypatch.setattr(cli, "_write_json", lambda value, _output: written.append(value))
    assert cli.main(["scan-window"]) == 0
    assert written == [payload]
