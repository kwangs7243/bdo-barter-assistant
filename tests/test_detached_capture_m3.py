from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from bdo_barter_assistant.barter.pipeline import scan_barter_frame
from bdo_barter_assistant.barter.scroll_scan import _discover_detached_region, _validate_viewport
from bdo_barter_assistant.capture.region import Region
from bdo_barter_assistant.capture.windows import (
    ScreenRect,
    WindowInfo,
    WindowSelectionError,
    capture_client_region,
    select_scroll_target,
)
from bdo_barter_assistant.ocr.layout import (
    DETACHED_BARTER_LAYOUT,
    detect_row_separator_bands,
    segment_complete_rows,
)


ROOT = Path(__file__).resolve().parents[1]
DETACHED_SAMPLE = ROOT / "barter_detached_1023x713.png"
PHASE_A_SAMPLE = ROOT / "tests" / "fixtures" / "detached_scroll_phase_a_1023x451.png"


def _window(*, title: str, process: str = "BlackDesert64.exe", hwnd: int = 1) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        title=title,
        process=process,
        process_path=f"C:/Game/{process}",
        pid=100 + hwnd,
        window_rect=ScreenRect(90, 80, 1113, 793),
        client_rect_screen=ScreenRect(100, 100, 1123, 813),
        dpi=96,
        visible=True,
        minimized=False,
    )


def test_detached_window_is_selected_before_main_window() -> None:
    detached = _window(title="Panel_Window_Barter_Search", hwnd=10)
    main = _window(title="검은사막 - 530702", hwnd=11)
    selected, mode, is_detached = select_scroll_target([main, detached])
    assert selected.hwnd == 10
    assert mode == "detached_barter_window"
    assert is_detached is True


def test_main_window_is_rejected_when_detached_window_is_absent() -> None:
    main = _window(title="검은사막 - 530702")
    with pytest.raises(WindowSelectionError, match="detached"):
        select_scroll_target([main])


def test_explicit_main_window_is_rejected_for_scroll_collection() -> None:
    main = _window(title="검은사막 - 530702")
    with pytest.raises(WindowSelectionError, match="requires the detached"):
        select_scroll_target([main], hwnd=main.hwnd)


def test_detached_roi_capture_uses_screen_relative_client_coordinates() -> None:
    window = _window(title="Panel_Window_Barter_Search")
    seen: list[tuple[int, int, int, int]] = []

    def grabber(bbox: tuple[int, int, int, int]) -> Image.Image:
        seen.append(bbox)
        return Image.new("RGB", (300, 200), "black")

    image = capture_client_region(window, Region(20, 30, 300, 200), grabber=grabber)
    assert seen == [(120, 130, 420, 330)]
    assert image.size == (300, 200)


def test_detached_roi_bootstrap_uses_complete_rows_only() -> None:
    image = Image.open("reference/samples/barter_cropped.png").convert("RGB")
    region, complete_rows = _discover_detached_region(image)
    assert complete_rows == 6
    assert region.x == 0
    assert region.width == image.width
    assert region.as_list() == [0, 0, 987, 490]
    assert _validate_viewport(image)["complete_rows"] == 6
    assert _validate_viewport(image)["accepted"] is True


def test_detached_roi_bootstrap_keeps_full_visible_list_viewport() -> None:
    with Image.open(DETACHED_SAMPLE) as source:
        image = source.convert("RGB")

    region, complete_rows = _discover_detached_region(image)

    assert complete_rows == 6
    assert region.as_list() == [0, 220, 1023, 493]


def test_separator_detection_is_independent_of_scroll_phase() -> None:
    with Image.open(PHASE_A_SAMPLE) as source:
        phase_a = source.convert("RGB")
    with Image.open(DETACHED_SAMPLE) as source:
        full = source.convert("RGB")
    region, _ = _discover_detached_region(full)
    phase_b = full.crop(
        (region.x, region.y, region.x + region.width, region.y + region.height)
    )

    phase_a_bands = detect_row_separator_bands(phase_a)
    phase_b_bands = detect_row_separator_bands(phase_b)
    phase_a_positions = [round((top + bottom) / 2) for top, bottom in phase_a_bands]
    phase_b_positions = [round((top + bottom) / 2) for top, bottom in phase_b_bands]
    phase_a_rows = segment_complete_rows(phase_a)
    phase_b_rows = segment_complete_rows(phase_b)

    assert phase_a_positions == [36, 111, 186, 261, 336, 411]
    assert phase_b_positions == [2, 77, 152, 227, 302, 377, 452, 489]
    assert [(row.top, row.bottom) for row in phase_a_rows] == [
        (39, 109),
        (114, 184),
        (189, 259),
        (264, 334),
        (339, 409),
    ]
    assert len(phase_b_rows) == 6


def test_detached_layout_profile_reads_real_six_row_capture() -> None:
    with Image.open(DETACHED_SAMPLE) as source:
        image = source.convert("RGB")
    region, complete_rows = _discover_detached_region(image)

    result = scan_barter_frame(
        image,
        region=region,
        layout_profile=DETACHED_BARTER_LAYOUT,
        source_label=str(DETACHED_SAMPLE),
    )

    assert complete_rows == 6
    assert result["layout_profile"] == "detached_barter_1023x713"
    assert result["coverage"]["complete_rows_detected"] == 6
    assert sum(row["island"]["value"] is not None for row in result["rows"]) == 6
    assert sum(row["remaining_count"] is not None for row in result["rows"]) == 6
    # Item dictionary coverage is intentionally measured, not used as golden
    # truth: unseen live items may not exist in the current reference list.
    assert sum(row["to_item"]["value"] is not None for row in result["rows"]) >= 5
    assert all(row["review_required"] for row in result["rows"])
