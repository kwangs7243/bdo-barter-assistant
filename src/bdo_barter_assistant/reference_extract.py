from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


_MASTER_BLOCK = re.compile(
    r"const\s+masterData\s*=\s*\{(?P<body>.*?)\n\};\s*\n\s*const\s+rawData",
    re.DOTALL,
)
_TIER_BLOCK = re.compile(r"(?m)^\s*(?P<tier>[1-7]):\s*\[(?P<body>.*?)\]\s*,?\s*$", re.DOTALL)
_ITEM_NAME = re.compile(r"\bname:\s*\"(?P<name>[^\"]+)\"")
_RAW_BLOCK = re.compile(
    r"const\s+rawData\s*=\s*\{(?P<body>.*?)\n\};\s*\n\s*//.*?\nconst\s+islandCoordinates",
    re.DOTALL,
)
_LOCATION = re.compile(r'"(?P<name>[^"]+)"\s*:\s*\{[^{}]*?"x"\s*:')


def extract_reference_dictionary(html_path: Path) -> dict[str, Any]:
    """Extract only OCR candidate names from the v14.1 reference HTML."""
    raw_bytes = html_path.read_bytes()
    html = raw_bytes.decode("utf-8")
    master_match = _MASTER_BLOCK.search(html)
    raw_match = _RAW_BLOCK.search(html)
    if not master_match or not raw_match:
        raise ValueError("masterData or rawData block was not found")

    items: list[dict[str, Any]] = []
    for tier_match in _TIER_BLOCK.finditer(master_match.group("body")):
        tier = int(tier_match.group("tier"))
        items.extend(
            {"name_ko": name_match.group("name"), "tier": tier}
            for name_match in _ITEM_NAME.finditer(tier_match.group("body"))
        )
    islands = [
        {"name_ko": match.group("name")}
        for match in _LOCATION.finditer(raw_match.group("body"))
    ]
    if len(items) != 118 or len(islands) != 100:
        raise ValueError(
            f"unexpected reference counts: items={len(items)}, islands={len(islands)}"
        )
    try:
        source_path = html_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        source_path = html_path.resolve().as_posix()
    return {
        "schema_version": 1,
        "source": {
            "path": source_path,
            "sha256": hashlib.sha256(raw_bytes).hexdigest().upper(),
            "fields": ["masterData.name", "rawData key"],
        },
        "items": items,
        "islands": islands,
    }


def write_reference_dictionary(html_path: Path, output_path: Path) -> None:
    payload = extract_reference_dictionary(html_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
