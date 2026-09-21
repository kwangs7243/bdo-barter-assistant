from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from PIL import Image

from bdo_barter_assistant.barter.pipeline import scan_barter_frame
from bdo_barter_assistant.capture.calibration import (
    default_calibration_path,
    resolve_barter_region,
    save_calibration,
)
from bdo_barter_assistant.capture.region import Region
from bdo_barter_assistant.capture.windows import (
    WindowInfo,
    capture_client_area,
    configure_process_dpi_awareness,
    enumerate_top_level_windows,
    get_window_info,
    select_window,
)


def scan_window(
    *,
    hwnd: int | None = None,
    title: str | None = None,
    process: str | None = None,
    region: Region | None = None,
    calibration_path: Path | None = None,
    save_region: bool = False,
    debug_capture: Path | None = None,
    scale: int = 4,
    windows: Iterable[WindowInfo] | None = None,
    grabber: Callable[[tuple[int, int, int, int]], Image.Image] | None = None,
    refresh_window: bool = True,
) -> dict[str, object]:
    """Capture one visible client area and feed it to the unchanged M1 pipeline."""
    dpi_awareness = "injected"
    if windows is None:
        dpi_awareness = configure_process_dpi_awareness()
        windows = enumerate_top_level_windows()
    selected = select_window(windows, hwnd=hwnd, title=title, process=process)
    if refresh_window:
        selected = get_window_info(selected.hwnd)
    captured = capture_client_area(selected, grabber=grabber)

    resolved_path = calibration_path or default_calibration_path()
    barter_region, normalized_region, region_source = resolve_barter_region(
        captured.image.size,
        explicit_region=region,
        calibration_path=resolved_path,
    )
    if save_region:
        if region is None:
            raise ValueError("--save-calibration requires an explicit --region")
        save_calibration(resolved_path, region, captured.image.size)
        region_source = "explicit_saved"
    if debug_capture is not None:
        debug_capture.parent.mkdir(parents=True, exist_ok=True)
        captured.image.save(debug_capture)

    result = scan_barter_frame(
        captured.image,
        source_label=f"window:{selected.hwnd}",
        region=barter_region,
        scale=scale,
    )
    result["capture"] = {
        "method": "desktop_client_area/ImageGrab",
        "window": selected.to_dict(),
        "capture_size": list(captured.image.size),
        "dpi_awareness": dpi_awareness,
        "barter_region": barter_region.as_list(),
        "barter_region_normalized": normalized_region.as_list(),
        "barter_region_source": region_source,
        "calibration_path": str(resolved_path),
        "debug_capture": str(debug_capture) if debug_capture else None,
    }
    return result
