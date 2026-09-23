"""apply_patch's parse refusals reached the model as "an invalid argument".

The failure envelope forwards an exception's own text only for
``SafeToolUserMessage`` subclasses -- exception text may carry secrets -- so a
plain ``ValueError`` from a tool handler is rendered as the generic
``_USER_MESSAGES["ValueError"]`` line. #2888 (widened at triage to #2889-#2891)
converted four tools whose messages were authored for the model to act on;
``apply_patch`` was not among them, although it is the tool where the model
authored the input the message is describing.

#2837 then added two more refusals to the same layer, one of them carrying a
hint written specifically so the model can correct itself -- "that is a
unified-diff header; hunks here open with ``'@@@'``" -- which the envelope
discarded along with the rest.

Every parse refusal names exactly what to change -- which marker is missing,
which line lacks a prefix, which directives the parser accepts -- and the model
received none of it. The "No operations found ... Nothing was applied" refusal
is the sharpest case: the comment above it says it is raised loudly rather than
reported as "no changes" because *"a patch that fails is retried, one that
reports success while dropping every operation is believed"*. The envelope
reduced it to a sentence that says nothing about what failed, so the retry it
exists to trigger is an uninformed one.

Only the parse layer is in scope here. ``_apply_hunk``'s context-mismatch
messages quote lines read off disk rather than the model's own patch, so they
stay ``ValueError``; see ``test_context_mismatch_text_is_still_withheld``.
"""

from __future__ import annotations

import pytest

from agentos.tools.builtin import patch as patch_tool
from agentos.tools.builtin.patch import Hunk
from agentos.tools.envelope import build_tool_failure_envelope
from agentos.tools.types import SafeToolError

GENERIC = "The tool received an invalid argument."


def _model_sees(patch_text: str) -> str:
    with pytest.raises(SafeToolError) as excinfo:
        patch_tool._parse_patch(patch_text)
    return build_tool_failure_envelope(excinfo.value, "apply_patch")["user_message"]


# ── the report ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "patch_text", "expected_fragment"),
    [
        (
            "missing begin marker",
            "*** Add File: a.py\n+x\n*** End Patch",
            "Missing '*** Begin Patch' marker",
        ),
        (
            "missing end marker",
            "*** Begin Patch\n*** Add File: a.py\n+x\n",
            "Missing '*** End Patch' marker",
        ),
        (
            "add-file line without a + prefix",
            "*** Begin Patch\n*** Add File: a.py\nprint(1)\n*** End Patch",
            "expected a '+' prefix",
        ),
        (
            "hunk line without a recognised prefix",
            "*** Begin Patch\n*** Update File: a.py\n@@@ -1,1 +1,1 @@@\nx = 1\n*** End Patch",
            "expected a ' ', '-', or '+' prefix",
        ),
        (
            "update block with a unified-diff header",
            "*** Begin Patch\n*** Update File: a.py\n@@ -1,1 +1,1 @@\n-x\n+y\n*** End Patch",
            "hunks here open with '@@@'",
        ),
        (
            "update block with no hunks at all",
            "*** Begin Patch\n*** Update File: a.py\n*** End Patch",
            "No hunks found in '*** Update File: a.py' block",
        ),
        (
            "no operations between the markers",
            "*** Begin Patch\n*** End Patch",
            "Nothing was applied",
        ),
    ],
)
def test_the_model_is_told_what_to_fix(label, patch_text, expected_fragment):
    message = _model_sees(patch_text)
    assert expected_fragment in message, label
    assert message != GENERIC, label


def test_the_loud_refusal_stays_loud():
    """The "Nothing was applied" case, which exists to be actionable.

    The comment above the raise says it is loud on purpose, because a patch
    that fails is retried and one that reports success is believed. Both the
    accepted directives and the fact that nothing was written must survive.
    """
    message = _model_sees("*** Begin Patch\n*** End Patch")
    for fragment in (
        "*** Add File:",
        "*** Update File:",
        "*** Delete File:",
        "Nothing was applied",
    ):
        assert fragment in message


def test_the_offending_line_is_quoted_back():
    """The model can only repair the line if it is told which line it is."""
    message = _model_sees(
        "*** Begin Patch\n*** Add File: a.py\n    pass\n*** End Patch",
    )
    assert "'    pass'" in message


# ── what stays withheld ────────────────────────────────────────────────────


def test_context_mismatch_text_is_still_withheld():
    """Out of scope on purpose: this message quotes the file, not the patch.

    ``_apply_hunk`` reports the line it actually read off disk. Forwarding that
    is the separate question #2888 answered for ``edit_file`` by routing the
    hint through ``redact_file_output``; nothing here changes it, and this test
    pins the boundary so the residue is not mistaken for the part that was
    fixed.
    """
    hunk = Hunk(old_start=1, old_count=1, new_start=1, new_count=1)
    hunk.lines = [" expected line"]

    with pytest.raises(ValueError) as excinfo:
        patch_tool._apply_hunk(["actual secret line\n"], hunk)

    assert not isinstance(excinfo.value, SafeToolError)
    envelope = build_tool_failure_envelope(excinfo.value, "apply_patch")
    assert envelope["user_message"] == GENERIC
    assert "actual secret line" not in envelope["user_message"]


def test_a_valid_patch_still_parses():
    """Positive control through the parser the tool actually calls."""
    ops = patch_tool._parse_patch(
        "*** Begin Patch\n*** Add File: a.py\n+print(1)\n*** End Patch",
    )
    assert len(ops) == 1
