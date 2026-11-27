"""Evaluate a scenario's expectations against the conversations a run produced (pure, stdlib only).

A *snapshot* is the list of v3 conversations at one instant, each summarized by ``conversation_row``:
recording labels, words, Home visibility and its reason, manual end, kind, status, whether it has a title
and notes, and in a ``speakers`` scenario a numbers-only speaker scorecard (``speakers``). No text.

*Facts* are the rest of what a run observed, for the checks that do not read a snapshot: ``fast_finish``
(recording label -> outcome), ``finish_taps`` (one row per tap, ``finish_tap_row``), ``ops``
(``scenario/budget.py``) and ``paging`` (``scenario/home.page_to_end``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from testing.pipeline_lab.scenario import budget as budgets
from testing.pipeline_lab.scenario.spec import FINISH_ALIAS, Check, Scenario

# Process exit codes for ``scenario run`` (one scenario): passed / xfail 0, failed / xpass 1, error 2.
# ``nondeterministic``: ``--repeat`` saw results differ between repeats of the same scenario.
OUTCOMES = {'passed': 0, 'xfail': 0, 'failed': 1, 'xpass': 1, 'nondeterministic': 1, 'error': 2}


@dataclass(frozen=True)
class CheckResult:
    check: Check
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {'check': self.check.describe(), 'ok': self.ok, 'detail': self.detail}


def has_title(row: Mapping[str, Any]) -> bool:
    structured = row.get('structured') or {}
    return bool(str((structured.get('title') if isinstance(structured, Mapping) else '') or '').strip())


def has_notes(row: Mapping[str, Any]) -> bool:
    structured = row.get('structured') or {}
    return bool(str((structured.get('overview') if isinstance(structured, Mapping) else '') or '').strip())


def finish_tap_row(outcome: str, conversation: Optional[Mapping[str, Any]], label_of) -> dict[str, Any]:
    """One Finish tap as the checks read it: the branch, and the returned conversation's shape (no text)."""
    row: dict[str, Any] = {'outcome': outcome}
    if conversation is not None:
        row.update(
            titled=has_title(conversation),
            has_notes=has_notes(conversation),
            discarded=bool(conversation.get('discarded')),
            # A derived window names its sources; the recording fallback (#26288) answers with the recording.
            recordings=[label_of(str(r)) for r in conversation.get('v3_recording_ids') or []]
            or (
                [label_of(str(conversation['id']))] if conversation.get('recording') and conversation.get('id') else []
            ),
            tile_state=conversation.get('tile_state'),
        )
    return row


def conversation_row(row: Mapping[str, Any], label_of, words: int) -> dict[str, Any]:
    """The safe summary of one v3 conversation: no ids beyond the short handle, no text."""
    status = row.get('status')
    return {
        'titled': has_title(row),
        'has_notes': has_notes(row),
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


SPEAKER_RATE = {'wrong_name': 'wrong_name_rate'}  # expect key stem -> scorecard key, where they differ


def speaker_misses(card: Optional[Mapping[str, Any]], want: Mapping[str, Any]) -> list[str]:
    """Mismatches of a conversation's speaker scorecard (``speakers/scenario.SpeakerScoring.card``) against a
    ``speakers`` expect field. A ``null`` rate (nothing to measure) fails a minimum."""
    if not card:
        return ['speakers=none (no scorecard: the conversation holds no truth recording)']
    misses = []
    for key, bound in want.items():
        if key == 'final_pass':
            if card.get('final_pass') != bound:
                misses.append(f'final_pass={card.get("final_pass")!r} (want {bound!r})')
            continue
        if key == 'voices':
            count, tolerance = bound
            have = card.get('voices')
            if have is None or abs(have - count) > tolerance:
                misses.append(f'voices={have!r} (want {count}' + (f' +/- {tolerance})' if tolerance else ')'))
            continue
        stem, _, side = key.rpartition('_')
        have = card.get(SPEAKER_RATE.get(stem, stem))
        ok = have is not None and (have >= bound if side == 'min' else have <= bound)
        if not ok:
            misses.append(f'{SPEAKER_RATE.get(stem, stem)}={have!r} (want {">=" if side == "min" else "<="} {bound})')
    return misses


def _matches(conv: Mapping[str, Any], fields: Mapping[str, Any]) -> list[str]:
    """Mismatches of one conversation against the check's fields (empty = it matches)."""
    misses = []
    for key, want in fields.items():
        if key == 'speakers':
            misses.extend(speaker_misses(conv.get('speakers'), want))
            continue
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
        elif key in ('home_titled', 'home_has_notes'):
            # Set by scenario/home.py from the Home route's row; None when it is not on Home.
            have = conv.get(key)
            ok = bool(have) == want
        elif key == 'hidden_reason':
            ok = conv['hidden_reason'] == want
            have = conv['hidden_reason']
        else:
            ok = conv.get(key) == want
            have = conv.get(key)
        if not ok:
            misses.append(f'{key}={have!r} (want {want!r})')
    return misses


def _response_misses(tap: Mapping[str, Any], fields: Mapping[str, Any]) -> list[str]:
    misses = []
    for key, want in fields.items():
        have = tap.get('recordings' if key == 'recordings_include' else key)
        if key == 'recordings':
            ok = have is not None and sorted(set(have)) == sorted(set(want))
        elif key == 'recordings_include':
            ok = have is not None and set(want) <= set(have)
        else:
            ok = have == want
        if not ok:
            misses.append(f'{key}={have!r} (want {want!r})')
    return misses


def _paging_result(paging: Optional[Mapping[str, Any]]) -> tuple[bool, str]:
    if not paging:
        return False, 'Home was not paged'
    if paging.get('error'):
        return False, f'paging stopped: {paging["error"]}'
    problems = []
    for key in ('missing', 'duplicated', 'hidden_seen'):
        if paging.get(key):
            problems.append(f'{key} {len(paging[key])}')
    summary = f'{paging.get("pages")} page(s), {paging.get("seen")} of {paging.get("expected")} visible'
    return (not problems), (summary + ('; ' + ', '.join(problems) if problems else ''))


def evaluate(
    check: Check,
    snapshot: Sequence[Mapping[str, Any]],
    finish_label: Optional[str],
    facts: Optional[Mapping[str, Any]] = None,
) -> CheckResult:
    facts = facts or {}
    if check.budget is not None:
        key, cap = check.budget
        ok, detail, _ = budgets.evaluate_budget(key, cap, facts.get('ops'))
        return CheckResult(check, ok, detail)
    if check.recording is not None:
        have = (facts.get('fast_finish') or {}).get(check.recording, 'none')
        want = check.fields.get('fast_finish')
        return CheckResult(check, have == want, f'fast_finish={have!r}' + ('' if have == want else f' (want {want!r})'))
    if check.finish_response is not None:
        taps = list(facts.get('finish_taps') or [])
        if len(taps) < check.finish_response:
            return CheckResult(check, False, f'tap {check.finish_response} did not run')
        tap = taps[check.finish_response - 1]
        misses = _response_misses(tap, check.fields)
        return CheckResult(check, not misses, '; '.join(misses) or f'tap {check.finish_response}: {tap["outcome"]}')
    if check.home_paging is not None:
        ok, detail = _paging_result(facts.get('paging'))
        return CheckResult(check, ok, detail)
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
    fields = dict(check.fields)
    if 'holders' in fields:
        want = fields.pop('holders')
        if len(holders) != want:
            return CheckResult(check, False, f'holders={len(holders)} (want {want})')
        if not fields:
            return CheckResult(check, True, f'{label} in {len(holders)} conversation(s)')
    misses = {c['handle']: _matches(c, fields) for c in holders}
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


# ---- verdict rows (scenario/verdict.py) -----------------------------------------------------------

# What a verdict shows of a conversation: the fields checks and compare read; no handle (it is a random id).
VERDICT_FIELDS = (
    'recordings', 'words', 'visible', 'hidden_reason', 'manual_end', 'kind', 'status', 'titled', 'has_notes',
)  # fmt: skip


def expected_of(check: Check) -> dict[str, Any]:
    if check.budget is not None:
        return {'budget': check.budget[0], 'at_most': check.budget[1]}
    if check.no_hidden_with is not None:
        return {'no_hidden_with': check.no_hidden_with}
    if check.recording is not None:
        return {'recording': check.recording, **dict(check.fields)}
    if check.finish_response is not None:
        return {'finish_response': check.finish_response, **dict(check.fields)}
    if check.home_paging is not None:
        return {'home_paging': check.home_paging}
    return {'conversation_of': check.conversation_of, **dict(check.fields)}


def actual_of(
    check: Check,
    snapshot: Sequence[Mapping[str, Any]],
    finish_label: Optional[str],
    facts: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """What the run showed for ``check``: the holder conversation that matched (else the first holder), or
    the hidden conversations holding the label. Same selection as :func:`evaluate`."""
    facts = facts or {}
    if check.budget is not None:
        return {'budget': check.budget[0], 'count': budgets.measured(facts.get('ops') or {}, check.budget[0])}
    if check.recording is not None:
        return {
            'recording': check.recording,
            'fast_finish': (facts.get('fast_finish') or {}).get(check.recording, 'none'),
        }
    if check.finish_response is not None:
        taps = list(facts.get('finish_taps') or [])
        return {'tap': taps[check.finish_response - 1] if len(taps) >= check.finish_response else None}
    if check.home_paging is not None:
        paging = dict(facts.get('paging') or {})
        return {k: (len(v) if isinstance(v, list) else v) for k, v in paging.items() if k != 'requests'}
    live = [c for c in snapshot if not c.get('deleted')]
    if check.no_hidden_with is not None:
        label = finish_label if check.no_hidden_with == FINISH_ALIAS else check.no_hidden_with
        hidden = [c for c in live if label in c['recordings'] and not c['visible']]
        return {'label': label, 'hidden': [{k: c.get(k) for k in VERDICT_FIELDS} for c in hidden]}
    label = finish_label if check.conversation_of == FINISH_ALIAS else check.conversation_of
    holders = [c for c in live if label is not None and label in c['recordings']]
    if not holders:
        return {'label': label, 'conversation': None}
    chosen = next((c for c in holders if not _matches(c, check.fields)), holders[0])
    conversation = {k: chosen.get(k) for k in VERDICT_FIELDS}
    if 'speakers' in check.fields:  # the scorecard: numbers only
        conversation['speakers'] = chosen.get('speakers')
    return {'label': label, 'conversation': conversation, 'holders': len(holders)}
