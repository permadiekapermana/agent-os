"""``MSTeamsChannel.send`` must respect Teams' message cap.

Teams caps a message at 28 KB. ``send`` handed ``message.content`` straight to
``send_activity`` with nothing capping it, so a long final answer — a file
dump, a long report — went out as one oversized activity. The gateway's
final-reply path logs a failed ``send`` and moves on
(``channel_dispatch.stream_relay_batch_fallback_failed``), so the answer the
user is waiting for disappears with nothing in the conversation saying so.

``split_text_for_limit``'s own docstring calls itself "shared by every adapter
with a platform message-length cap". Telegram and Discord adopted it in #1544
and Slack in PR #2237; this adapter never did.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from agentos.channels.msteams import MSTeamsChannel, MSTeamsChannelConfig
from agentos.channels.types import OutgoingMessage


class _RecordingTurnContext:
    def __init__(self, sent: list[str]) -> None:
        self._sent = sent

    async def send_activity(self, payload: Any) -> Any:
        self._sent.append(str(payload))
        return SimpleNamespace(id=f"msg-{len(self._sent)}")


class _CapturingAdapter:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def continue_conversation(self, ref: Any, callback: Any, bot_id: Any = None) -> None:
        await callback(_RecordingTurnContext(self.sent))


def _channel() -> tuple[MSTeamsChannel, _CapturingAdapter]:
    adapter = _CapturingAdapter()
    channel = MSTeamsChannel(config=MSTeamsChannelConfig(name="msteams"))
    channel._references["conv-1"] = SimpleNamespace()
    channel._adapter = adapter  # type: ignore[assignment]
    return channel, adapter


async def _send(channel: MSTeamsChannel, content: str) -> None:
    await channel.send(OutgoingMessage(content=content, reply_to=None))


# Teams' documented cap, spelled out here rather than imported from the
# adapter, so these tests measure the delivered activities against the
# platform's own number and not against whatever the adapter happens to use.
_TEAMS_DOCUMENTED_CAP = 28 * 1024

# A report-sized answer: well over the cap, with line boundaries to cut on.
_LONG_REPLY = "\n".join(f"line {n}: " + "x" * 80 for n in range(1200))


@pytest.mark.asyncio
async def test_every_activity_stays_within_the_teams_cap() -> None:
    """No single activity may exceed the limit — that is the whole defect."""
    channel, adapter = _channel()

    await _send(channel, _LONG_REPLY)

    assert len(_LONG_REPLY) > _TEAMS_DOCUMENTED_CAP  # the input is oversized
    assert adapter.sent, "send emitted nothing"
    assert max(len(text) for text in adapter.sent) <= _TEAMS_DOCUMENTED_CAP


@pytest.mark.asyncio
async def test_the_chunks_reassemble_into_the_whole_reply() -> None:
    """Splitting must not drop or duplicate any of the answer."""
    channel, adapter = _channel()

    await _send(channel, _LONG_REPLY)

    assert "".join(adapter.sent) == _LONG_REPLY


@pytest.mark.asyncio
async def test_an_oversized_reply_becomes_more_than_one_activity() -> None:
    """The positive control for the split itself."""
    channel, adapter = _channel()

    await _send(channel, _LONG_REPLY)

    assert len(adapter.sent) > 1


@pytest.mark.asyncio
async def test_a_short_reply_is_still_one_activity() -> None:
    """A guard: the ordinary reply must not gain a chunking round trip."""
    channel, adapter = _channel()

    await _send(channel, "hello")

    assert adapter.sent == ["hello"]


@pytest.mark.asyncio
async def test_each_chunk_is_captured_by_value() -> None:
    """The callbacks close over a loop variable — bind it, don't read it late.

    ``send_streaming`` already carries this defence for the same reason; the
    chunks would otherwise all report the last segment.
    """
    channel, adapter = _channel()

    await _send(channel, _LONG_REPLY)

    assert len(adapter.sent) > 1
    assert len(set(adapter.sent)) == len(adapter.sent)


@pytest.mark.asyncio
async def test_the_last_chunk_id_is_the_one_remembered() -> None:
    """A later edit or reply must address the message that ends the answer."""
    channel, adapter = _channel()

    await _send(channel, _LONG_REPLY)

    remembered = set(channel._message_conversation_keys)
    assert remembered == {f"msg-{len(adapter.sent)}"}
