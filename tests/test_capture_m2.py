from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from bdo_barter_assistant.barter.window_scan import scan_window
from bdo_barter_assistant.capture.calibration import (
    REFERENCE_BARTER_REGION,
    load_calibration,
    resolve_barter_region,
    save_calibration,
)
from bdo_barter_assistant.capture.region import NormalizedRegion, Region
from bdo_barter_assistant.capture.windows import (
    ScreenRect,
    WindowInfo,
    capture_client_area,
    select_window,
)


ROOT = Path(__file__).resolve().parents[1]
FULLSCREEN = ROOT / "reference" / "samples" / "barter_fullscreen.png"
GOLDEN = ROOT / "tests" / "fixtures" / "golden_rows.json"


def _window(*, hwnd: int = 42, title: str = "검은사막", process: str = "BlackDesert64.exe") -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        title=title,
        process=process,
        process_path=f"C:/Game/{process}",
        pid=100,
        window_rect=ScreenRect(90, 80, 2030, 1200),
        client_rect_screen=ScreenRect(100, 100, 2020, 1180),
        dpi=120,
        visible=True,
        minimized=False,
    )


def _values(row: dict[str, object]) -> dict[str, object]:
    return {
        "island": row["island"]["value"],
        "remaining_count": row["remaining_count"],
        "from_item": row["from_item"]["value"],
        "req_amount": row["req_amount"],
        "to_item": row["to_item"]["value"],
        "yield_amount": row["yield_amount"],
    }


def test_normalized_roi_scales_with_client_area() -> None:
    normalized = NormalizedRegion.from_pixels(REFERENCE_BARTER_REGION, (1920, 1080))
    assert normalized.to_pixels((1920, 1080)) == REFERENCE_BARTER_REGION
    assert normalized.to_pixels((2560, 1440)) == Region(619, 539, 1316, 653)


def test_calibration_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "capture.json"
    saved = save_calibration(path, REFERENCE_BARTER_REGION, (1920, 1080))
    loaded = load_calibration(path)
    region, normalized, source = resolve_barter_region(
        (1920, 1080), calibration_path=path
    )
    assert loaded == saved
    assert region == REFERENCE_BARTER_REGION
    assert normalized == saved.roi
    assert source == "calibration"


def test_window_selection_requires_unique_match() -> None:
    windows = [_window(hwnd=1), _window(hwnd=2, title="메모장", process="notepad.exe")]
    assert select_window(windows).hwnd == 1
    assert select_window(windows, hwnd=2).process == "notepad.exe"


def test_client_capture_uses_screen_client_rect_in_memory() -> None:
    window = _window()
    seen: list[tuple[int, int, int, int]] = []

    def grabber(bbox: tuple[int, int, int, int]) -> Image.Image:
        seen.append(bbox)
        return Image.new("RGB", (1920, 1080), "black")

    captured = capture_client_area(window, grabber=grabber)
    assert seen == [(100, 100, 2020, 1180)]
    assert captured.image.size == window.client_size


def test_virtual_window_frame_reaches_unchanged_m1_pipeline(tmp_path: Path) -> None:
    with Image.open(FULLSCREEN) as source:
        frame = source.convert("RGB")
    window = _window()
    result = scan_window(
        hwnd=window.hwnd,
        windows=[window],
        grabber=lambda _bbox: frame.copy(),
        refresh_window=False,
        calibration_path=tmp_path / "missing.json",
    )
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert result["capture"]["capture_size"] == [1920, 1080]
    assert result["capture"]["barter_region"] == REFERENCE_BARTER_REGION.as_list()
    assert result["capture"]["debug_capture"] is None
    assert result["coverage"]["complete_rows_detected"] == 6
    assert [_values(row) for row in result["rows"]] == golden
    assert not list(tmp_path.iterdir())
