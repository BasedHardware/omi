"""Audit trail for support operator commands: ``support_actions/{action_id}``.

Every ``scripts/support/ops.py`` command, read or write, records one document
before it touches customer data and finishes it afterwards. The document holds
the ticket, the human who asked (``actor``), the agent or operator identity
that ran it, the command, a digest of its arguments, digests of the state it
changed, and the outcome. It never holds customer content: results are stored
as a digest plus a short content-free summary supplied by the command.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator
from uuid import uuid4

from database.account_deletion_marker import account_deletion_firestore_client

SUPPORT_ACTIONS_COLLECTION = "support_actions"
SUPPORT_ACTION_SCHEMA_VERSION = "support_action.v1"
_SUMMARY_MAX_KEYS = 32


class SupportActionError(RuntimeError):
    """The audit record could not be written, so the command must not run."""


@dataclass(frozen=True)
class ActionContext:
    """Who is acting, for which ticket, and why. Required on every command."""

    ticket: str
    actor: str
    reason: str
    agent: str
    apply: bool = False
    # The cloud identity the command actually ran under (from ADC), recorded next
    # to the self-declared ``agent`` so the trail does not rest on CLI text alone.
    principal: str | None = None

    def __post_init__(self) -> None:
        for name in ("ticket", "actor", "reason", "agent"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SupportActionError(f"{name} is required")


@dataclass
class ActionRecord:
    """Mutable handle a command fills in while it runs."""

    action_id: str
    summary: dict[str, Any] = field(default_factory=dict)
    before_digest: str | None = None
    after_digest: str | None = None


def digest(value: Any) -> str:
    """Stable SHA-256 of a JSON-serializable value (sorted keys, str fallback)."""

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _content_free_summary(summary: dict[str, Any]) -> dict[str, Any]:
    if len(summary) > _SUMMARY_MAX_KEYS:
        raise SupportActionError("action summary has too many keys")
    clean: dict[str, Any] = {}
    for key, value in summary.items():
        if isinstance(value, (bool, int, float)) or value is None:
            clean[key] = value
        elif isinstance(value, str) and len(value) <= 200:
            clean[key] = value
        else:
            clean[key] = {"digest": digest(value)}
    return clean


def _collection(firestore_client: Any | None) -> Any:
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    return client.collection(SUPPORT_ACTIONS_COLLECTION)


@contextmanager
def record_action(
    ctx: ActionContext,
    command: str,
    args: dict[str, Any],
    *,
    firestore_client: Any | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Iterator[ActionRecord]:
    """Write a ``started`` audit document, run the body, then finish it.

    A failure to write the starting document aborts before the body runs. The
    finishing write records ``succeeded`` or ``failed`` with the error type.
    """

    action_id = f"{now().strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:12]}"
    document = _collection(firestore_client).document(action_id)
    started = {
        "schema_version": SUPPORT_ACTION_SCHEMA_VERSION,
        "ticket": ctx.ticket,
        "actor": ctx.actor,
        "agent": ctx.agent,
        "principal": ctx.principal,
        "reason": ctx.reason,
        "command": command,
        "apply": ctx.apply,
        "args_digest": digest(args),
        "outcome": "started",
        "started_at": now(),
    }
    try:
        document.set(started)
    except Exception as exc:  # noqa: BLE001 - no audit record, no action
        raise SupportActionError("support action audit record could not be written") from exc
    record = ActionRecord(action_id=action_id)
    try:
        yield record
    except BaseException as exc:
        document.set(
            {
                "outcome": "failed",
                "error_type": type(exc).__name__,
                # What the handler recorded before failing (for example a write that
                # committed before a later verification step failed).
                "summary": _content_free_summary(record.summary),
                "before_digest": record.before_digest,
                "finished_at": now(),
            },
            merge=True,
        )
        raise
    document.set(
        {
            "outcome": "succeeded",
            "summary": _content_free_summary(record.summary),
            "before_digest": record.before_digest,
            "after_digest": record.after_digest,
            "finished_at": now(),
        },
        merge=True,
    )
