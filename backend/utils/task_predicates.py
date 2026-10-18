"""Pure predicates over canonical task rows. No imports, no reads: safe from async code."""

from typing import Any, Mapping


def is_open_conversation_task(task: Mapping[str, Any]) -> bool:
    """An open task that came from a conversation: live, not done, unlocked, conversation- or legacy-sourced.

    One definition for every reader that follows a task back to its conversation (the
    commitment follow-up producer, the commitments read). The owner is checked by the caller.
    """
    return (
        not task.get('deleted')
        and not task.get('completed')
        and task.get('status', 'active') == 'active'
        and bool(task.get('conversation_id'))
        and not task.get('is_locked')
        and task.get('source', 'legacy') in {'legacy', 'conversation'}
    )
