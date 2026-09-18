"""cron.update must not wipe an existing webhook delivery on sessionTarget="main".

Webhook delivery is explicitly permitted for sessionTarget="main" -- see the
comment in ``_job_to_wire`` ("Suppressing webhook for main caused round-trip
data loss on read-back"). Only channel/announce delivery is unsupported
there. But the payload-related merge branch in ``_handle_cron_update``
unconditionally replaced ``patch["delivery"]`` with an empty
``DeliveryConfig()`` whenever the caller edited a payload-related field
(text, payloadKind, sessionTarget, ...) without also re-sending a
``delivery`` block -- silently discarding a webhook URL/token that was
correctly saved via ``cron.add``.
"""

from __future__ import annotations

from agentos.gateway.rpc import RpcContext
from agentos.gateway.rpc_cron import _handle_cron_update
from agentos.scheduler.payloads import SYSTEM_EVENT_KIND
from agentos.scheduler.types import CronJob, DeliveryConfig, DeliveryMode, SessionTarget


class _FakeScheduler:
    def __init__(self, job: CronJob) -> None:
        self.updated: dict | None = None
        self.job = job

    async def update_job(self, job_id, **patch) -> CronJob:
        self.updated = patch
        for key, value in patch.items():
            setattr(self.job, key, value)
        return self.job

    async def get_job(self, job_id) -> CronJob | None:
        return self.job if self.job.id == job_id else None


def _job_with_webhook() -> CronJob:
    return CronJob(
        id="job-1",
        name="watchdog",
        handler_key="system_event",
        payload={"kind": SYSTEM_EVENT_KIND, "text": "old text"},
        session_target=SessionTarget.MAIN,
        session_key="agent:main",
        origin_session_key="agent:main",
        delivery=DeliveryConfig(
            mode=DeliveryMode.WEBHOOK,
            webhook_url="https://hooks.example.com/x",
            webhook_token="tok",
        ),
    )


async def test_editing_text_on_a_main_job_keeps_its_existing_webhook() -> None:
    job = _job_with_webhook()
    scheduler = _FakeScheduler(job)

    await _handle_cron_update(
        {"id": "job-1", "text": "new text"},
        RpcContext(conn_id="t", cron_scheduler=scheduler),
    )

    assert scheduler.updated is not None
    # No "delivery" key in the patch at all -- the existing webhook on the
    # job itself must be left untouched, not overwritten with a copy.
    assert "delivery" not in scheduler.updated
    assert job.delivery.mode == DeliveryMode.WEBHOOK
    assert job.delivery.webhook_url == "https://hooks.example.com/x"
    assert job.delivery.webhook_token == "tok"


async def test_editing_text_on_a_main_job_with_channel_delivery_still_clears_it() -> None:
    """Channel/announce delivery is genuinely unsupported for sessionTarget=
    "main" -- that clearing behavior must be preserved."""
    job = _job_with_webhook()
    job.delivery = DeliveryConfig(mode=DeliveryMode.CHANNEL, channel_name="telegram")
    scheduler = _FakeScheduler(job)

    await _handle_cron_update(
        {"id": "job-1", "text": "new text"},
        RpcContext(conn_id="t", cron_scheduler=scheduler),
    )

    assert scheduler.updated is not None
    assert scheduler.updated["delivery"].mode == DeliveryMode.NONE
