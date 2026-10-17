"""Explicit authority boundary for the same guarded, journaled capabilities.

The caller authenticates the owner. User authority means that owner's current
request; Dream authority requires the autonomous coordinator's verifier decision.
Chat mounting is deliberately outside this change.
"""

from models.agent_edit import HarnessEdit
from models.agent_tools import HarnessQuestion
from contextlib import nullcontext
from database import review_store
from utils.agent_capabilities import tools


def apply_staged(uid, item, *, authority, verified=False):
    if authority not in {'user', 'dream'}:
        raise ValueError('agent_invalid_authority')
    if authority == 'dream' and not verified:
        raise ValueError('agent_verification_required')
    if isinstance(item.operation, HarnessQuestion):
        raise ValueError('agent_question_requires_review')
    with review_store.user_request_authority(uid) if authority == 'user' else nullcontext():
        if isinstance(item.operation, HarnessEdit):
            return tools.apply_verified_edit(
                uid, item.operation, item.records, expected_records=item.fences, authority=authority
            )
        from utils.agent_capabilities.registry import get_kind

        return get_kind('vocabulary').apply(
            uid, item.operation, item.records, expected_records=item.fences, authority=authority
        )
