"""Tests for the bundled http-fetch skill script."""

from __future__ import annotations

import importlib.util
import io
import sys
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "src" / "agentos" / "skills" / "bundled" / "http-fetch" / "scripts" / "http_fetch.py"
)


def _load_http_fetch():
    spec = importlib.util.spec_from_file_location("http_fetch", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["http_fetch"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def http_fetch():
    return _load_http_fetch()


class FakeResponse:
    def __init__(self, status: int, body: bytes, reason: str = "OK") -> None:
        self.status = status
        self._body = body
        self.reason = reason

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


def test_http_fetch_get_success(http_fetch, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    fake_resp = FakeResponse(200, b"hello world")
    with patch("urllib.request.urlopen", return_value=fake_resp):
        rc = http_fetch.main(["--url", "https://example.com/api"])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out == "hello world"
    assert captured.err == ""


def test_http_fetch_headers_and_post_body(
    http_fetch, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    fake_resp = FakeResponse(201, b'{"status": "created"}', reason="Created")

    captured_req = None

    def fake_urlopen(req, timeout=30.0):
        nonlocal captured_req
        captured_req = req
        return fake_resp

    fake_stdin = io.TextIOWrapper(io.BytesIO(b'{"key": "value"}'), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        rc = http_fetch.main(
            [
                "--url",
                "https://api.example.com/items",
                "--method",
                "POST",
                "--header",
                "Authorization: Bearer test-secret",
                "-H",
                "Content-Type: application/json",
            ]
        )

    assert rc == 0
    assert captured_req is not None
    assert captured_req.get_method() == "POST"
    assert captured_req.data == b'{"key": "value"}'
    assert captured_req.headers["Authorization"] == "Bearer test-secret"
    assert captured_req.headers["Content-type"] == "application/json"
    captured = capsys.readouterr()
    assert '{"status": "created"}' in captured.out


def test_http_fetch_invalid_header_format(http_fetch, capsys) -> None:
    rc = http_fetch.main(["--url", "https://example.com", "--header", "invalid_no_colon"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "invalid header format" in captured.err


def test_http_fetch_non_2xx_response(http_fetch, capsys) -> None:
    error_resp = urllib.error.HTTPError(
        url="https://example.com/notfound",
        code=404,
        msg="Not Found",
        hdrs=MagicMock(),
        fp=io.BytesIO(b"Page Not Found"),
    )
    with patch("urllib.request.urlopen", side_effect=error_resp):
        rc = http_fetch.main(["--url", "https://example.com/notfound"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "Page Not Found" in captured.out
    assert "HTTP 404: Not Found: Page Not Found" in captured.err


def test_http_fetch_truncation(http_fetch, capsys) -> None:
    large_payload = b"A" * 100
    fake_resp = FakeResponse(200, large_payload)
    with patch("urllib.request.urlopen", return_value=fake_resp):
        rc = http_fetch.main(["--url", "https://example.com", "--max-bytes", "10"])
    assert rc == 0
    captured = capsys.readouterr()
    assert len(captured.out.encode("utf-8")) <= 12
    assert captured.out.endswith("…")


def test_http_fetch_invalid_url_and_method(http_fetch, capsys) -> None:
    assert http_fetch.main(["--url", "ftp://example.com"]) == 2
    assert http_fetch.main(["--url", "https://example.com", "--method", "INVALID"]) == 2


def test_http_fetch_network_errors(http_fetch, capsys) -> None:
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("DNS failed")):
        assert http_fetch.main(["--url", "https://example.com"]) == 2

    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        assert http_fetch.main(["--url", "https://example.com"]) == 2
