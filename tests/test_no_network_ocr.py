from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ocr_pipeline_has_no_network_client_dependency() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src" / "bdo_barter_assistant").rglob("*.py")
    )

    forbidden_imports = ("import requests", "import httpx", "import urllib.request")
    assert not any(name in source for name in forbidden_imports)

