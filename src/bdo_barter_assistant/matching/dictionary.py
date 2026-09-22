from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Literal

from rapidfuzz import fuzz

from bdo_barter_assistant.reference_data import OcrDictionary


_STAGE_PREFIX = re.compile(r"[\[\(]?\s*(?P<tier>[1-7])\s*단계\s*[\]\)]?")
_MATCH_CHARS = re.compile(r"[^0-9A-Za-z가-힣]")


def clean_ocr_text(text: str) -> str:
    """Remove UI stage labels while preserving the OCR observation itself elsewhere."""
    return _STAGE_PREFIX.sub("", text).strip(" []()|:·")


def compact(text: str) -> str:
    return _MATCH_CHARS.sub("", clean_ocr_text(text)).casefold()


@dataclass(frozen=True)
class MatchAlternative:
    value: str
    source_value: str
    confidence: float


@dataclass(frozen=True)
class DictionaryMatch:
    raw: str
    value: str | None
    confidence: float
    margin: float
    auto_confirmed: bool
    alternatives: tuple[MatchAlternative, ...]


@dataclass(frozen=True)
class ParsedItemText:
    raw: str
    cleaned: str
    observed_tier: int | None


def parse_item_text(text: str) -> ParsedItemText:
    """Separate an observed stage label from the item text before matching."""
    match = _STAGE_PREFIX.search(text)
    return ParsedItemText(
        raw=text,
        cleaned=clean_ocr_text(text),
        observed_tier=int(match.group("tier")) if match else None,
    )


def _candidate_forms(
    candidates: Iterable[str], kind: Literal["item", "island"]
) -> list[tuple[str, str]]:
    forms: list[tuple[str, str]] = []
    for candidate in dict.fromkeys(candidates):
        forms.append((candidate, candidate))
        if kind == "island" and not candidate.endswith(("섬", "제도", "항구", "해안")):
            forms.append((f"{candidate} 섬", candidate))
    return forms


def match_dictionary(
    raw: str,
    candidates: Iterable[str],
    *,
    kind: Literal["item", "island"],
    minimum_confidence: float = 0.78,
    minimum_margin: float = 0.05,
) -> DictionaryMatch:
    """Return a conservative fuzzy match, retaining alternatives and score margin."""
    query = compact(raw)
    if kind == "island":
        query = re.sub(r"\d+$", "", query)
        if query.endswith("성"):
            query = query[:-1] + "섬"
    if not query:
        return DictionaryMatch(raw, None, 0.0, 0.0, False, ())

    scored: list[MatchAlternative] = []
    for display, source in _candidate_forms(candidates, kind):
        # Jamo decomposition distinguishes visually related Hangul OCR errors.
        # For example, 간/칸 differ less than 간/틴 even though each is one
        # Unicode syllable substitution under a plain edit distance.
        candidate = unicodedata.normalize("NFD", compact(display))
        score = fuzz.ratio(unicodedata.normalize("NFD", query), candidate) / 100.0
        scored.append(MatchAlternative(display, source, score))
    scored.sort(key=lambda item: (-item.confidence, item.value))

    unique: list[MatchAlternative] = []
    seen_values: set[str] = set()
    for entry in scored:
        if entry.value not in seen_values:
            unique.append(entry)
            seen_values.add(entry.value)
        if len(unique) == 3:
            break

    best = unique[0]
    runner_up = unique[1].confidence if len(unique) > 1 else 0.0
    margin = best.confidence - runner_up
    confirmed = best.confidence >= minimum_confidence and margin >= minimum_margin
    return DictionaryMatch(
        raw=raw,
        value=best.value if confirmed else None,
        confidence=best.confidence,
        margin=margin,
        auto_confirmed=confirmed,
        alternatives=tuple(unique),
    )


def _match_grouped_candidates(
    raw: str,
    groups: Iterable[tuple[str, Iterable[str]]],
    *,
    kind: Literal["item", "island"],
    minimum_confidence: float = 0.78,
    minimum_margin: float = 0.05,
) -> DictionaryMatch:
    """Score aliases inside one semantic group, then compare distinct groups."""
    query = compact(raw)
    if kind == "island":
        query = re.sub(r"\d+$", "", query)
        if query.endswith("성"):
            query = query[:-1] + "섬"
    if not query:
        return DictionaryMatch(raw, None, 0.0, 0.0, False, ())

    scored: list[MatchAlternative] = []
    for canonical, aliases in groups:
        forms = _candidate_forms(aliases, kind)
        alias_scores = [
            (
                fuzz.ratio(
                    unicodedata.normalize("NFD", query),
                    unicodedata.normalize("NFD", compact(display)),
                )
                / 100.0,
                display,
            )
            for display, _source in forms
        ]
        score, display = max(alias_scores, default=(0.0, canonical))
        scored.append(MatchAlternative(canonical, display, score))
    scored.sort(key=lambda item: (-item.confidence, item.value))
    alternatives = tuple(scored[:3])
    best = alternatives[0]
    runner_up = alternatives[1].confidence if len(alternatives) > 1 else 0.0
    margin = best.confidence - runner_up
    confirmed = best.confidence >= minimum_confidence and margin >= minimum_margin
    return DictionaryMatch(
        raw=raw,
        value=best.value if confirmed else None,
        confidence=best.confidence,
        margin=margin,
        auto_confirmed=confirmed,
        alternatives=alternatives,
    )


def match_location(raw: str, dictionary: OcrDictionary) -> DictionaryMatch:
    """Match locations while preventing aliases of one coordinate from competing."""
    return _match_grouped_candidates(
        raw,
        (
            (location.canonical_name, location.aliases)
            for location in dictionary.locations
        ),
        kind="island",
    )


def match_item(
    raw: str,
    dictionary: OcrDictionary,
    *,
    allowed_kinds: set[int | Literal["mat", "coin"]] | None = None,
) -> DictionaryMatch:
    """Match an item after applying only reference-supported tier narrowing."""
    parsed = parse_item_text(raw)
    effective_kinds = allowed_kinds
    if parsed.observed_tier is not None:
        effective_kinds = {parsed.observed_tier}

    groups: list[tuple[str, tuple[str, ...]]] = []
    for item in dictionary.item_entries:
        if effective_kinds is None or item.tier in effective_kinds:
            groups.append((item.name, (item.name,)))
    for item in dictionary.special_items:
        if effective_kinds is None or item.category in effective_kinds:
            groups.append((item.name, (item.name, *item.patterns)))
    return _match_grouped_candidates(raw, groups, kind="item")
