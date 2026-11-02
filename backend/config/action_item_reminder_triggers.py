"""Which task writes must reconcile the task's client-scheduled reminder.

The phone arms a reminder locally from the FCM data message and never re-reads the task, so
every task writer has to resend it when a field it was armed from changes. Deliberately
dependency-free: the chat tool modules that call it are loaded by suites that stub ``models``.
"""

from typing import Any, Mapping

# Every task field a client-scheduled reminder is armed from: the lifecycle that
# ``should_schedule_action_item_reminder`` reads, the due time, and the title the phone displays.
# Task writers decide from this one set, so a hand-written per-writer field list cannot drop one
# (each writer used to list completion and due date only, so a renamed task kept its old title).
ACTION_ITEM_REMINDER_FIELDS = frozenset({'completed', 'status', 'deleted', 'due_at', 'description'})


def action_item_write_affects_reminder(update_data: Mapping[str, Any]) -> bool:
    """True when a task write touches a field its client reminder was armed from."""
    return not ACTION_ITEM_REMINDER_FIELDS.isdisjoint(update_data)
