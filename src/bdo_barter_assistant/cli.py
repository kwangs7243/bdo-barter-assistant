from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from bdo_barter_assistant.barter.pipeline import scan_barter_image
from bdo_barter_assistant.barter.scroll_scan import ScrollScanConfig, scan_scroll_window
from bdo_barter_assistant.barter.window_scan import scan_window
from bdo_barter_assistant.capture.region import Region
from bdo_barter_assistant.capture.windows import (
    WindowCaptureError,
    WindowSelectionError,
    enumerate_top_level_windows,
    filter_windows,
)
from bdo_barter_assistant.evaluation import evaluate_golden
from bdo_barter_assistant.reference_extract import write_reference_dictionary


def _write_json(payload: Any, output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")


def _region(value: str | None) -> Region | None:
    return Region.parse(value) if value else None


def _hwnd(value: str) -> int:
    return int(value, 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BDO barter local OCR and window capture")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract-reference")
    extract.add_argument("html", type=Path)
    extract.add_argument("output", type=Path)

    scan = subparsers.add_parser("scan")
    scan.add_argument("image", type=Path)
    scan.add_argument("--region", help="manual crop as x,y,width,height")
    scan.add_argument("--scale", type=int, default=4)
    scan.add_argument("--output", type=Path)

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("image", type=Path)
    evaluate.add_argument("--golden", type=Path, required=True)
    evaluate.add_argument("--region", help="manual crop as x,y,width,height")
    evaluate.add_argument("--scale", type=int, default=4)
    evaluate.add_argument("--repeat", type=int, default=1)
    evaluate.add_argument("--output", type=Path)

    windows = subparsers.add_parser("windows")
    windows.add_argument("--title", help="case-insensitive title substring")
    windows.add_argument("--process", help="case-insensitive executable substring")
    windows.add_argument("--game-only", action="store_true")
    windows.add_argument("--output", type=Path)

    scan_window_parser = subparsers.add_parser("scan-window")
    scan_window_parser.add_argument("--hwnd", type=_hwnd, help="decimal or 0x-prefixed handle")
    scan_window_parser.add_argument("--title", help="case-insensitive title substring")
    scan_window_parser.add_argument("--process", help="case-insensitive executable substring")
    scan_window_parser.add_argument("--region", help="client-relative x,y,width,height")
    scan_window_parser.add_argument("--calibration", type=Path)
    scan_window_parser.add_argument("--save-calibration", action="store_true")
    scan_window_parser.add_argument("--debug-capture", type=Path)
    scan_window_parser.add_argument("--scale", type=int, default=4)
    scan_window_parser.add_argument("--output", type=Path)

    scan_scroll = subparsers.add_parser("scan-scroll")
    scan_scroll.add_argument("--hwnd", type=_hwnd, help="decimal or 0x-prefixed handle")
    scan_scroll.add_argument("--title", help="case-insensitive title substring")
    scan_scroll.add_argument("--process", help="case-insensitive executable substring")
    scan_scroll.add_argument("--region", help="client-relative x,y,width,height")
    scan_scroll.add_argument("--calibration", type=Path)
    scan_scroll.add_argument("--scale", type=int, default=4)
    scan_scroll.add_argument("--idle-timeout", type=float, default=12.0)
    scan_scroll.add_argument("--poll-interval", type=float, default=0.25)
    scan_scroll.add_argument("--debounce", type=float, default=0.6)
    scan_scroll.add_argument("--change-threshold", type=float, default=0.02)
    scan_scroll.add_argument("--countdown", type=int, default=3)
    scan_scroll.add_argument(
        "--debug",
        nargs="?",
        const=Path(".debug/scroll-session"),
        type=Path,
        help="save OCR viewports/results, optionally to a directory",
    )
    scan_scroll.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "extract-reference":
        write_reference_dictionary(args.html, args.output)
        return 0
    if args.command == "scan":
        result = scan_barter_image(
            args.image, region=_region(args.region), scale=args.scale
        )
        _write_json(result, args.output)
        return 0
    if args.command == "evaluate":
        result = evaluate_golden(
            args.image,
            args.golden,
            region=_region(args.region),
            scale=args.scale,
            repeat=args.repeat,
        )
        _write_json(result, args.output)
        return 0
    if args.command == "windows":
        try:
            found = filter_windows(
                enumerate_top_level_windows(),
                title=args.title,
                process=args.process,
                game_only=args.game_only,
            )
        except WindowCaptureError as error:
            _write_json({"error": str(error)}, None)
            return 2
        _write_json([window.to_dict() for window in found], args.output)
        return 0
    if args.command == "scan-window":
        try:
            result = scan_window(
                hwnd=args.hwnd,
                title=args.title,
                process=args.process,
                region=_region(args.region),
                calibration_path=args.calibration,
                save_region=args.save_calibration,
                debug_capture=args.debug_capture,
                scale=args.scale,
            )
        except WindowSelectionError as error:
            _write_json(
                {
                    "error": str(error),
                    "candidates": [item.to_dict() for item in error.candidates],
                },
                None,
            )
            return 2
        except (WindowCaptureError, ValueError) as error:
            _write_json({"error": str(error)}, None)
            return 2
        _write_json(result, args.output)
        return 0
    if args.command == "scan-scroll":
        try:
            result = scan_scroll_window(
                hwnd=args.hwnd,
                title=args.title,
                process=args.process,
                region=_region(args.region),
                calibration_path=args.calibration,
                scale=args.scale,
                config=ScrollScanConfig(
                    idle_timeout=args.idle_timeout,
                    poll_interval=args.poll_interval,
                    debounce=args.debounce,
                    change_threshold=args.change_threshold,
                ),
                countdown=args.countdown,
                debug_dir=args.debug,
                notify=lambda message: print(message, file=sys.stderr, flush=True),
            )
        except WindowSelectionError as error:
            _write_json(
                {
                    "error": str(error),
                    "candidates": [item.to_dict() for item in error.candidates],
                },
                None,
            )
            return 2
        except (WindowCaptureError, ValueError) as error:
            _write_json({"error": str(error)}, None)
            return 2
        session = result["session"]
        print(
            "scan-scroll complete: "
            f"rows={session['unique_rows']}, "
            f"review_required={session['review_required_rows']}, "
            f"ocr_viewports={session['ocr_frames']}, "
            f"duplicate_skips={session['duplicate_viewports_skipped']}, "
            f"duration={session['duration_sec']}s, "
            f"avg_ocr={session['average_ocr_seconds']}s",
            file=sys.stderr,
        )
        _write_json(result, args.output)
        return 0
    raise AssertionError(f"unknown command: {args.command}")
