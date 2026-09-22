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
_LOCATION = re.compile(
    r'"(?P<name>[^"]+)"\s*:\s*\{\s*"x"\s*:\s*(?P<x>-?\d+)\s*,'
    r'\s*"y"\s*:\s*(?P<y>-?\d+)(?P<extra>[^{}]*)\}'
)
_GET_ITEM_TIER = re.compile(
    r"function\s+getItemTier\s*\([^)]*\)\s*\{(?P<body>.*?)\n\}", re.DOTALL
)
_INCLUDES_PATTERN = re.compile(r'cleanName\.includes\("(?P<pattern>[^"]+)"\)')
_ALL_ITEMS_PUSH = re.compile(r"allItems\.push\((?P<body>.*?)\);", re.DOTALL)
_QUOTED_VALUE = re.compile(r'"(?P<value>[^"]+)"')
_TRADE_RULES = re.compile(r"TRADE_RULES\s*:\s*\{(?P<body>.*?)\}\s*,\s*\n")
_TRADE_RULE = re.compile(
    r"T(?P<tier>[2-7])\s*:\s*\{\s*req\s*:\s*(?P<req>\d+)\s*,"
    r"\s*get\s*:\s*(?P<get>\d+)\s*\}"
)


def extract_reference_dictionary(html_path: Path) -> dict[str, Any]:
    """Extract the local parser's semantic reference from the v14.1 HTML."""
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
    raw_locations = [
        {
            "name_ko": match.group("name"),
            "x": int(match.group("x")),
            "y": int(match.group("y")),
            "is_ocean": "isOcean" in match.group("extra"),
        }
        for match in _LOCATION.finditer(raw_match.group("body"))
    ]
    islands = [{"name_ko": location["name_ko"]} for location in raw_locations]
    if len(items) != 118 or len(islands) != 100:
        raise ValueError(
            f"unexpected reference counts: items={len(items)}, islands={len(islands)}"
        )
    try:
        source_path = html_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        source_path = html_path.resolve().as_posix()
    grouped_locations: dict[tuple[int, int, bool], list[dict[str, Any]]] = {}
    for location in raw_locations:
        key = (location["x"], location["y"], location["is_ocean"])
        grouped_locations.setdefault(key, []).append(location)
    locations = []
    for aliases in grouped_locations.values():
        source_name = aliases[0]["name_ko"]
        canonical_name = source_name
        for suffix in (" 섬", " 제도"):
            display_name = source_name + suffix
            if f'"{display_name}"' in html:
                canonical_name = display_name
                break
        alias_names = list(dict.fromkeys(
            [alias["name_ko"] for alias in aliases] + [canonical_name]
        ))
        locations.append({
            "canonical_name": canonical_name,
            "aliases": alias_names,
            "x": aliases[0]["x"],
            "y": aliases[0]["y"],
            "is_ocean": aliases[0]["is_ocean"],
        })

    tier_function = _GET_ITEM_TIER.search(html)
    if not tier_function:
        raise ValueError("getItemTier function was not found")
    semantic_patterns = []
    for pattern in _INCLUDES_PATTERN.finditer(tier_function.group("body")):
        value = pattern.group("pattern")
        semantic_patterns.append(
            {"pattern": value, "category": "coin" if value == "까마귀 주화" else "mat"}
        )

    special_names: list[str] = []
    for push_match in _ALL_ITEMS_PUSH.finditer(html):
        special_names.extend(
            match.group("value")
            for match in _QUOTED_VALUE.finditer(push_match.group("body"))
        )
    extracted_special_names = list(dict.fromkeys(special_names))
    special_names.extend(
        entry["pattern"]
        for entry in semantic_patterns
        if not any(entry["pattern"] in name for name in extracted_special_names)
    )
    special_items = []
    for name in dict.fromkeys(special_names):
        matched = [
            entry for entry in semantic_patterns if entry["pattern"] in name
        ]
        if not matched:
            continue
        special_items.append(
            {
                "name_ko": name,
                "category": matched[0]["category"],
                "patterns": [entry["pattern"] for entry in matched],
            }
        )

    rules_match = _TRADE_RULES.search(html)
    if not rules_match:
        raise ValueError("APP_CONFIG.TRADE_RULES was not found")
    trade_rules = {
        match.group("tier"): {
            "req": int(match.group("req")),
            "get": int(match.group("get")),
        }
        for match in _TRADE_RULE.finditer(rules_match.group("body"))
    }
    if set(trade_rules) != {"2", "3", "4", "5", "6", "7"}:
        raise ValueError(f"unexpected trade rules: {trade_rules}")

    return {
        "schema_version": 2,
        "source": {
            "path": source_path,
            "sha256": hashlib.sha256(raw_bytes).hexdigest().upper(),
            "fields": [
                "masterData.name/tier",
                "rawData key/coordinates/isOcean",
                "getItemTier includes patterns",
                "APP_CONFIG.TRADE_RULES",
            ],
        },
        "items": items,
        "islands": islands,
        "locations": locations,
        "special_items": special_items,
        "item_semantic_patterns": semantic_patterns,
        "trade_rules": trade_rules,
    }


def write_reference_dictionary(html_path: Path, output_path: Path) -> None:
    payload = extract_reference_dictionary(html_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
