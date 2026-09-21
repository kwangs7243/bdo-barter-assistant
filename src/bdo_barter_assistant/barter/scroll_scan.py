from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any, Callable

from PIL import Image

from bdo_barter_assistant.barter.collection import (
    finalize_collected_rows,
    merge_viewport_rows,
)
from bdo_barter_assistant.barter.pipeline import scan_barter_frame
from bdo_barter_assistant.capture.calibration import (
    default_calibration_path,
    resolve_barter_region,
)
from bdo_barter_assistant.capture.change import (
    ViewportChangeConfig,
    viewport_changed,
    viewport_difference,
    viewport_fingerprint,
)
from bdo_barter_assistant.capture.region import Region, crop_region
from bdo_barter_assistant.capture.windows import (
    WindowInfo,
    capture_client_area,
    configure_process_dpi_awareness,
    enumerate_top_level_windows,
    get_window_info,
    select_window,
)


@dataclass(frozen=True)
class ScrollScanConfig:
    idle_timeout: float = 12.0
    poll_interval: float = 0.25
    # The game list can be paged quickly; one stable poll is enough to queue
    # a viewport while the OCR worker processes it independently.
    debounce: float = 0.2
    change_threshold: float = 0.02

    def __post_init__(self) -> None:
        if self.idle_timeout <= 0:
            raise ValueError("idle timeout must be positive")
        if self.poll_interval <= 0:
            raise ValueError("poll interval must be positive")
        if self.debounce < 0:
            raise ValueError("debounce cannot be negative")
        if self.idle_timeout <= self.debounce:
            raise ValueError("idle timeout must be greater than debounce")
        ViewportChangeConfig(threshold=self.change_threshold)


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def collect_scroll_session(
    capture_viewport: Callable[[], Image.Image],
    scan_viewport: Callable[[Image.Image], dict[str, Any]],
    *,
    config: ScrollScanConfig | None = None,
    debug_dir: Path | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Collect stable, changed viewports until inactivity or Ctrl+C."""
    config = config or ScrollScanConfig()
    change_config = ViewportChangeConfig(threshold=config.change_threshold)
    started_at = _iso_now()
    started = clock()
    last_change_at = started
    candidate_since = started
    candidate_image: Image.Image | None = None
    candidate_fingerprint: Image.Image | None = None
    candidate_processed = False
    processed_fingerprints: list[Image.Image] = []
    collected_rows: list[dict[str, Any]] = []
    captured_frames = 0
    duplicate_skips = 0
    ocr_frames = 0
    queued_viewports = 0
    ocr_total = 0.0
    change_events = 0
    stop_reason = "idle_timeout"
    ocr_jobs: Queue[tuple[int, Image.Image] | None] = Queue()
    ocr_errors: list[BaseException] = []

    def ocr_worker() -> None:
        nonlocal ocr_frames, ocr_total, collected_rows
        while True:
            job = ocr_jobs.get()
            try:
                if job is None:
                    return
                viewport_index, viewport_image = job
                result = scan_viewport(viewport_image)
                ocr_frames += 1
                timings = result.get("timing_seconds", {})
                ocr_total += float(timings.get("ocr", timings.get("total", 0.0)))
                collected_rows = merge_viewport_rows(
                    collected_rows,
                    list(result.get("rows", [])),
                    viewport_index=viewport_index,
                )
                if debug_dir is not None:
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    viewport_image.save(debug_dir / f"viewport_{viewport_index:03d}.png")
                    (debug_dir / f"viewport_{viewport_index:03d}.json").write_text(
                        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
            except BaseException as error:  # propagate after the capture loop drains
                ocr_errors.append(error)
            finally:
                ocr_jobs.task_done()

    worker = Thread(target=ocr_worker, name="bdo-ocr-worker", daemon=True)
    worker.start()

    try:
        while True:
            image = capture_viewport().convert("RGB")
            captured_frames += 1
            now = clock()
            fingerprint = viewport_fingerprint(image, change_config)

            if candidate_fingerprint is None:
                candidate_image = image
                candidate_fingerprint = fingerprint
                candidate_since = now
                last_change_at = now
                candidate_processed = False
            elif viewport_changed(candidate_fingerprint, fingerprint, change_config):
                candidate_image = image
                candidate_fingerprint = fingerprint
                candidate_since = now
                last_change_at = now
                candidate_processed = False
                change_events += 1
            elif candidate_processed:
                duplicate_skips += 1

            stable_for = now - candidate_since
            if (
                not candidate_processed
                and candidate_image is not None
                and candidate_fingerprint is not None
                and stable_for >= config.debounce
            ):
                seen_before = any(
                    viewport_difference(candidate_fingerprint, previous)
                    <= config.change_threshold
                    for previous in processed_fingerprints
                )
                if seen_before:
                    duplicate_skips += 1
                else:
                    processed_fingerprints.append(candidate_fingerprint.copy())
                    ocr_jobs.put((queued_viewports, candidate_image.copy()))
                    queued_viewports += 1
                candidate_processed = True

            now = clock()
            if candidate_processed and now - last_change_at >= config.idle_timeout:
                break
            sleeper(config.poll_interval)
    except KeyboardInterrupt:
        stop_reason = "user_interrupt"
    finally:
        ocr_jobs.put(None)
        ocr_jobs.join()
        worker.join()

    if ocr_errors:
        raise RuntimeError("OCR worker failed") from ocr_errors[0]

    ended = clock()
    rows = finalize_collected_rows(collected_rows)
    review_count = sum(bool(row.get("review_required")) for row in rows)
    return {
        "session": {
            "started_at": started_at,
            "ended_at": _iso_now(),
            "stop_reason": stop_reason,
            "captured_frames": captured_frames,
            "ocr_frames": ocr_frames,
            "queued_viewports": queued_viewports,
            "duplicate_viewports_skipped": duplicate_skips,
            "change_events": change_events,
            "duration_sec": round(ended - started, 4),
            "average_ocr_seconds": round(ocr_total / ocr_frames, 4)
            if ocr_frames
            else 0.0,
            "unique_rows": len(rows),
            "review_required_rows": review_count,
            "settings": {
                "idle_timeout": config.idle_timeout,
                "poll_interval": config.poll_interval,
                "debounce": config.debounce,
                "change_threshold": config.change_threshold,
            },
        },
        "coverage": {
            "scan_started": True,
            "scan_finished_by_user": stop_reason == "user_interrupt",
            "unreviewed_count": review_count,
        },
        "rows": rows,
        "network_requests": 0,
    }


def scan_scroll_window(
    *,
    hwnd: int | None = None,
    title: str | None = None,
    process: str | None = None,
    region: Region | None = None,
    calibration_path: Path | None = None,
    scale: int = 4,
    config: ScrollScanConfig | None = None,
    countdown: int = 3,
    debug_dir: Path | None = None,
    notify: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Select a game window and collect user-scrolled barter viewports."""
    if countdown < 0:
        raise ValueError("countdown cannot be negative")
    dpi_awareness = configure_process_dpi_awareness()
    selected = select_window(
        enumerate_top_level_windows(), hwnd=hwnd, title=title, process=process
    )
    selected = get_window_info(selected.hwnd)
    resolved_path = calibration_path or default_calibration_path()
    barter_region, normalized_region, region_source = resolve_barter_region(
        selected.client_size,
        explicit_region=region,
        calibration_path=resolved_path,
    )

    for remaining in range(countdown, 0, -1):
        if notify is not None:
            notify(f"scan-scroll starts in {remaining}...")
        time.sleep(1)

    def capture_viewport() -> Image.Image:
        current = get_window_info(selected.hwnd)
        captured = capture_client_area(current)
        return crop_region(captured.image, barter_region)

    def scan_viewport(image: Image.Image) -> dict[str, Any]:
        return scan_barter_frame(
            image,
            source_label=f"window:{selected.hwnd}:scroll",
            scale=scale,
        )

    result = collect_scroll_session(
        capture_viewport,
        scan_viewport,
        config=config,
        debug_dir=debug_dir,
    )
    result["capture"] = {
        "method": "desktop_client_area/ImageGrab",
        "window": selected.to_dict(),
        "dpi_awareness": dpi_awareness,
        "barter_region": barter_region.as_list(),
        "barter_region_normalized": normalized_region.as_list(),
        "barter_region_source": region_source,
        "calibration_path": str(resolved_path),
        "debug_dir": str(debug_dir) if debug_dir else None,
    }
    return result
