"""``_LONG_SECRET_RE`` swallowed absolute paths before ``_ABS_PATH_RE`` saw them.

``build_intent_summary`` redacts an absolute path down to its basename on
purpose -- ``_redact_path_keep_basename`` exists for that, and the contract
test in ``test_decision_log_contract`` asserts the basename survives, because
the basename is what makes the summary worth mining in the first place.

A path is a run of ``[A-Za-z0-9_/-]``, which is exactly what ``_LONG_SECRET_RE``
matches at 32 characters or more, and it ran first. Any path whose dot-free
prefix reached 32 characters -- an ordinary project path, a few directories
deep -- was replaced by ``[secret]`` before the path rule ever ran. The summary
then claimed the turn mentioned a credential when it mentioned a file, and the
filename was gone.

The existing contract test passes only because its fixture path
(``/home/alice/private/vendor.pdf``) is 25 characters before the extension.
One directory deeper and it goes red.
"""

from __future__ import annotations

import pytest

from agentos.observability.decision_log import (
    _ABS_PATH_RE,
    _LONG_SECRET_RE,
    build_intent_summary,
)

# ── the report ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "basename"),
    [
        ("/home/alice/projects/backend/src/handlers.py", "handlers.py"),
        ("/Users/alice/Documents/reports/q3-vendor.pdf", "q3-vendor.pdf"),
        ("/home/alice/work/agentos/src/agentos/config.yaml", "config.yaml"),
        ("/root/services/payments/deploy/values.yaml", "values.yaml"),
    ],
)
def test_a_long_absolute_path_keeps_its_basename(path, basename):
    summary = build_intent_summary(f"summarise {path}")
    assert summary == f"summarise [path:{basename}]"
    assert "[secret]" not in summary, "a path is not a credential"


def test_the_fixture_from_the_contract_test_is_just_under_the_threshold():
    """Why the existing contract test stayed green: it is 25 chars, not 32.

    This is a guard, not proof -- it passes on `main` too. It pins the reason
    the defect went unnoticed, so shortening the fixture cannot hide it again.
    """
    short = "/home/alice/private/vendor.pdf"
    assert len(_LONG_SECRET_RE.findall(short)) == 0
    assert build_intent_summary(f"analyze {short}") == "analyze [path:vendor.pdf]"

    deeper = "/home/alice/private/docs/reports/vendor.pdf"
    assert _LONG_SECRET_RE.search(deeper) is not None, "the long-token rule does reach it"
    assert build_intent_summary(f"analyze {deeper}") == "analyze [path:vendor.pdf]"


# ── the reorder must not hand back a secret ────────────────────────────────


@pytest.mark.parametrize(
    "secret",
    [
        "sk-1234567890abcdef1234567890abcdef",
        "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "ghp_16C7e42F292c6912E7710c838347Ae178B4a",
    ],
)
def test_a_secret_stored_as_a_filename_is_still_dropped(secret):
    """The path rule now runs first, so the basename it keeps is re-checked."""
    summary = build_intent_summary(f"use /home/alice/tokens/{secret} now")
    assert secret not in summary
    assert summary == "use [path] now"


def test_a_bare_long_secret_outside_a_path_is_still_redacted():
    """Positive control: the long-token rule still runs, just second."""
    assert build_intent_summary("token AbCdEfGhIjKlMnOpQrStUvWxYz0123456789 ok") == (
        "token [secret] ok"
    )


@pytest.mark.parametrize(
    "text",
    [
        "deploy with api_key=sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz012345",
        "mail alice@example.com about /home/alice/private/vendor.pdf",
        "fetch https://example.com/a/very/long/path/that/keeps/going/on",
    ],
)
def test_the_other_rules_are_unchanged(text):
    """Guards: URL, email and assignment redaction are untouched by the reorder."""
    summary = build_intent_summary(text)
    for leaked in ("sk-proj-", "alice@example.com", "https://"):
        assert leaked not in summary


def test_a_relative_path_is_out_of_scope_here():
    """Documenting the residue, not blessing it.

    ``_ABS_PATH_RE`` matches only machine-local absolute paths, so a relative
    path is never handed to the basename rule and is still swallowed whole by
    ``_LONG_SECRET_RE``. Fixing that means narrowing the long-token class
    itself (dropping ``/``), which trades away redaction coverage and is a
    separate decision -- deliberately not made in this change. This test pins
    the boundary of what was fixed so the residue is not mistaken for it.
    """
    assert _ABS_PATH_RE.search("src/agentos/observability/decision_log.py") is None
    assert "[secret]" in build_intent_summary("open src/agentos/observability/decision_log.py")
