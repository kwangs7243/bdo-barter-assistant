from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


DEFAULT_DICTIONARY_PATH = Path(__file__).resolve().parents[2] / "data" / "ocr_dictionary.json"


@dataclass(frozen=True)
class ItemReference:
    name: str
    tier: int


@dataclass(frozen=True)
class SpecialItemReference:
    name: str
    category: Literal["mat", "coin"]
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class LocationReference:
    canonical_name: str
    aliases: tuple[str, ...]
    x: int
    y: int
    is_ocean: bool


@dataclass(frozen=True)
class TradeRule:
    required: int
    yielded: int


@dataclass(frozen=True)
class OcrDictionary:
    item_entries: tuple[ItemReference, ...]
    special_items: tuple[SpecialItemReference, ...]
    locations: tuple[LocationReference, ...]
    trade_rules: dict[int, TradeRule]

    @property
    def items(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.item_entries)

    @property
    def islands(self) -> tuple[str, ...]:
        return tuple(location.canonical_name for location in self.locations)

    def item_kind(self, name: str | None) -> int | Literal["mat", "coin"] | None:
        if not name:
            return None
        for item in self.item_entries:
            if item.name == name:
                return item.tier
        for item in self.special_items:
            if item.name == name:
                return item.category
        return None


def load_ocr_dictionary(path: Path = DEFAULT_DICTIONARY_PATH) -> OcrDictionary:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return OcrDictionary(
        item_entries=tuple(
            ItemReference(name=item["name_ko"], tier=int(item["tier"]))
            for item in payload["items"]
        ),
        special_items=tuple(
            SpecialItemReference(
                name=item["name_ko"],
                category=item["category"],
                patterns=tuple(item["patterns"]),
            )
            for item in payload.get("special_items", [])
        ),
        locations=tuple(
            LocationReference(
                canonical_name=location["canonical_name"],
                aliases=tuple(location["aliases"]),
                x=int(location["x"]),
                y=int(location["y"]),
                is_ocean=bool(location["is_ocean"]),
            )
            for location in payload.get("locations", [])
        ),
        trade_rules={
            int(tier): TradeRule(
                required=int(rule["req"]), yielded=int(rule["get"])
            )
            for tier, rule in payload.get("trade_rules", {}).items()
        },
    )
