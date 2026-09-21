from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Literal

from rapidfuzz import fuzz


_STAGE_PREFIX = re.compile(r"[\[\(]?\s*\d+\s*단계\s*[\]\)]?")
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
