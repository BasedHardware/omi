"""Server-side task/workstream goal-link invariant seam owned concretely by Ticket 04."""

from typing import Optional, Protocol

import database.goals as goals_db
import database.workstreams as workstreams_db


class WorkstreamGoalResolver(Protocol):
    def __call__(self, uid: str, workstream_id: str) -> Optional[str]:
        ...


class GoalExistenceResolver(Protocol):
    def __call__(self, uid: str, goal_id: str) -> bool:
        ...


class TaskLinkValidationError(ValueError):
    pass


class TaskLinkResolverUnavailableError(TaskLinkValidationError):
    pass


def _default_goal_exists(uid: str, goal_id: str) -> bool:
    return goals_db.get_goal_by_id(uid, goal_id) is not None


_resolver: Optional[WorkstreamGoalResolver] = workstreams_db.get_workstream_goal_id
_goal_resolver: Optional[GoalExistenceResolver] = _default_goal_exists


def register_workstream_goal_resolver(resolver: WorkstreamGoalResolver) -> None:
    global _resolver
    _resolver = resolver


def register_goal_existence_resolver(resolver: GoalExistenceResolver) -> None:
    global _goal_resolver
    _goal_resolver = resolver


def clear_workstream_goal_resolver() -> None:
    global _goal_resolver, _resolver
    _resolver = None
    _goal_resolver = None


def validate_task_links(uid: str, *, goal_id: Optional[str], workstream_id: Optional[str]) -> None:
    if goal_id is None and workstream_id is None:
        return
    if workstream_id is not None and _resolver is None:
        raise TaskLinkResolverUnavailableError('Ticket 04 workstream goal resolver is not registered')
    if goal_id is not None:
        if _goal_resolver is None:
            raise TaskLinkResolverUnavailableError('Ticket 04 goal resolver is not registered')
        if not _goal_resolver(uid, goal_id):
            raise TaskLinkValidationError('goal does not exist')
    if workstream_id is not None:
        assert _resolver is not None
        try:
            workstream_goal_id = _resolver(uid, workstream_id)
        except workstreams_db.WorkstreamNotFoundError as exc:
            raise TaskLinkValidationError('workstream does not exist') from exc
        if workstream_goal_id != goal_id:
            raise TaskLinkValidationError('task goal_id must match workstream goal_id')


__all__ = [
    'TaskLinkResolverUnavailableError',
    'TaskLinkValidationError',
    'WorkstreamGoalResolver',
    'clear_workstream_goal_resolver',
    'register_goal_existence_resolver',
    'register_workstream_goal_resolver',
    'validate_task_links',
]
