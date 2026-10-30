"""Checks that run on every replay: label-free invariants plus contract-aware identity.

Golden cases that expect a specific person's name only measure anything when the
snapshot actually supports that name — a voice binding or an affirmative user
correction. Without support the expectation is skipped (never failed: the
identity contract forbids naming an unbound speaker), and the check inverts:
any non-owner name that reaches participants or the title without support is a
failure. Labelled cases load from a path outside Git and carry a
``contract_version``; a case written for another contract version is reported
STALE, not FAIL.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

# Bump when the checked output contract changes shape (packet-v2 pinned-default era).
CONTRACT_VERSION = 2

_SKIP = 'SKIP'
_STALE = 'STALE'
_PASS = 'PASS'
_FAIL = 'FAIL'


def _visible_text(notes: Mapping[str, Any]) -> str:
    title = str(notes.get('title') or '')
    body = '\n'.join(str(s.get('body_markdown') or '') for s in notes.get('sections') or [] if isinstance(s, Mapping))
    return f'{title}\n{body}'


def label_free_invariants(
    notes: Mapping[str, Any] | None,
    *,
    stop: str = '',
    transcript_words: int = 0,
    est_cost_usd: float = 0.0,
    cost_cap_usd: float,
    nesting_min_words: int = 1500,
) -> list[str]:
    """What every accepted note must satisfy, independent of any labelled expectation."""
    if not notes:
        return [f'no notes (stop={stop})']
    from utils.llm.notes_output_contract import is_action_heading, nested_bullet_count

    failures: list[str] = []
    sections = [s for s in notes.get('sections') or [] if isinstance(s, Mapping)]
    if not sections:
        failures.append('no sections')
    if transcript_words >= nesting_min_words and not any(
        nested_bullet_count(str(s.get('body_markdown') or '')) for s in sections
    ):
        failures.append('no nested bullets for a long transcript')
    action = [str(s.get('heading')) for s in sections if is_action_heading(str(s.get('heading') or ''))]
    if action:
        failures.append('action-item section present')
    if est_cost_usd > cost_cap_usd:
        failures.append(f'cost ${est_cost_usd:.4f} over the ${cost_cap_usd:.4f} cap')
    return failures


def _word_pattern(name: str) -> re.Pattern[str]:
    return re.compile(r'(?<!\w)' + re.escape(name) + r"(?!\w)", re.IGNORECASE)


def identity_invariants(notes: Mapping[str, Any] | None, identity: Any) -> list[str]:
    """No non-owner name in participants or the title without identity support.

    Runs on the final (post-repair) submission: the production identity repair
    should already have removed unsupported names, so any survivor is a real
    regression. Reasons carry positions, not names.
    """
    if not notes or identity is None:
        return []
    failures = []
    people = [p for p in notes.get('participants') or [] if isinstance(p, Mapping)]
    for index, person in enumerate(people):
        if person.get('is_ai_agent'):
            continue
        name = str(person.get('name') or '').strip()
        if not name:
            failures.append(f'participant {index} has no name')
        elif not identity.supported(name, person.get('speaker') or None):
            failures.append(f'participant {index} lacks identity support')
    title = str(notes.get('title') or '')
    if title:
        for name in sorted(set(identity.meeting_names)):
            if name and not identity.supported(name) and _word_pattern(name).search(title):
                failures.append('title names a person without identity support')
    return failures


@dataclass
class LabelledCase:
    id: str
    contract_version: Any
    expect: list[str] = field(default_factory=list)
    forbid: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> 'LabelledCase':
        if not data.get('id') or not isinstance(data.get('expect', []), list):
            raise SystemExit('a labelled case needs "id" and an "expect" list')
        return cls(
            id=str(data['id']),
            contract_version=data.get('contract_version', CONTRACT_VERSION),
            expect=[str(n) for n in data.get('expect') or []],
            forbid=[str(n) for n in data.get('forbid') or []],
        )


def load_cases(path: str | Path) -> dict[str, LabelledCase]:
    """Cases live in a JSONL file outside Git; nothing here ever enters the repository."""
    file = Path(path)
    if not file.exists():
        return {}
    cases: dict[str, LabelledCase] = {}
    for number, line in enumerate(file.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        case = LabelledCase.from_json(json.loads(line))
        cases[case.id] = case
        if not case.id:
            raise SystemExit(f'{file}:{number}: empty case id')
    return cases


def score_case(
    case: LabelledCase,
    notes: Mapping[str, Any] | None,
    identity: Any,
    *,
    current_version: Any = CONTRACT_VERSION,
    invariant_failures: Sequence[str] = (),
) -> dict[str, Any]:
    """PASS / FAIL / STALE plus reasons. Expected names score only when supported."""
    if case.contract_version != current_version:
        return {'status': _STALE, 'reasons': [f'contract_version {case.contract_version} != {current_version}']}
    reasons = ['no notes'] if not notes else list(invariant_failures)
    unscored = 0
    visible = _visible_text(notes or {}).casefold()
    people = [p for p in (notes or {}).get('participants') or [] if isinstance(p, Mapping)]
    for index, name in enumerate(case.expect):
        supported = identity is not None and identity.supported(name)
        if not supported:
            # The identity contract forbids naming an unbound speaker; skip, never fail.
            unscored += 1
            continue
        entry = next((p for p in people if str(p.get('name') or '').casefold() == name.casefold()), None)
        if entry is None:
            reasons.append(f'expected name {index} not in participants')
        elif not str(entry.get('speaker') or '').strip():
            reasons.append(f'expected name {index} in participants without a speaker key')
        if name.casefold() not in visible and name.split()[0].casefold() not in visible:
            reasons.append(f'expected name {index} not in title or notes')
    for index, name in enumerate(case.forbid):
        named = [p.get('name') for p in people if name.casefold() in str(p.get('name') or '').casefold()]
        if named or name.casefold() in visible:
            reasons.append(f'forbidden name {index} present')
    return {
        'status': _FAIL if reasons else _PASS,
        'reasons': reasons,
        'unscored_expected_names': unscored,
        'scored_expected_names': len(case.expect) - unscored,
    }


def summarize_case_results(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate the per-run ``case`` results attached by the adapter into counts."""
    counted = [r for r in rows if isinstance(r.get('case'), Mapping)]
    return {
        'runs': len(counted),
        'pass': sum(r['case'].get('status') == _PASS for r in counted),
        'fail': sum(r['case'].get('status') == _FAIL for r in counted),
        'stale': sum(r['case'].get('status') == _STALE for r in counted),
    }
