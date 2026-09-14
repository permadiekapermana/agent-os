"""Tests for apply_patch marker resolution logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentos.tools.builtin.patch import _parse_patch, apply_patch
from agentos.tools.types import ToolContext, current_tool_context


def _original_async(fn):
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.mark.asyncio
async def test_apply_patch_preamble_end_marker_does_not_drop_ops(tmp_workspace: Path) -> None:
    """A stray *** End Patch in a preamble does not cause patch ops to be dropped."""
    patch_text = (
        "*** End Patch\n*** Begin Patch\n*** Add File: sample.txt\n+hello world\n*** End Patch"
    )
    ctx = ToolContext(workspace_dir=str(tmp_workspace))
    token = current_tool_context.set(ctx)
    try:
        raw_apply_patch = _original_async(apply_patch)
        res = await raw_apply_patch(patch_text)
        assert "1 file(s) added" in res
        assert (tmp_workspace / "sample.txt").read_text(encoding="utf-8") == "hello world"
    finally:
        current_tool_context.reset(token)


def test_parse_patch_missing_end_marker_after_begin_raises() -> None:
    """Missing *** End Patch after *** Begin Patch raises ValueError."""
    patch_text = "*** End Patch\n*** Begin Patch\n*** Add File: sample.txt\n+hello world"
    with pytest.raises(ValueError, match="Missing '\\*\\*\\* End Patch' marker"):
        _parse_patch(patch_text)
