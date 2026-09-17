"""Robustness tests for pdf-toolkit scripts.

Ensures that malformed page range specs and corrupt/unreadable PDF files
are handled gracefully with clean exit code 2 and standard error messages,
never escaping as unhandled tracebacks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src" / "agentos" / "skills" / "bundled" / "pdf-toolkit" / "scripts"


def _import_script(name: str):
    sys.path.insert(0, str(SCRIPTS))
    try:
        return __import__(name)
    finally:
        sys.path.pop(0)


def _make_pdf(path: Path, pages: int = 2) -> None:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=LETTER)
    for number in range(1, pages + 1):
        c.setFont("Helvetica", 14)
        c.drawString(72, 720, f"PAGE {number}")
        c.showPage()
    c.save()


@pytest.fixture
def corrupt_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "corrupt.pdf"
    p.write_bytes(b"%PDF-1.4\nthis is not a valid pdf stream header or trailer\n")
    return p


@pytest.fixture
def valid_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "valid.pdf"
    _make_pdf(p, 3)
    return p


@pytest.mark.parametrize(
    "invalid_spec",
    [
        "abc",
        "1-foo",
        "bar-2",
        "1-2-3",
        "0",
        "-5",
        "1--2",
        "",
        "   ",
        ",,",
    ],
)
def test_split_rejects_invalid_page_specs(
    valid_pdf: Path,
    tmp_path: Path,
    invalid_spec: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    split_mod = _import_script("split")
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        ["split.py", str(valid_pdf), "--pages", invalid_spec, "--out", str(out_dir)],
    )

    exit_code = split_mod.main()
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "error: invalid page specification" in captured.err
    assert not out_dir.exists()


def test_split_handles_corrupt_pdf(
    corrupt_pdf: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    split_mod = _import_script("split")
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        ["split.py", str(corrupt_pdf), "--pages", "1", "--out", str(out_dir)],
    )

    exit_code = split_mod.main()
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "error: failed to read PDF" in captured.err
    assert not out_dir.exists()


def test_extract_handles_corrupt_pdf(
    corrupt_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    extract_mod = _import_script("extract")
    monkeypatch.setattr(sys, "argv", ["extract.py", str(corrupt_pdf)])

    exit_code = extract_mod.main()
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "error: failed to extract" in captured.err


def test_form_fill_list_fields_handles_corrupt_pdf(
    corrupt_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    form_fill_mod = _import_script("form_fill")
    monkeypatch.setattr(sys, "argv", ["form_fill.py", str(corrupt_pdf), "--list-fields"])

    exit_code = form_fill_mod.main()
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "error: failed to read form" in captured.err


def test_form_fill_fill_handles_corrupt_pdf(
    corrupt_pdf: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    form_fill_mod = _import_script("form_fill")
    data_file = tmp_path / "data.json"
    data_file.write_text('{"name": "Alice"}', encoding="utf-8")
    out_pdf = tmp_path / "filled.pdf"

    monkeypatch.setattr(
        sys,
        "argv",
        ["form_fill.py", str(corrupt_pdf), str(data_file), "--out", str(out_pdf)],
    )

    exit_code = form_fill_mod.main()
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "error: failed to fill" in captured.err
    assert not out_pdf.exists()


def test_merge_handles_corrupt_input_among_valid_inputs(
    valid_pdf: Path,
    corrupt_pdf: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    merge_mod = _import_script("merge")
    out_pdf = tmp_path / "merged.pdf"
    monkeypatch.setattr(
        sys,
        "argv",
        ["merge.py", str(valid_pdf), str(corrupt_pdf), "--out", str(out_pdf)],
    )

    exit_code = merge_mod.main()
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "warn: failed to read" in captured.err
    summary = json.loads(captured.out)
    assert summary["pages_written"] == 3
    assert str(corrupt_pdf) in summary["missing_files"]
    assert out_pdf.is_file()


def test_merge_fails_cleanly_when_all_inputs_are_corrupt(
    corrupt_pdf: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    merge_mod = _import_script("merge")
    out_pdf = tmp_path / "merged.pdf"
    monkeypatch.setattr(
        sys,
        "argv",
        ["merge.py", str(corrupt_pdf), "--out", str(out_pdf)],
    )

    exit_code = merge_mod.main()
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "warn: failed to read" in captured.err
    assert "error: no requested page exists in any input" in captured.err
    assert not out_pdf.exists()


@pytest.mark.parametrize(
    "invalid_pages",
    [
        "abc",
        "1-foo",
        "0",
        "-3",
        "1--4",
    ],
)
def test_merge_manifest_rejects_malformed_pages_spec(
    valid_pdf: Path,
    tmp_path: Path,
    invalid_pages: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    merge_mod = _import_script("merge")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps([{"file": str(valid_pdf), "pages": invalid_pages}]), encoding="utf-8"
    )
    out_pdf = tmp_path / "merged.pdf"

    monkeypatch.setattr(
        sys,
        "argv",
        ["merge.py", str(manifest), "--out", str(out_pdf)],
    )

    exit_code = merge_mod.main()
    assert exit_code == 2

    captured = capsys.readouterr()
    assert 'error: manifest entry 0 has invalid "pages" spec' in captured.err
    assert not out_pdf.exists()
