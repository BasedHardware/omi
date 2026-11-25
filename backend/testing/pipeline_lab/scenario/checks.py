"""Evaluate a scenario's expectations against the conversations a run produced (pure, stdlib only).

A *snapshot* is the list of v3 conversations at one instant, each summarized by ``conversation_row``:
recording labels, words, Home visibility and its reason, manual end, kind, status. No text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from testing.pipeline_lab.scenario.spec import FINISH_ALIAS, Check, Scenario

# Process exit codes for ``scenario run`` (one scenario): passed / xfail 0, failed / xpass 1, error 2.
OUTCOMES = {'passed': 0, 'xfail': 0, 'failed': 1, 'xpass': 1, 'error': 2}


@dataclass(frozen=True)
class CheckResult:
    check: Check
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {'check': self.check.describe(), 'ok': self.ok, 'detail': self.detail}


def conversation_row(row: Mapping[str, Any], label_of, words: int) -> dict[str, Any]:
    """The safe summary of one v3 conversation: no ids beyond the short handle, no text."""
    status = row.get('status')
    return {
        'handle': str(row.get('id') or '')[:8],
        'recordings': [label_of(str(r)) for r in row.get('v3_recording_ids') or []],
        'words': words,
        'visible': bool(
            not row.get('home_hidden')
            and not row.get('deleted')
            and not row.get('discarded')
            and getattr(status, 'value', status) != 'failed'
        ),
        'hidden_reason': row.get('home_hidden_reason'),
        'manual_end': bool(row.get('manual_end')),
        'kind': row.get('kind'),
        'status': getattr(status, 'value', status),
        'deleted': bool(row.get('deleted')),
        'started_at': row.get('started_at'),
    }


def _matches(conv: Mapping[str, Any], fields: Mapping[str, Any]) -> list[str]:
    """Mismatches of one conversation against the check's fields (empty = it matches)."""
    misses = []
    for key, want in fields.items():
        if key == 'recordings':
            ok = sorted(set(conv['recordings'])) == sorted(set(want))
            have = conv['recordings']
        elif key == 'recordings_include':
            ok = set(want) <= set(conv['recordings'])
            have = conv['recordings']
        elif key == 'min_words':
            ok = conv['words'] >= want
            have = conv['words']
        elif key == 'on_home':
            # Set by scenario/home.py from the product's Home route; None = the route gave no answer.
            have = conv.get('on_home')
            ok = have is not None and have == want
        elif key == 'hidden_reason':
            ok = conv['hidden_reason'] == want
            have = conv['hidden_reason']
        else:
            ok = conv.get(key) == want
            have = conv.get(key)
        if not ok:
            misses.append(f'{key}={have!r} (want {want!r})')
    return misses


def evaluate(check: Check, snapshot: Sequence[Mapping[str, Any]], finish_label: Optional[str]) -> CheckResult:
    live = [c for c in snapshot if not c.get('deleted')]
    if check.no_hidden_with is not None:
        label = finish_label if check.no_hidden_with == FINISH_ALIAS else check.no_hidden_with
        hidden = [c for c in live if label in c['recordings'] and not c['visible']]
        if hidden:
            reasons = ', '.join(f"{c['handle']} {c['recordings']} {c['hidden_reason']}" for c in hidden)
            return CheckResult(check, False, f'hidden: {reasons}')
        return CheckResult(check, True, 'none hidden')
    label = finish_label if check.conversation_of == FINISH_ALIAS else check.conversation_of
    if label is None:
        return CheckResult(check, False, 'the Finish cut no recording')
    holders = [c for c in live if label in c['recordings']]
    if not holders:
        return CheckResult(check, False, f'no conversation holds {label}')
    misses = {c['handle']: _matches(c, check.fields) for c in holders}
    good = [handle for handle, miss in misses.items() if not miss]
    if good:
        return CheckResult(check, True, f'{label} in {good[0]}')
    detail = '; '.join(f'{handle}: ' + ', '.join(miss) for handle, miss in misses.items())
    return CheckResult(check, False, detail)


def outcome(scenario: Scenario, results: Sequence[CheckResult], error: Optional[str] = None) -> str:
    """``xfail`` only when a check the known bug names fails and every other check passes; a failure the
    bug does not explain is ``failed`` (an empty run, a missing Finish target, an unrelated regression)."""
    if error:
        return 'error'
    failure = scenario.expected_failure
    named = set((failure or {}).get('checks') or ())
    failing = [r for r in results if not r.ok]
    if any(r.check.label not in named for r in failing):
        return 'failed'
    if failing:
        return 'xfail'
    if failure is None:
        return 'passed'
    return 'xpass' if failure.get('strict', True) else 'passed'
