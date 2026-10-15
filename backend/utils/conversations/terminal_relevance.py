"""Total, model-free decisions for lifecycle paths that bypass normal assessment.

Only terminal repair assesses transcript rules. Imports and provisional intake
retain their existing keep policy, explicitly attributed to their owning path.
The decision core uses pure rules and explicit protection callbacks; recording
loads metrics lazily at the persistence boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable
import re

from utils.conversations.relevance_rules import RULES_VERSION, deterministic_relevance

from utils.conversation_relevance_labels import TERMINAL_PATHS, DECISION_TRIGGERS, DECIDERS

# Terminal snapshots may belong to integrations/cameras whose useful content
# lives outside transcript_segments. Restrict transcript-only repair to audio.
TRANSCRIPT_SOURCES = frozenset(
    {
        'friend',
        'omi',
        'fieldy',
        'bee',
        'plaud',
        'frame',
        'friend_com',
        'apple_watch',
        'phone',
        'phone_call',
        'desktop',
        'sdcard',
        'limitless',
        'rayban_meta',
    }
)


def valid_decision(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get('verdict'), str)
        and value['verdict'] in {'keep', 'discard'}
        and isinstance(value.get('decided_by'), str)
        and value['decided_by'] in DECIDERS
        and isinstance(value.get('reason'), str)
        and re.fullmatch(r'[a-z][a-z0-9_]{0,39}', value['reason']) is not None
        and isinstance(value.get('trigger'), str)
        and value['trigger'] in DECISION_TRIGGERS
    )


def terminal_decision(
    row: Mapping[str, Any],
    *,
    path: str,
    texts: Sequence[str] = (),
    decoded: bool = False,
    assess: bool = False,
    calendar_retains: Callable[[], bool | None] | None = None,
    photos_retain: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    """Preserve an existing verdict; never infer silence from unreadable input.

    A missing calendar check (or its failure) protects a possible meeting.
    User discards are never promoted and user restores outrank all rules.
    Photos and wake-word markers bypass transcript-only assessment entirely.
    """
    assert path in TERMINAL_PATHS
    prior = row.get('relevance_decision')
    source = getattr(row.get('source'), 'value', row.get('source'))
    discarded = bool(row.get('discarded'))
    if valid_decision(prior) and (prior['verdict'] == 'discard') == discarded:
        return dict(prior)
    verdict, tier, reason = 'keep', 'policy', f'{path}_default'
    if discarded:
        verdict, reason = 'discard', 'already_discarded'
    elif row.get('sync_relevance_user_kept'):
        tier, reason = 'user', 'restored'
    elif isinstance(prior, Mapping) and prior.get('verdict') == 'keep':
        # Missing provenance is not permission to reverse prior positive evidence.
        tier, reason = 'policy', 'prior_keep'
        if prior.get('decided_by') == 'rule':
            tier = 'rule'
            prior_reason = prior.get('reason')
            reason = (
                prior_reason
                if isinstance(prior_reason, str) and prior_reason in {'explicit_reminder', 'substantial_length'}
                else 'prior_rule_keep'
            )
        elif prior.get('reason') == 'calendar_overlap':
            tier, reason = 'override', 'calendar_overlap'
    elif (
        assess
        and decoded
        and isinstance(source, str)
        and source in TRANSCRIPT_SOURCES
        and not (
            row.get('imported')
            or row.get('has_photos')
            or row.get('photos')
            or row.get('user_title')
            or row.get('starred')
            or row.get('folder_user_set')
            or _has_wake_word(texts)
        )
    ):
        rule_verdict, rule = deterministic_relevance(texts, None)
        if rule_verdict == 'keep':
            verdict, tier, reason = 'keep', 'rule', rule
        elif rule_verdict == 'discard':
            try:
                if photos_retain():
                    return {
                        'verdict': 'keep',
                        'decided_by': 'policy',
                        'reason': f'{path}_default',
                        'trigger': path,
                        'rules_version': RULES_VERSION,
                    }
                retains = calendar_retains() if calendar_retains is not None else None
            except Exception:
                retains = None
            if retains is None:
                reason = f'{path}_default'
            elif retains:
                tier, reason = 'override', 'calendar_overlap'
            else:
                verdict, tier, reason = 'discard', 'rule', rule
    return {'verdict': verdict, 'decided_by': tier, 'reason': reason, 'trigger': path, 'rules_version': RULES_VERSION}


def _has_wake_word(texts: Sequence[str]) -> bool:
    from utils.conversations.wake_word import find_wake_word_matches

    return bool(find_wake_word_matches([{'text': text} for text in texts]))


def stamp_terminal_decision(payload: dict[str, Any], *, path: str) -> None:
    """Explicit keep policy at an admission boundary; normal assessment follows."""
    decision = terminal_decision(payload, path=path)
    if payload.get('relevance_decision') == decision:
        return
    payload['relevance_decision'] = decision
    # Never change a pre-existing discard at these policy-only boundaries.
    from utils.metrics import record_conversation_relevance

    record_conversation_relevance(
        trigger=decision['trigger'],
        verdict=decision['verdict'],
        decided_by=decision['decided_by'],
        reason=decision['reason'],
    )
