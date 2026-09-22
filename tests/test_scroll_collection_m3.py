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
    _detect_scrollbar_state,
    collect_scroll_session,
)
from bdo_barter_assistant.capture.change import (
    ViewportChangeConfig,
    viewport_changed,
    viewport_difference,
    viewport_fingerprint,
)
from bdo_barter_assistant.capture.windows import WindowCaptureError
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


def test_detached_scrollbar_bottom_allows_panel_border_margin() -> None:
    bottom = Image.new("RGB", (1023, 493), "black")
    before_bottom = bottom.copy()
    tan = (120, 90, 40)
    for image, top, last in ((bottom, 428, 479), (before_bottom, 408, 458)):
        for y in range(top, last + 1):
            for x in range(image.width - 22, image.width - 13):
                image.putpixel((x, y), tan)

    assert _detect_scrollbar_state(bottom)["at_bottom"] is True
    assert _detect_scrollbar_state(before_bottom)["at_bottom"] is False


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


def _visual_token(name: str) -> tuple[int, ...]:
    index = ord(name) - ord("A")
    return tuple(int(bit == index) for bit in range(32))


def _accept_viewport(image: Image.Image) -> dict[str, object]:
    first = image.getpixel((0, 0)) == (0, 0, 0)
    names = "ABCDEF" if first else "DEFGHI"
    return {
        "complete_rows": 6,
        "row_heights": [70] * 6,
        "separator_positions": [0, 75, 150, 225, 300, 375, 450],
        "row_fingerprints": [_visual_token(name) for name in names],
        "scrollbar": {
            "available": True,
            "at_top": first,
            "at_bottom": not first,
        },
        "geometry_valid": True,
        "accepted": True,
    }


def test_bottom_viewport_stops_session_after_connected_viewports() -> None:
    clock = _FakeClock()
    images = [
        Image.new("RGB", (100, 50), color)
        for color in ("black",) * 3 + ("white",) * 3
    ]
    captures = 0
    calls = 0

    def capture() -> Image.Image:
        nonlocal captures
        image = images[min(captures, len(images) - 1)]
        captures += 1
        return image.copy()

    def scanner(_image: Image.Image) -> dict[str, object]:
        nonlocal calls
        calls += 1
        names = "ABCDEF" if _image.getpixel((0, 0)) == (0, 0, 0) else "DEFGHI"
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
        validate_viewport=_accept_viewport,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert calls == 2
    assert result["session"]["stop_reason"] == "bottom_reached"
    assert result["session"]["ocr_frames"] == 2
    assert result["session"]["average_ocr_seconds"] == 1.7
    assert result["coverage"]["coverage_complete"] is True
    assert result["coverage"]["accepted_viewport_overlaps"] == [0, 3]


def test_duplicate_bottom_viewport_completes_coverage_without_second_ocr() -> None:
    clock = _FakeClock()
    first = Image.new("RGB", (100, 50), "black")
    second = Image.new("RGB", (100, 50), "white")
    captures = 0
    beeps: list[int] = []

    def capture() -> Image.Image:
        nonlocal captures
        captures += 1
        return (first if captures <= 3 else second).copy()

    def validate(image: Image.Image) -> dict[str, object]:
        result = _accept_viewport(first)
        result["scrollbar"] = {
            "available": True,
            "at_top": image.getpixel((0, 0)) == (0, 0, 0),
            "at_bottom": image.getpixel((0, 0)) != (0, 0, 0),
        }
        return result

    result = collect_scroll_session(
        capture,
        lambda _image: {
            "rows": [_row(name) for name in "ABCDEF"],
            "timing_seconds": {"ocr": 0.1},
        },
        config=ScrollScanConfig(
            idle_timeout=1.0,
            poll_interval=0.1,
            stable_frames=3,
            stable_duration=0.2,
        ),
        validate_viewport=validate,
        beep=lambda: beeps.append(1),
        clock=clock,
        sleeper=clock.sleep,
    )

    assert result["session"]["stop_reason"] == "bottom_reached"
    assert result["session"]["accepted_viewports"] == 2
    assert result["session"]["ocr_frames"] == 1
    assert result["session"]["duplicate_viewports_skipped"] == 1
    assert result["coverage"]["accepted_viewport_overlaps"] == [0, 6]
    assert result["coverage"]["coverage_complete"] is True
    assert len(beeps) == 2


def test_window_disappearance_returns_partial_rows_instead_of_losing_result() -> None:
    clock = _FakeClock()
    frame = Image.new("RGB", (100, 50), "black")
    captures = 0

    def capture() -> Image.Image:
        nonlocal captures
        captures += 1
        if captures > 3:
            raise WindowCaptureError("window does not exist")
        return frame.copy()

    result = collect_scroll_session(
        capture,
        lambda _image: {
            "rows": [_row(name) for name in "ABCDEF"],
            "timing_seconds": {"ocr": 0.1},
        },
        config=ScrollScanConfig(
            idle_timeout=1.0,
            poll_interval=0.1,
            stable_frames=3,
            stable_duration=0.2,
        ),
        validate_viewport=_accept_viewport,
        clock=clock,
        sleeper=clock.sleep,
    )

    assert result["session"]["stop_reason"] == "window_unavailable"
    assert result["session"]["unique_rows"] == 6
    assert result["coverage"]["coverage_complete"] is False


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
        validate_viewport=_accept_viewport,
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


def test_latest_stable_frame_is_queued_not_change_frame() -> None:
    clock = _FakeClock()
    first = Image.new("RGB", (100, 50), "black")
    second = Image.new("RGB", (100, 50), "white")
    captures = 0
    seen: list[tuple[int, int, int]] = []

    def capture() -> Image.Image:
        nonlocal captures
        captures += 1
        return (first if captures <= 3 else second).copy()

    def scanner(image: Image.Image) -> dict[str, object]:
        seen.append(image.getpixel((0, 0)))
        names = "ABCDEF" if image.getpixel((0, 0)) == (0, 0, 0) else "DEFGHI"
        return {"rows": [_row(name) for name in names], "timing_seconds": {"ocr": 0.1}}

    collect_scroll_session(
        capture,
        scanner,
        config=ScrollScanConfig(
            idle_timeout=0.6,
            poll_interval=0.1,
            stable_frames=3,
            stable_duration=0.2,
        ),
        validate_viewport=_accept_viewport,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert seen == [(0, 0, 0), (255, 255, 255)]


def test_insufficient_stable_frames_are_not_queued() -> None:
    clock = _FakeClock()
    black = Image.new("RGB", (100, 50), "black")
    white = Image.new("RGB", (100, 50), "white")
    captures = 0

    def capture() -> Image.Image:
        nonlocal captures
        captures += 1
        if captures > 8:
            raise KeyboardInterrupt
        return (black if captures % 2 else white).copy()

    calls = 0

    def scanner(_image: Image.Image) -> dict[str, object]:
        nonlocal calls
        calls += 1
        names = "ABCDEF" if _image.getpixel((0, 0)) == (0, 0, 0) else "DEFGHI"
        return {"rows": [_row(name) for name in names], "timing_seconds": {"ocr": 0.1}}

    result = collect_scroll_session(
        capture,
        scanner,
        config=ScrollScanConfig(
            idle_timeout=1.0,
            poll_interval=0.1,
            stable_frames=3,
        ),
        validate_viewport=_accept_viewport,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert calls == 0
    assert result["session"]["stop_reason"] == "user_interrupt"


def test_overlap_zero_viewport_is_rejected_without_beep() -> None:
    clock = _FakeClock()
    frames = [
        Image.new("RGB", (100, 50), "black"),
        Image.new("RGB", (100, 50), "black"),
        Image.new("RGB", (100, 50), "black"),
        Image.new("RGB", (100, 50), "white"),
        Image.new("RGB", (100, 50), "white"),
        Image.new("RGB", (100, 50), "white"),
        Image.new("RGB", (100, 50), "black"),
        Image.new("RGB", (100, 50), "black"),
        Image.new("RGB", (100, 50), "black"),
    ]
    index = 0
    beeps: list[int] = []
    logs: list[str] = []

    def capture() -> Image.Image:
        nonlocal index
        image = frames[min(index, len(frames) - 1)]
        index += 1
        return image.copy()

    def validate_without_bottom(image: Image.Image) -> dict[str, object]:
        result = _accept_viewport(image)
        result["scrollbar"] = {
            "available": True,
            "at_top": image.getpixel((0, 0)) == (0, 0, 0),
            "at_bottom": False,
        }
        return result

    result = collect_scroll_session(
        capture,
        lambda image: {
            "rows": [
                _row(name)
                for name in (
                    "ABCDEF" if image.getpixel((0, 0)) == (0, 0, 0) else "DEFGHI"
                )
            ],
            "timing_seconds": {"ocr": 0.1},
        },
        config=ScrollScanConfig(
            idle_timeout=0.6,
            poll_interval=0.1,
            stable_frames=3,
            stable_duration=0.2,
            motion_threshold=0.02,
            duplicate_threshold=1.0 - 1e-6,
        ),
        validate_viewport=validate_without_bottom,
        notify=logs.append,
        beep=lambda: beeps.append(1),
        clock=clock,
        sleeper=clock.sleep,
    )
    assert result["session"]["accepted_viewports"] == 2
    assert result["session"]["rejected_overlap_zero"] >= 1
    assert result["session"]["change_events"] >= 2
    assert len(beeps) == 2
    assert any("scroll up slightly" in message for message in logs)


def test_separator_motion_must_stop_before_accept_beep() -> None:
    clock = _FakeClock()
    frame = Image.new("RGB", (100, 50), "black")
    captures = 0
    beeps: list[int] = []

    def capture() -> Image.Image:
        nonlocal captures
        captures += 1
        if captures > 8:
            raise KeyboardInterrupt
        return frame.copy()

    def validate(image: Image.Image) -> dict[str, object]:
        result = _accept_viewport(image)
        shift = [0, 3, 6, 6, 6, 6, 6, 6][captures - 1]
        result["separator_positions"] = [
            value + shift for value in result["separator_positions"]
        ]
        return result

    result = collect_scroll_session(
        capture,
        lambda _image: {
            "rows": [_row(name) for name in "ABCDEF"],
            "timing_seconds": {"ocr": 0.1},
        },
        config=ScrollScanConfig(
            idle_timeout=1.0,
            poll_interval=0.1,
            stable_frames=3,
            stable_duration=0.2,
        ),
        validate_viewport=validate,
        beep=lambda: beeps.append(captures),
        clock=clock,
        sleeper=clock.sleep,
    )

    assert beeps == [5]
    assert result["session"]["accepted_viewports"] == 1
    assert result["session"]["stop_reason"] == "user_interrupt"


def test_first_viewport_is_rejected_when_scrollbar_is_not_at_top() -> None:
    clock = _FakeClock()
    frame = Image.new("RGB", (100, 50), "white")
    logs: list[str] = []
    beeps: list[int] = []

    result = collect_scroll_session(
        lambda: frame.copy(),
        lambda _image: {
            "rows": [_row(name) for name in "DEFGHI"],
            "timing_seconds": {"ocr": 0.1},
        },
        config=ScrollScanConfig(
            idle_timeout=0.6,
            poll_interval=0.1,
            stable_frames=3,
            stable_duration=0.2,
        ),
        validate_viewport=_accept_viewport,
        notify=logs.append,
        beep=lambda: beeps.append(1),
        clock=clock,
        sleeper=clock.sleep,
    )

    assert result["session"]["accepted_viewports"] == 0
    assert result["session"]["rejected_not_at_top"] == 1
    assert result["coverage"]["coverage_complete"] is False
    assert not beeps
    assert any("scroll to top" in message for message in logs)


def test_accept_beep_and_log_fire_once_per_viewport() -> None:
    clock = _FakeClock()
    frames = [Image.new("RGB", (100, 50), color) for color in ("black",) * 3 + ("white",) * 3]
    index = 0
    beeps: list[int] = []
    logs: list[str] = []

    def capture() -> Image.Image:
        nonlocal index
        image = frames[min(index, len(frames) - 1)]
        index += 1
        return image.copy()

    result = collect_scroll_session(
        capture,
        lambda image: {
            "rows": [
                _row(name)
                for name in (
                    "ABCDEF" if image.getpixel((0, 0)) == (0, 0, 0) else "DEFGHI"
                )
            ],
            "timing_seconds": {"ocr": 0.1},
        },
        config=ScrollScanConfig(
            idle_timeout=0.6,
            poll_interval=0.1,
            stable_frames=3,
            stable_duration=0.2,
        ),
        validate_viewport=_accept_viewport,
        notify=logs.append,
        beep=lambda: beeps.append(1),
        clock=clock,
        sleeper=clock.sleep,
    )
    assert result["session"]["accepted_viewports"] == 2
    assert len(beeps) == 2
    assert sum("accepted" in log for log in logs) == 2


def test_scan_window_cli_keeps_m2_result_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"rows": [], "capture": {"capture_size": [1920, 1080]}}
    monkeypatch.setattr(cli, "scan_window", lambda **_kwargs: payload)
    written: list[object] = []
    monkeypatch.setattr(cli, "_write_json", lambda value, _output: written.append(value))
    assert cli.main(["scan-window"]) == 0
    assert written == [payload]
