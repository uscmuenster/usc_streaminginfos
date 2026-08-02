from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from usc_kommentatoren.lineups import download_pdf


def _response(content: bytes, content_type: str) -> Mock:
    response = Mock()
    response.content = content
    response.headers = {"Content-Type": content_type}
    response.raise_for_status.return_value = None
    return response


def test_download_pdf_rejects_html_success_response(tmp_path: Path) -> None:
    destination = tmp_path / "scoresheet.pdf"
    response = _response(b"<!doctype html><title>Not found</title>", "text/html")

    with patch("usc_kommentatoren.lineups.requests.get", return_value=response):
        with pytest.raises(requests.RequestException, match="kein PDF"):
            download_pdf("https://example.test/missing.pdf", destination)

    assert not destination.exists()


def test_download_pdf_writes_valid_pdf_response(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "scoresheet.pdf"
    content = b"%PDF-1.7\nexample"
    response = _response(content, "application/pdf")

    with patch("usc_kommentatoren.lineups.requests.get", return_value=response):
        result = download_pdf("https://example.test/scoresheet.pdf", destination)

    assert result == destination
    assert destination.read_bytes() == content
