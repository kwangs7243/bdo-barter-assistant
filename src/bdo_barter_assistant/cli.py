from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from bdo_barter_assistant.barter.pipeline import scan_barter_image
from bdo_barter_assistant.capture.region import Region
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BDO barter OCR M1 proof of concept")
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
    raise AssertionError(f"unknown command: {args.command}")

