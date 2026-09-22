from bdo_barter_assistant.barter.trade_contract import normalize_trade_observation
from bdo_barter_assistant.matching.dictionary import match_item, match_location, parse_item_text
from bdo_barter_assistant.reference_data import load_ocr_dictionary


def _row(*, from_raw: str, to_raw: str, count: int | None = 10, req: int | None = None, yield_: int | None = None) -> dict[str, object]:
    return {
        "island": {"value": None},
        "from_item": {"value": None},
        "to_item": {"value": None},
        "remaining_count": count,
        "req_amount": req,
        "yield_amount": yield_,
        "raw": {
            "island": "해모 섬",
            "from_item": from_raw,
            "to_item": to_raw,
            "remaining_count": f"남은 교환 횟수: {count}회" if count is not None else "남은 교환 횟수:",
        },
    }


def test_item_stage_is_parsed_and_narrows_to_reference_tier() -> None:
    dictionary = load_ocr_dictionary()
    parsed = parse_item_text("[2단계] 오색 구슬")
    matched = match_item(parsed.raw, dictionary)

    assert parsed.observed_tier == 2
    assert matched.value == "오색 구슬"
    assert matched.auto_confirmed


def test_location_aliases_compete_by_canonical_location() -> None:
    dictionary = load_ocr_dictionary()
    matched = match_location("해모 섬", dictionary)

    assert matched.value == "해모 섬"
    assert [alternative.value for alternative in matched.alternatives].count("해모 섬") == 1


def test_general_trade_derives_amounts_from_reference_rules() -> None:
    dictionary = load_ocr_dictionary()
    result = normalize_trade_observation(
        _row(from_raw="[2단계] 오색 구슬", to_raw="[3단계] 걸쭉한 괴생물 혈액"),
        dictionary,
    )

    assert result["scheduler_ready"] is True
    assert result["scanned_trade"] == {
        "island": "해모 섬",
        "fromItem": "오색 구슬",
        "reqAmount": 1,
        "toItem": "걸쭉한 괴생물 혈액",
        "count": 10,
        "yield": 3,
    }
    assert result["scheduler_contract"]["provenance"]["yield"]["source"] == "reference_rule"


def test_base_trade_requires_observed_request_amount() -> None:
    dictionary = load_ocr_dictionary()
    missing = normalize_trade_observation(
        _row(from_raw="현지 광물", to_raw="[1단계] 갈퀴 꽃 씨앗 주머니"), dictionary
    )
    present = normalize_trade_observation(
        _row(from_raw="현지 광물", to_raw="[1단계] 갈퀴 꽃 씨앗 주머니", req=30), dictionary
    )

    assert missing["scheduler_ready"] is False
    assert "missing_reqAmount" in missing["scheduler_contract"]["review_reasons"]
    assert present["scheduler_ready"] is True
    assert present["scanned_trade"]["yield"] == 1


def test_coin_trade_requires_observed_yield_and_accepts_zero_count() -> None:
    dictionary = load_ocr_dictionary()
    missing = normalize_trade_observation(
        _row(from_raw="[4단계] 해상 기사단의 투구", to_raw="까마귀 주화", count=0),
        dictionary,
    )
    present = normalize_trade_observation(
        _row(from_raw="[4단계] 해상 기사단의 투구", to_raw="까마귀 주화", count=0, yield_=100),
        dictionary,
    )

    assert missing["scheduler_ready"] is False
    assert missing["scanned_trade"]["count"] == 0
    assert present["scheduler_ready"] is True
    assert present["scanned_trade"]["yield"] == 100
