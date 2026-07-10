"""Server-side task/workstream goal-link invariant seam owned concretely by Ticket 04."""

from typing import Optional, Protocol


class WorkstreamGoalResolver(Protocol):
    def __call__(self, uid: str, workstream_id: str) -> Optional[str]: ...


class TaskLinkValidationError(ValueError):
    pass


class TaskLinkResolverUnavailableError(TaskLinkValidationError):
    pass


_resolver: Optional[WorkstreamGoalResolver] = None


def register_workstream_goal_resolver(resolver: WorkstreamGoalResolver) -> None:
    global _resolver
    _resolver = resolver


def clear_workstream_goal_resolver() -> None:
    global _resolver
    _resolver = None


def validate_task_links(uid: str, *, goal_id: Optional[str], workstream_id: Optional[str]) -> None:
    if workstream_id is None:
        return
    if _resolver is None:
        raise TaskLinkResolverUnavailableError('Ticket 04 workstream goal resolver is not registered')
    workstream_goal_id = _resolver(uid, workstream_id)
    if workstream_goal_id != goal_id:
        raise TaskLinkValidationError('task goal_id must match workstream goal_id')


__all__ = [
    'TaskLinkResolverUnavailableError',
    'TaskLinkValidationError',
    'WorkstreamGoalResolver',
    'clear_workstream_goal_resolver',
    'register_workstream_goal_resolver',
    'validate_task_links',
]
