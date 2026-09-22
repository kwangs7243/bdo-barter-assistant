from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Literal

from bdo_barter_assistant.matching.dictionary import (
    DictionaryMatch,
    clean_ocr_text,
    compact,
    match_item,
    match_location,
    parse_item_text,
)
from bdo_barter_assistant.reference_data import OcrDictionary, load_ocr_dictionary


ItemKind = int | Literal["mat", "coin"]
_HANGUL = re.compile(r"[가-힣]")
_QUANTITY_SUFFIX = re.compile(r"\s*[xX×]\s*\d+\s*$")


def _match_payload(match: DictionaryMatch) -> dict[str, Any]:
    return {
        "raw": match.raw,
        "value": match.value,
        "reference_id": None,
        "match_confidence": round(match.confidence, 4),
        "match_margin": round(match.margin, 4),
        "auto_confirmed": match.auto_confirmed,
    }


def _alternatives(match: DictionaryMatch) -> list[dict[str, Any]]:
    return [
        {
            "value": alternative.value,
            "source_value": alternative.source_value,
            "confidence": round(alternative.confidence, 4),
        }
        for alternative in match.alternatives
    ]


def _raw_text(row: dict[str, Any], field: str) -> str:
    value = row.get("raw", {}).get(field, "")
    return value if isinstance(value, str) else ""


def _expected_from_kinds(to_kind: ItemKind | None) -> set[ItemKind] | None:
    if isinstance(to_kind, int) and 2 <= to_kind <= 7:
        return {to_kind - 1}
    if to_kind in {"mat", "coin"}:
        return {4, 5}
    return None


def _base_item_payload(raw: str, to_match: DictionaryMatch) -> dict[str, Any] | None:
    cleaned = _QUANTITY_SUFFIX.sub("", clean_ocr_text(raw)).strip()
    compacted = compact(cleaned)
    if (
        not cleaned
        or parse_item_text(raw).observed_tier is not None
        or len(_HANGUL.findall(cleaned)) < 2
        or len(compacted) < 2
    ):
        return None
    return {
        "raw": raw,
        "value": cleaned,
        "reference_id": None,
        "match_confidence": round(min(to_match.confidence, 0.85), 4),
        "match_margin": 0.0,
        "auto_confirmed": True,
        "semantic_kind": 0,
        "normalization_source": "base_context",
    }


def normalize_trade_observation(
    row: dict[str, Any], dictionary: OcrDictionary | None = None
) -> dict[str, Any]:
    """Re-match one OCR observation and complete the scheduler compatibility contract."""
    dictionary = dictionary or load_ocr_dictionary()
    normalized = deepcopy(row)
    island_raw = _raw_text(normalized, "island")
    from_raw = _raw_text(normalized, "from_item")
    to_raw = _raw_text(normalized, "to_item")

    island_match = match_location(island_raw, dictionary)
    to_match = match_item(to_raw, dictionary)
    to_kind = dictionary.item_kind(to_match.value)

    if to_kind == 1:
        unrestricted_from = match_item(from_raw, dictionary)
        if not unrestricted_from.auto_confirmed and unrestricted_from.confidence < 0.70:
            from_payload = _base_item_payload(from_raw, to_match)
            from_match = unrestricted_from
        else:
            from_payload = None
            from_match = unrestricted_from
    else:
        from_match = match_item(
            from_raw,
            dictionary,
            allowed_kinds=_expected_from_kinds(to_kind),
        )
        from_payload = None

    normalized["island"] = _match_payload(island_match)
    normalized["to_item"] = _match_payload(to_match)
    normalized["from_item"] = from_payload or _match_payload(from_match)
    normalized.setdefault("alternatives", {})
    normalized["alternatives"].update(
        {
            "island": _alternatives(island_match),
            "from_item": _alternatives(from_match),
            "to_item": _alternatives(to_match),
        }
    )
    normalized["confidence"] = {
        "island": round(island_match.confidence, 4),
        "from_item": float(normalized["from_item"].get("match_confidence", 0.0)),
        "to_item": round(to_match.confidence, 4),
    }
    normalized["field_auto_confirmed"] = {
        "island": island_match.auto_confirmed,
        "remaining_count": normalized.get("remaining_count") is not None,
        "from_item": bool(normalized["from_item"].get("auto_confirmed")),
        "req_amount": normalized.get("req_amount") is not None,
        "to_item": to_match.auto_confirmed,
        "yield_amount": normalized.get("yield_amount") is not None,
    }
    return complete_trade_contract(normalized, dictionary)


def _provenance(value: Any, source: str | None) -> dict[str, Any]:
    return {"value": value, "source": source}


def complete_trade_contract(
    row: dict[str, Any], dictionary: OcrDictionary | None = None
) -> dict[str, Any]:
    """Complete scannedTrades values without treating derived values as OCR."""
    dictionary = dictionary or load_ocr_dictionary()
    completed = deepcopy(row)
    island = completed.get("island", {}).get("value")
    from_item = completed.get("from_item", {}).get("value")
    to_item = completed.get("to_item", {}).get("value")
    count = completed.get("remaining_count")
    from_kind = completed.get("from_item", {}).get("semantic_kind")
    if from_kind is None:
        from_kind = dictionary.item_kind(from_item)
    to_kind = dictionary.item_kind(to_item)

    req_amount: int | None = None
    req_source: str | None = None
    yield_amount: int | None = None
    yield_source: str | None = None
    exception = "none"

    if from_kind == 0 and to_kind == 1:
        exception = "base_req_amount"
        req_amount = completed.get("req_amount")
        req_source = "ocr" if req_amount is not None else None
        yield_amount = 1
        yield_source = "reference_rule"
    elif to_kind == "coin":
        exception = "coin_yield"
        req_amount = 1
        req_source = "reference_rule"
        yield_amount = completed.get("yield_amount")
        yield_source = "ocr" if yield_amount is not None else None
    elif to_kind == "mat":
        rule = dictionary.trade_rules.get(5)
        if rule:
            req_amount = rule.required
            yield_amount = rule.yielded
            req_source = yield_source = "reference_rule"
    elif isinstance(to_kind, int):
        rule = dictionary.trade_rules.get(to_kind)
        if rule:
            req_amount = rule.required
            yield_amount = rule.yielded
            req_source = yield_source = "reference_rule"

    reasons: list[str] = []
    for field, value in (
        ("island", island),
        ("fromItem", from_item),
        ("toItem", to_item),
        ("count", count),
        ("reqAmount", req_amount),
        ("yield", yield_amount),
    ):
        if value is None or (isinstance(value, str) and not value.strip()):
            reasons.append(f"missing_{field}")

    expected_from = _expected_from_kinds(to_kind)
    if to_kind == 1 and from_kind != 0:
        reasons.append("incompatible_item_tiers")
    elif expected_from is not None and from_kind not in expected_from:
        reasons.append("incompatible_item_tiers")
    elif to_kind is None:
        reasons.append("unknown_to_item_semantics")

    scheduler_ready = not reasons
    provenance = {
        "island": _provenance(island, "ocr" if island is not None else None),
        "fromItem": _provenance(from_item, "ocr" if from_item is not None else None),
        "reqAmount": _provenance(req_amount, req_source),
        "toItem": _provenance(to_item, "ocr" if to_item is not None else None),
        "count": _provenance(count, "ocr" if count is not None else None),
        "yield": _provenance(yield_amount, yield_source),
    }
    completed["scanned_trade"] = {
        "island": island,
        "fromItem": from_item,
        "reqAmount": req_amount,
        "toItem": to_item,
        "count": count,
        "yield": yield_amount,
    }
    completed["scheduler_contract"] = {
        "scheduler_ready": scheduler_ready,
        "review_reasons": reasons,
        "from_tier": from_kind,
        "to_tier": to_kind,
        "exception": exception,
        "provenance": provenance,
    }
    completed["scheduler_ready"] = scheduler_ready
    completed["review_required"] = not scheduler_ready
    completed["review_status"] = (
        "auto_confirmed" if scheduler_ready else "review_required"
    )
    return completed


def _failure_classification(
    row: dict[str, Any], dictionary: OcrDictionary
) -> str:
    """Classify unresolved evidence without turning the label into a guess."""
    contract = row.get("scheduler_contract", {})
    if contract.get("scheduler_ready"):
        return "none"
    required_fields = {
        "island": "island",
        "fromItem": "from_item",
        "toItem": "to_item",
        "count": "remaining_count",
    }
    for logical, raw_field in required_fields.items():
        if f"missing_{logical}" in contract.get("review_reasons", []):
            raw = _raw_text(row, raw_field).strip()
            if not raw:
                return "raw_empty"
            payload = row.get(raw_field, {})
            confidence = float(payload.get("match_confidence", 0.0)) if isinstance(payload, dict) else 0.0
            margin = float(payload.get("match_margin", 0.0)) if isinstance(payload, dict) else 0.0
            if confidence >= 0.70 and margin < 0.05:
                return "top1_correct_looking_but_threshold_blocked"
            if logical == "island" and any(
                alternative["value"] == alternative["source_value"]
                for alternative in row.get("alternatives", {}).get("island", [])
            ) and margin < 0.05:
                return "alias_margin_issue"
            hangul_count = len(_HANGUL.findall(raw))
            if hangul_count >= 3 and confidence < 0.60:
                return "dictionary_reference_missing"
            return "actual_ocr_corruption"
    for logical, raw_field in (("reqAmount", "req_amount"), ("yield", "yield_amount")):
        if f"missing_{logical}" in contract.get("review_reasons", []):
            return "actual_ocr_corruption"
    return "contract_context_conflict"


def evaluate_contract_payload(
    payload: dict[str, Any], dictionary: OcrDictionary | None = None
) -> dict[str, Any]:
    """Re-evaluate a stored scan from its raw OCR observations."""
    dictionary = dictionary or load_ocr_dictionary()
    evaluated = deepcopy(payload)
    rows = [normalize_trade_observation(row, dictionary) for row in payload.get("rows", [])]
    for row in rows:
        row["failure_classification"] = _failure_classification(row, dictionary)
    evaluated["rows"] = rows

    exceptions = {
        "base_req_amount": [
            row for row in rows if row["scheduler_contract"]["exception"] == "base_req_amount"
        ],
        "coin_yield": [
            row for row in rows if row["scheduler_contract"]["exception"] == "coin_yield"
        ],
    }
    metrics = {
        "total_rows": len(rows),
        "coverage_complete": bool(payload.get("coverage", {}).get("coverage_complete")),
        "scheduler_ready": sum(bool(row["scheduler_ready"]) for row in rows),
        "review_required": sum(bool(row["review_required"]) for row in rows),
        "island_resolved": sum(row["scanned_trade"]["island"] is not None for row in rows),
        "fromItem_resolved": sum(row["scanned_trade"]["fromItem"] is not None for row in rows),
        "toItem_resolved": sum(row["scanned_trade"]["toItem"] is not None for row in rows),
        "count_resolved": sum(row["scanned_trade"]["count"] is not None for row in rows),
        "reqAmount_reference_derived": sum(
            row["scheduler_contract"]["provenance"]["reqAmount"]["source"]
            == "reference_rule"
            for row in rows
        ),
        "yield_reference_derived": sum(
            row["scheduler_contract"]["provenance"]["yield"]["source"]
            == "reference_rule"
            for row in rows
        ),
        "base_reqAmount_required": len(exceptions["base_req_amount"]),
        "base_reqAmount_success": sum(
            row["scanned_trade"]["reqAmount"] is not None
            for row in exceptions["base_req_amount"]
        ),
        "coin_yield_required": len(exceptions["coin_yield"]),
        "coin_yield_success": sum(
            row["scanned_trade"]["yield"] is not None
            for row in exceptions["coin_yield"]
        ),
        "failure_classification": {
            label: sum(row["failure_classification"] == label for row in rows)
            for label in (
                "raw_empty",
                "top1_correct_looking_but_threshold_blocked",
                "alias_margin_issue",
                "dictionary_reference_missing",
                "actual_ocr_corruption",
                "contract_context_conflict",
                "none",
            )
        },
        # A live scan has no row-level human truth label, so this cannot be
        # honestly measured from the stored OCR result alone.
        "wrong_auto_confirmed_count": None,
    }
    evaluated["contract_metrics"] = metrics
    if "session" in evaluated:
        evaluated["session"]["review_required_rows"] = metrics["review_required"]
        evaluated["session"]["scheduler_ready_rows"] = metrics["scheduler_ready"]
    if "coverage" in evaluated:
        evaluated["coverage"]["unreviewed_count"] = metrics["review_required"]
    return evaluated
