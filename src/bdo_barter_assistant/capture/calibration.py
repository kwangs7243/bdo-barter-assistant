from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from bdo_barter_assistant.capture.region import NormalizedRegion, Region


REFERENCE_CLIENT_SIZE = (1920, 1080)
REFERENCE_BARTER_REGION = Region(464, 404, 987, 490)
DEFAULT_NORMALIZED_REGION = NormalizedRegion.from_pixels(
    REFERENCE_BARTER_REGION, REFERENCE_CLIENT_SIZE
)


@dataclass(frozen=True)
class CaptureCalibration:
    roi: NormalizedRegion
    reference_client_size: tuple[int, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "coordinate_space": "client_normalized",
            "roi": self.roi.as_list(),
            "reference_client_size": list(self.reference_client_size),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "CaptureCalibration":
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported capture calibration schema")
        roi = payload.get("roi")
        size = payload.get("reference_client_size")
        if not isinstance(roi, list) or len(roi) != 4:
            raise ValueError("calibration roi must contain four values")
        if not isinstance(size, list) or len(size) != 2:
            raise ValueError("calibration reference_client_size must contain two values")
        return cls(
            roi=NormalizedRegion(*(float(value) for value in roi)),
            reference_client_size=(int(size[0]), int(size[1])),
        )


def default_calibration_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "BDOBarterAssistant" / "capture-calibration.json"


def load_calibration(path: Path) -> CaptureCalibration:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("capture calibration must be a JSON object")
    return CaptureCalibration.from_dict(payload)


def save_calibration(
    path: Path, region: Region, client_size: tuple[int, int]
) -> CaptureCalibration:
    calibration = CaptureCalibration(
        roi=NormalizedRegion.from_pixels(region, client_size),
        reference_client_size=client_size,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(calibration.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return calibration


def resolve_barter_region(
    client_size: tuple[int, int],
    *,
    explicit_region: Region | None = None,
    calibration_path: Path | None = None,
) -> tuple[Region, NormalizedRegion, str]:
    if explicit_region is not None:
        normalized = NormalizedRegion.from_pixels(explicit_region, client_size)
        return explicit_region, normalized, "explicit"
    if calibration_path is not None and calibration_path.exists():
        calibration = load_calibration(calibration_path)
        return calibration.roi.to_pixels(client_size), calibration.roi, "calibration"
    return (
        DEFAULT_NORMALIZED_REGION.to_pixels(client_size),
        DEFAULT_NORMALIZED_REGION,
        "m1_reference_normalized",
    )
