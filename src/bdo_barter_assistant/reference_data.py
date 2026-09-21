from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DICTIONARY_PATH = Path(__file__).resolve().parents[2] / "data" / "ocr_dictionary.json"


@dataclass(frozen=True)
class OcrDictionary:
    items: tuple[str, ...]
    islands: tuple[str, ...]


def load_ocr_dictionary(path: Path = DEFAULT_DICTIONARY_PATH) -> OcrDictionary:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return OcrDictionary(
        items=tuple(item["name_ko"] for item in payload["items"]),
        islands=tuple(location["name_ko"] for location in payload["islands"]),
    )

