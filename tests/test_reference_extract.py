from pathlib import Path

from bdo_barter_assistant.reference_extract import extract_reference_dictionary


ROOT = Path(__file__).resolve().parents[1]
HTML = next((ROOT / "reference" / "original").glob("*.html"))


def test_reference_dictionary_is_extracted_from_html() -> None:
    payload = extract_reference_dictionary(HTML)

    assert len(payload["items"]) == 118
    assert len(payload["islands"]) == 100
    assert payload["source"]["sha256"] == (
        "155EE19C515A72627EFFB4884F540BBD7FCEA487967C47FE6CCB3A608BCEAE9F"
    )
    item_names = {item["name_ko"] for item in payload["items"]}
    island_names = {island["name_ko"] for island in payload["islands"]}
    assert "황금빛 선인장 꽃다발" in item_names
    assert "반달 조리용 칼" in item_names
    assert "칸베라 섬" in island_names
    assert "일리야" in island_names
    assert payload["schema_version"] == 2
    assert payload["trade_rules"] == {
        "2": {"req": 1, "get": 3},
        "3": {"req": 1, "get": 3},
        "4": {"req": 1, "get": 2},
        "5": {"req": 1, "get": 1},
        "6": {"req": 1, "get": 1},
        "7": {"req": 1, "get": 1},
    }
    assert len(payload["locations"]) == 95
    assert next(
        location for location in payload["locations"] if "해모" in location["aliases"]
    )["canonical_name"] == "해모 섬"
    assert {item["category"] for item in payload["special_items"]} == {"mat", "coin"}
