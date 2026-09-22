from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any, Callable

from PIL import Image

from bdo_barter_assistant.barter.collection import (
    finalize_collected_rows,
    merge_viewport_rows_by_visual_overlap,
    row_visual_fingerprint,
    visual_overlap_length,
)
from bdo_barter_assistant.barter.pipeline import scan_barter_frame
from bdo_barter_assistant.barter.trade_contract import normalize_trade_observation
from bdo_barter_assistant.capture.calibration import (
    default_calibration_path,
    resolve_barter_region,
)
from bdo_barter_assistant.capture.change import (
    ViewportChangeConfig,
    viewport_difference,
    viewport_fingerprint,
)
from bdo_barter_assistant.capture.region import NormalizedRegion, Region
from bdo_barter_assistant.capture.windows import (
    WindowCaptureError,
    capture_client_area,
    capture_client_region,
    configure_process_dpi_awareness,
    enumerate_top_level_windows,
    get_window_info,
    select_scroll_target,
)
from bdo_barter_assistant.ocr.layout import (
    DETACHED_BARTER_LAYOUT,
    REFERENCE_LAYOUT,
    detect_row_separator_bands,
    segment_complete_rows,
)
from bdo_barter_assistant.reference_data import load_ocr_dictionary


@dataclass(frozen=True)
class ScrollScanConfig:
    idle_timeout: float = 12.0
    poll_interval: float = 0.1
    stable_frames: int = 8
    stable_duration: float = 0.7
    motion_threshold: float = 0.02
    duplicate_threshold: float = 0.005
    visual_overlap_threshold: float = 0.02

    # Compatibility aliases for the first M3 implementation.
    debounce: float | None = None
    change_threshold: float | None = None

    def __post_init__(self) -> None:
        if self.idle_timeout <= 0:
            raise ValueError("idle timeout must be positive")
        if self.poll_interval <= 0:
            raise ValueError("poll interval must be positive")
        if self.stable_frames < 2:
            raise ValueError("stable frames must be at least 2")
        if self.stable_duration < 0:
            raise ValueError("stable duration cannot be negative")
        for name, value in (
            ("motion threshold", self.motion_threshold),
            ("duplicate threshold", self.duplicate_threshold),
            ("visual overlap threshold", self.visual_overlap_threshold),
        ):
            if not 0.0 < value < 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.change_threshold is not None:
            if not 0.0 < self.change_threshold < 1.0:
                raise ValueError("change threshold must be between 0 and 1")
            object.__setattr__(self, "motion_threshold", self.change_threshold)
        if self.debounce is not None:
            if self.debounce < 0:
                raise ValueError("debounce cannot be negative")
            frames = max(2, int(self.debounce / self.poll_interval) + 1)
            object.__setattr__(self, "stable_frames", frames)
            object.__setattr__(self, "stable_duration", self.debounce)
        if self.idle_timeout <= self.stable_duration:
            raise ValueError("idle timeout must be greater than stable duration")
        ViewportChangeConfig(threshold=self.motion_threshold)


@dataclass(frozen=True)
class _QueuedViewport:
    queue_index: int
    image: Image.Image
    metadata: dict[str, Any]


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _validate_viewport(image: Image.Image) -> dict[str, Any]:
    bands = detect_row_separator_bands(image)
    rows = segment_complete_rows(image)
    heights = [row.bottom - row.top for row in rows]
    geometry_valid = bool(rows) and all(60 <= height <= 80 for height in heights)
    return {
        "complete_rows": len(rows),
        "row_heights": heights,
        "separator_positions": [round((top + bottom) / 2) for top, bottom in bands],
        "row_fingerprints": [row_visual_fingerprint(row.image) for row in rows],
        "scrollbar": _detect_scrollbar_state(image),
        "geometry_valid": geometry_valid,
        "accepted": geometry_valid,
    }


def _detect_scrollbar_state(image: Image.Image) -> dict[str, Any]:
    """Measure the tan scrollbar thumb for top/bottom coverage markers."""
    if image.width < 40 or image.height < 20:
        return {"available": False, "at_top": False, "at_bottom": False}
    rgb = image.convert("RGB")
    left = image.width - 22
    right = image.width - 13
    thumb_rows: list[int] = []
    for y in range(image.height):
        matching = 0
        for x in range(left, right):
            red, green, blue = rgb.getpixel((x, y))
            if red >= 90 and green >= 70 and red > blue * 1.15:
                matching += 1
        if matching >= 4:
            thumb_rows.append(y)
    groups = _group_positions(thumb_rows)
    if not groups:
        return {"available": False, "at_top": False, "at_bottom": False}
    top, bottom = max(groups, key=lambda band: band[1] - band[0])
    if bottom - top < 8:
        return {"available": False, "at_top": False, "at_bottom": False}
    # The detached panel leaves a small bottom border below the scrollbar
    # track. Scale the allowance with the captured viewport instead of
    # requiring the thumb to reach the final image pixels.
    bottom_margin = max(10, round(image.height * 0.035))
    return {
        "available": True,
        "thumb_top": top,
        "thumb_bottom": bottom,
        "at_top": top <= 7,
        "at_bottom": bottom >= image.height - bottom_margin,
    }


def _group_positions(values: list[int]) -> list[tuple[int, int]]:
    groups: list[list[int]] = []
    for value in values:
        if not groups or value > groups[-1][-1] + 1:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [(group[0], group[-1]) for group in groups]


def _separator_geometry_matches(
    left: dict[str, Any], right: dict[str, Any], *, tolerance: int = 1
) -> bool:
    left_positions = list(left.get("separator_positions", []))
    right_positions = list(right.get("separator_positions", []))
    return len(left_positions) == len(right_positions) and all(
        abs(a - b) <= tolerance for a, b in zip(left_positions, right_positions)
    )


def _noop(_: str) -> None:
    return None


def _noop_beep() -> None:
    return None


def _discover_detached_region(image: Image.Image) -> tuple[Region, int]:
    """Derive a detached-window list ROI from its first complete rows.

    The bootstrap frame is captured once. Subsequent polls use the resulting
    client-relative ROI directly, so the 1920x1080 game window is never used
    for detached-window collection.
    """
    rows = segment_complete_rows(image)
    if not rows:
        raise WindowCaptureError(
            "detached barter list ROI could not be detected; pass --region"
        )
    # Bootstrap happens while the list is at the top. Keep the whole remaining
    # client height so later pixel-scroll phases cannot clip the final complete
    # row near the panel bottom.
    top = max(0, min(row.top for row in rows) - 5)
    return Region(0, top, image.width, image.height - top), len(rows)


def collect_scroll_session(
    capture_viewport: Callable[[], Image.Image],
    scan_viewport: Callable[[Image.Image], dict[str, Any]],
    *,
    config: ScrollScanConfig | None = None,
    debug_dir: Path | None = None,
    validate_viewport: Callable[[Image.Image], dict[str, Any]] | None = None,
    notify: Callable[[str], None] | None = None,
    beep: Callable[[], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Capture only complete, stable viewports while the user scrolls."""
    config = config or ScrollScanConfig()
    validator = validate_viewport or _validate_viewport
    log = notify or _noop
    accepted_beep = beep or _noop_beep
    change_config = ViewportChangeConfig(threshold=config.motion_threshold)
    started_at = _iso_now()
    started = clock()
    last_motion_at = started
    previous_fingerprint: Image.Image | None = None
    recent: deque[tuple[Image.Image, Image.Image, dict[str, Any], float, float]] = deque(
        maxlen=config.stable_frames
    )
    previous_validation: dict[str, Any] | None = None
    accepted_visual_rows: list[tuple[int, ...]] = []
    current_accepted = False
    accepted_any = False
    start_at_top = False
    end_at_bottom = False
    accepted_viewport_overlaps: list[int] = []
    collected_rows: list[dict[str, Any]] = []
    captured_frames = 0
    duplicate_skips = 0
    ocr_frames = 0
    queued_viewports = 0
    ocr_total = 0.0
    change_events = 0
    accepted_viewports = 0
    rejected_viewports = 0
    rejected_overlap_zero = 0
    rejected_not_at_top = 0
    stop_reason = "idle_timeout"
    ocr_jobs: Queue[_QueuedViewport | None] = Queue()
    ocr_errors: list[BaseException] = []

    def ocr_worker() -> None:
        nonlocal ocr_frames, ocr_total, collected_rows
        while True:
            job = ocr_jobs.get()
            try:
                if job is None:
                    return
                result = scan_viewport(job.image)
                ocr_frames += 1
                timings = result.get("timing_seconds", {})
                ocr_total += float(timings.get("ocr", timings.get("total", 0.0)))
                incoming = list(result.get("rows", []))
                overlap = int(job.metadata["visual_overlap"])
                expected_rows = int(job.metadata["complete_rows"])
                if len(incoming) != expected_rows:
                    raise RuntimeError(
                        "OCR segmentation changed after viewport acceptance: "
                        f"expected {expected_rows}, got {len(incoming)}"
                    )
                before = len(collected_rows)
                collected_rows = merge_viewport_rows_by_visual_overlap(
                    collected_rows,
                    incoming,
                    viewport_index=job.queue_index,
                    overlap=overlap,
                )
                added = len(collected_rows) - before
                review_count = sum(bool(row.get("review_required")) for row in incoming)
                first = incoming[0].get("island", {}).get("value") if incoming else None
                last = incoming[-1].get("island", {}).get("value") if incoming else None
                log(
                    f"[OCR  #{ocr_frames}] rows={len(incoming)} | overlap={overlap} "
                    f"| added={added} | total={len(collected_rows)} "
                    f"| review={review_count} | first={first} | last={last}"
                )
                if debug_dir is not None:
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    job.image.save(debug_dir / f"viewport_{job.queue_index + 1:03d}.png")
                    debug_payload = {"capture": job.metadata, "ocr": result}
                    (debug_dir / f"viewport_{job.queue_index + 1:03d}.json").write_text(
                        json.dumps(debug_payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
            except BaseException as error:
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
            validation = validator(image)
            motion_score = (
                0.0
                if previous_fingerprint is None
                else viewport_difference(previous_fingerprint, fingerprint)
            )
            geometry_moved = (
                previous_validation is not None
                and not _separator_geometry_matches(previous_validation, validation)
            )
            if motion_score > config.motion_threshold or geometry_moved:
                change_events += 1
                last_motion_at = now
                recent.clear()
                current_accepted = False
                recent.append((image, fingerprint, validation, 0.0, now))
            else:
                recent.append((image, fingerprint, validation, motion_score, now))
            previous_fingerprint = fingerprint
            previous_validation = validation

            stable_elapsed = recent[-1][4] - recent[0][4] if recent else 0.0
            stable = (
                len(recent) == config.stable_frames
                and stable_elapsed + 1e-9 >= config.stable_duration
                and all(
                    score <= config.motion_threshold and item.get("geometry_valid", False)
                    for _, _, item, score, _ in recent
                )
                and all(
                    _separator_geometry_matches(recent[0][2], item)
                    for _, _, item, _, _ in list(recent)[1:]
                )
            )
            if stable and not current_accepted:
                latest_image, _, validation, _, _ = recent[-1]
                row_fingerprints = list(validation.get("row_fingerprints", []))
                scrollbar = dict(validation.get("scrollbar", {}))
                visual_overlap = (
                    visual_overlap_length(
                        accepted_visual_rows,
                        row_fingerprints,
                        threshold=config.visual_overlap_threshold,
                    )
                    if accepted_visual_rows
                    else 0
                )
                added_rows = len(row_fingerprints) - visual_overlap
                metadata = {
                    "accepted_at": datetime.now().astimezone().isoformat(),
                    "stability_frames": config.stable_frames,
                    "stability_seconds": round(stable_elapsed, 4),
                    "motion_scores": [
                        round(score, 6) for _, _, _, score, _ in recent
                    ],
                    "complete_rows": validation.get("complete_rows", 0),
                    "row_heights": validation.get("row_heights", []),
                    "separator_positions": validation.get("separator_positions", []),
                    "geometry_valid": validation.get("geometry_valid", False),
                    "scrollbar": scrollbar,
                    "visual_overlap": visual_overlap,
                    "visual_added_rows": added_rows,
                    "queue_index": queued_viewports,
                }
                if not validation.get("accepted", False):
                    rejected_viewports += 1
                    log(
                        f"[SCAN] rejected | complete_rows={validation.get('complete_rows', 0)} "
                        f"| geometry_valid={validation.get('geometry_valid', False)}"
                    )
                elif not accepted_any and not (
                    scrollbar.get("available") and scrollbar.get("at_top")
                ):
                    rejected_viewports += 1
                    rejected_not_at_top += 1
                    log("[SCAN] rejected | reason=list_not_at_top | scroll to top")
                elif accepted_any and visual_overlap == 0:
                    rejected_viewports += 1
                    rejected_overlap_zero += 1
                    log(
                        "[SCAN] rejected | reason=no_visual_overlap "
                        "| scroll up slightly"
                    )
                elif accepted_any and added_rows == 0:
                    duplicate_skips += 1
                    if scrollbar.get("at_bottom"):
                        accepted_viewport_overlaps.append(visual_overlap)
                        accepted_viewports += 1
                        end_at_bottom = True
                        log(
                            f"[SCAN #{accepted_viewports}] accepted "
                            f"| complete_rows={validation.get('complete_rows', 0)} "
                            f"| overlap={visual_overlap} | added=0 "
                            f"| bottom=true | queued={queued_viewports}"
                        )
                        try:
                            accepted_beep()
                        except Exception:
                            pass
                    else:
                        log(
                            f"[SCAN] duplicate "
                            f"| complete_rows={validation.get('complete_rows', 0)} "
                            f"| visual_overlap={visual_overlap}"
                        )
                else:
                    if not accepted_any:
                        start_at_top = True
                    accepted_visual_rows.extend(row_fingerprints[visual_overlap:])
                    accepted_viewport_overlaps.append(visual_overlap)
                    end_at_bottom = bool(scrollbar.get("at_bottom"))
                    ocr_jobs.put(
                        _QueuedViewport(
                            queue_index=queued_viewports,
                            image=latest_image.copy(),
                            metadata=metadata,
                        )
                    )
                    queued_viewports += 1
                    accepted_viewports += 1
                    accepted_any = True
                    log(
                        f"[SCAN #{accepted_viewports}] accepted "
                        f"| complete_rows={validation.get('complete_rows', 0)} "
                        f"| overlap={visual_overlap} | added={added_rows} "
                        f"| queued={queued_viewports}"
                    )
                    try:
                        accepted_beep()
                    except Exception:
                        pass
                current_accepted = True

            if accepted_any and end_at_bottom:
                stop_reason = "bottom_reached"
                break

            if now - last_motion_at >= config.idle_timeout and (
                accepted_any or captured_frames > config.stable_frames
            ):
                break
            sleeper(config.poll_interval)
    except WindowCaptureError as error:
        stop_reason = "window_unavailable"
        log(f"[SCAN] stopped | reason=window_unavailable | {error}")
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
    if any("scheduler_contract" in row for row in rows):
        dictionary = load_ocr_dictionary()
        rows = [normalize_trade_observation(row, dictionary) for row in rows]
    review_count = sum(bool(row.get("review_required")) for row in rows)
    every_transition_has_overlap = all(
        overlap > 0 for overlap in accepted_viewport_overlaps[1:]
    )
    coverage_complete = bool(
        accepted_viewports
        and start_at_top
        and every_transition_has_overlap
        and end_at_bottom
    )
    return {
        "session": {
            "started_at": started_at,
            "ended_at": _iso_now(),
            "stop_reason": stop_reason,
            "captured_frames": captured_frames,
            "accepted_viewports": accepted_viewports,
            "rejected_viewports": rejected_viewports,
            "rejected_overlap_zero": rejected_overlap_zero,
            "rejected_not_at_top": rejected_not_at_top,
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
                "stable_frames": config.stable_frames,
                "stable_duration": config.stable_duration,
                "motion_threshold": config.motion_threshold,
                "duplicate_threshold": config.duplicate_threshold,
                "visual_overlap_threshold": config.visual_overlap_threshold,
            },
        },
        "coverage": {
            "scan_started": True,
            "scan_finished_by_user": stop_reason == "user_interrupt",
            "start_at_top": start_at_top,
            "every_transition_has_overlap": every_transition_has_overlap,
            "end_at_bottom": end_at_bottom,
            "coverage_complete": coverage_complete,
            "visual_rows_collected": len(accepted_visual_rows),
            "accepted_viewport_overlaps": accepted_viewport_overlaps,
            "unreviewed_count": review_count,
        },
        "rows": rows,
        "network_requests": 0,
    }


def _windows_beep() -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_OK)
    except (ImportError, RuntimeError, OSError):
        return None


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
    selected, capture_mode, detached = select_scroll_target(
        enumerate_top_level_windows(), hwnd=hwnd, title=title, process=process
    )
    selected = get_window_info(selected.hwnd)
    resolved_path = calibration_path or default_calibration_path()
    bootstrap_rows = None
    if detached:
        if region is None:
            bootstrap = capture_client_area(selected).image
            barter_region, bootstrap_rows = _discover_detached_region(bootstrap)
            normalized_region = NormalizedRegion.from_pixels(
                barter_region, selected.client_size
            )
            region_source = "detached_auto"
        else:
            normalized_region = NormalizedRegion.from_pixels(region, selected.client_size)
            barter_region = region
            region_source = "detached_explicit"
    else:
        barter_region, normalized_region, region_source = resolve_barter_region(
            selected.client_size,
            explicit_region=region,
            calibration_path=resolved_path,
        )

    if notify is not None:
        notify(
            f"[M3] capture target | title={selected.title} | hwnd={hex(selected.hwnd)} "
            f"| client={selected.client_size[0]}x{selected.client_size[1]} "
            f"| mode={capture_mode}"
        )
        if bootstrap_rows is not None:
            notify(
                f"[M3] detached list ROI auto-detected | region={barter_region.as_list()} "
                f"| complete_rows={bootstrap_rows}"
            )

    for remaining in range(countdown, 0, -1):
        if notify is not None:
            notify(f"scan-scroll starts in {remaining}...")
        time.sleep(1)

    def capture_viewport() -> Image.Image:
        current = get_window_info(selected.hwnd)
        return capture_client_region(current, barter_region)

    def scan_viewport(image: Image.Image) -> dict[str, Any]:
        return scan_barter_frame(
            image,
            source_label=f"window:{selected.hwnd}:scroll",
            scale=scale,
            layout_profile=DETACHED_BARTER_LAYOUT if detached else REFERENCE_LAYOUT,
        )

    result = collect_scroll_session(
        capture_viewport,
        scan_viewport,
        config=config,
        debug_dir=debug_dir,
        notify=notify,
        beep=_windows_beep,
    )
    result["capture"] = {
        "method": "desktop barter ROI/ImageGrab",
        "mode": capture_mode,
        "detached_window": detached,
        "window": selected.to_dict(),
        "dpi_awareness": dpi_awareness,
        "barter_region": barter_region.as_list(),
        "barter_region_normalized": normalized_region.as_list(),
        "barter_region_source": region_source,
        "ocr_layout_profile": (
            DETACHED_BARTER_LAYOUT.name if detached else REFERENCE_LAYOUT.name
        ),
        "detached_bootstrap_complete_rows": bootstrap_rows,
        "calibration_path": str(resolved_path),
        "debug_dir": str(debug_dir) if debug_dir else None,
    }
    return result
