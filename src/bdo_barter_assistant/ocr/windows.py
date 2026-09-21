from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from PIL import Image


@dataclass(frozen=True)
class OcrText:
    text: str
    lines: tuple[str, ...]
    confidence: None = None


class WindowsOcrAdapter:
    """Batch adapter for the offline Windows 10 Korean OCR runtime."""

    def __init__(self, language: str = "ko", timeout_seconds: int = 30) -> None:
        self.language = language
        self.timeout_seconds = timeout_seconds
        self.script_path = Path(__file__).with_name("windows_ocr.ps1")

    def recognize_many(self, images: Mapping[str, Image.Image]) -> dict[str, OcrText]:
        if os.name != "nt":
            raise RuntimeError("Windows OCR is only available on Windows")
        if not images:
            return {}

        with tempfile.TemporaryDirectory(prefix="bdo-barter-ocr-") as directory:
            temp_dir = Path(directory)
            for key, image in sorted(images.items()):
                image.save(temp_dir / f"{key}.png", format="PNG")
            output_path = temp_dir / "ocr-result.json"
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.script_path),
                    "-ImageDirectory",
                    str(temp_dir),
                    "-Language",
                    self.language,
                    "-OutputPath",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                timeout=self.timeout_seconds,
                creationflags=creation_flags,
            )
            if completed.returncode != 0:
                stderr = completed.stderr.decode(errors="replace").strip()
                raise RuntimeError(f"Windows OCR failed: {stderr}")
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        observations: dict[str, OcrText] = {}
        for entry in payload:
            key = Path(entry["path"]).stem
            observations[key] = OcrText(
                text=entry["text"].strip(),
                lines=tuple(line.strip() for line in entry["lines"] if line.strip()),
            )
        return observations

