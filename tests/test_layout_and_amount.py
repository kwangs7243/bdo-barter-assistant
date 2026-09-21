from pathlib import Path

from PIL import Image

from bdo_barter_assistant.ocr.amount import read_amount
from bdo_barter_assistant.ocr.layout import segment_complete_rows


ROOT = Path(__file__).resolve().parents[1]
CROPPED = ROOT / "reference" / "samples" / "barter_cropped.png"


def test_six_complete_rows_are_segmented() -> None:
    with Image.open(CROPPED) as image:
        rows = segment_complete_rows(image.convert("RGB"))

    assert len(rows) == 6
    assert [(row.top, row.bottom) for row in rows] == [
        (3, 73),
        (78, 148),
        (153, 223),
        (228, 298),
        (303, 373),
        (378, 448),
    ]


def test_small_icon_amounts_are_read_from_pixels() -> None:
    with Image.open(CROPPED) as image:
        rows = segment_complete_rows(image.convert("RGB"))

    assert [read_amount(row, "req_amount").value for row in rows] == [1] * 6
    assert [read_amount(row, "yield_amount").value for row in rows] == [
        1,
        2,
        1,
        2,
        2,
        3,
    ]

