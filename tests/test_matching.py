from bdo_barter_assistant.matching.dictionary import match_dictionary


def test_hangul_jamo_matching_resolves_common_island_ocr_errors() -> None:
    candidates = ("일리야", "칸베라 섬", "틴베라 섬")

    iliya = match_dictionary("일리야성 \\7", candidates, kind="island")
    kanvera = match_dictionary("간베라성 \\7", candidates, kind="island")

    assert iliya.value == "일리야 섬"
    assert iliya.auto_confirmed
    assert kanvera.value == "칸베라 섬"
    assert kanvera.auto_confirmed
    assert kanvera.margin >= 0.05


def test_unknown_text_is_not_auto_confirmed() -> None:
    result = match_dictionary("판독불가", ("오색 구슬", "해적선 돛대"), kind="item")

    assert result.value is None
    assert not result.auto_confirmed

