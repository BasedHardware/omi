"""Runtime witnesses for the ``database.conversations`` query-helper call surface.

Every statically discovered ``get_conversations*`` call-site binding must map
to a named ``CallerWitness``; each witness executes the real owning function
with the helper monkeypatched to capture signature-bound arguments, and every
captured call must fit one of the binding's named ``CallerProfile`` domains.
Unrelated body edits must not break coverage; new callers, aliases, wrappers,
or widened argument domains must fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from tests.support.firestore_caller_witnesses import (
    WITNESSES,
    CallerWitness,
    HelperCapture,
    install_capture,
    matching_profile,
    rejected_trial,
    trial,
    witness_completeness_errors,
)
from tests.support.firestore_conversation_profiles import (
    PROFILES,
    TARGETS,
    discover_callers,
    discover_conversation_callers,
)
from tests.support.firestore_query_drivers import _block_all_sockets, block_outbound_network

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def discovered_callers():
    return discover_conversation_callers(BACKEND_ROOT)


def test_witnesses_cover_the_discovered_call_surface(discovered_callers):
    errors = witness_completeness_errors(discovered_callers)
    assert not errors, '; '.join(errors)


@pytest.mark.parametrize('key', sorted(WITNESSES))
def test_named_witness_matches_runtime_call(key, monkeypatch):
    witness = WITNESSES[key]
    capture = install_capture(monkeypatch, witness)
    with block_outbound_network(), _block_all_sockets() as sockets:
        witness.run(monkeypatch, capture)
    assert not sockets, f'{key}: witness recipe attempted network: {sockets[:3]}'
    assert capture.calls, f'{key}: recipe produced no helper call'
    bound = set()
    for call in capture.calls:
        name = matching_profile(witness.target, call, witness.profiles)
        assert name is not None, f'{key}: bound args {call} fit no named profile in {witness.profiles}'
        bound.add(name)
    unexercised = set(witness.profiles) - bound
    assert not unexercised, f'{key}: named profiles never exercised by the real caller: {sorted(unexercised)}'


def test_trial_fails_when_function_errors_before_capture(monkeypatch):
    capture = HelperCapture(calls=[], function=lambda *a, **k: None)
    with pytest.raises(TypeError):
        trial(capture, lambda required_kwarg: None)


def test_trial_fails_when_branch_drops_helper_call(monkeypatch):
    capture = HelperCapture(calls=[], function=lambda *a, **k: None)
    with pytest.raises(AssertionError, match='exactly one helper call'):
        trial(capture, lambda flag: flag if flag else flag, False)


def test_rejected_trial_fails_on_helper_call(monkeypatch):
    calls = []

    def helper(**kwargs):
        calls.append(kwargs)
        return []

    def caller():
        helper(uid='u1')
        raise HTTPException(status_code=400)

    capture = HelperCapture(calls=calls, function=helper)
    with pytest.raises(AssertionError, match='rejected trial reached'):
        rejected_trial(capture, caller)


def test_witness_profiles_resolve():
    for witness in WITNESSES.values():
        names = {profile.name for profile in PROFILES[witness.target]}
        assert witness.profiles and set(witness.profiles) <= names, witness.key


def test_completeness_fails_on_unknown_caller(discovered_callers):
    mutated = dict(discovered_callers)
    mutated['utils/fake.py:new_caller:database.conversations.get_conversations'] = {
        'target': 'database.conversations.get_conversations',
        'references': 1,
    }
    assert witness_completeness_errors(mutated)


def test_completeness_fails_on_alias_binding(discovered_callers):
    mutated = dict(discovered_callers)
    mutated['utils/fake.py:aliased:database.conversations.get_conversations'] = {
        'target': 'database.conversations.get_conversations',
        'references': 1,
    }
    assert witness_completeness_errors(mutated)


def test_completeness_fails_on_wrapper_reference(discovered_callers):
    mutated = {key: dict(row) for key, row in discovered_callers.items()}
    key = 'routers/conversations.py:get_conversations:database.conversations.get_conversations_without_photos'
    mutated[key]['references'] += 1
    assert witness_completeness_errors(mutated)


def test_completeness_fails_on_missing_caller(discovered_callers):
    dropped = sorted(discovered_callers)[0]
    mutated = {key: row for key, row in discovered_callers.items() if key != dropped}
    errors = witness_completeness_errors(mutated)
    assert any(dropped in error for error in errors)


def test_named_witness_binds_to_expected_profile(monkeypatch):
    key = 'utils/imports/limitless.py:find_legacy_limitless_conversation_id:database.conversations.get_conversations'
    witness = WITNESSES[key]
    capture = install_capture(monkeypatch, witness)
    witness.run(monkeypatch, capture)
    assert [matching_profile(witness.target, call, witness.profiles) for call in capture.calls] == [
        'limitless-legacy-lookup'
    ]


def test_unrelated_body_edit_leaves_detection_and_witnesses_unchanged(tmp_path, monkeypatch):
    consumer = tmp_path / 'consumer.py'
    consumer.write_text(
        'from database.conversations import get_conversations as listing\n' 'def read(uid):\n    return listing(uid)\n'
    )
    before = discover_callers(tmp_path, TARGETS)
    consumer.write_text(
        'from database.conversations import get_conversations as listing\n'
        'import logging\n'
        'def read(uid):\n'
        '    logging.info("reading %s", uid)\n'
        '    rows = listing(uid)\n'
        '    return [row for row in rows if row]\n'
    )
    after = discover_callers(tmp_path, TARGETS)
    assert after == before
    stub = CallerWitness(
        'consumer.py:read:database.conversations.get_conversations',
        'database.conversations.get_conversations',
        'database.conversations.get_conversations',
        ('developer-list',),
        1,
        lambda monkeypatch, capture: None,
    )
    assert not witness_completeness_errors(after, {stub.key: stub})


def test_profile_membership_rejects_widened_domains():
    target = 'database.conversations.get_conversations'
    names = WITNESSES['routers/developer.py:get_conversations:database.conversations.get_conversations'].profiles
    base = {
        'uid': 'u1',
        'limit': 25,
        'offset': 0,
        'include_discarded': False,
        'statuses': ['completed'],
        'start_date': None,
        'end_date': None,
        'categories': [],
        'folder_id': None,
        'starred': None,
        'date_field': 'created_at',
    }
    assert matching_profile(target, dict(base), names) is not None
    assert matching_profile(target, dict(base, categories=['unreviewed-category']), names) is None
    assert matching_profile(target, dict(base, statuses=['failed']), names) is None
    assert matching_profile(target, dict(base, date_field='started_at'), names) is None
    assert matching_profile(target, dict(base, starred=True, include_discarded=True), names) is None
