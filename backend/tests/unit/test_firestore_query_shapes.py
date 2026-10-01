"""Runtime Firestore query-shape inventory and index guard.

A module-scoped fixture executes every registered query driver twice against
fresh recording fakes; the tests then assert:

- every statically discovered ``database.*`` querying function has a registry
  entry and every registry entry is a discovered function (AST sentinel —
  detection only, never shape construction),
- no driver raised, every driven entry produced shapes, and no unclassified
  parameters remain,
- every recorded ``calling_function`` belongs to a registry entry,
- covered-by helpers are actually observed inside one of their *named*
  covering drivers (not merely somewhere in the global capture),
- digest-pinned covered-by/skip entries keep their reviewed function bodies,
- driver trials are isolated: fresh clients per driver, deep-copied arguments,
  reset seeds/queues per trial, and leftover queued rows fail,
- the unserved-shape ledgers match the checked-in ``firestore_query_known_gaps``
  ledger exactly (full row metadata compared in both sections), and
- the export artifact is deterministic and schema-stable.

The checked-in ledger is a reviewed baseline: tests never rewrite it.
"""

from __future__ import annotations

import ast
import copy
import json
import socket
import sys
import textwrap
import types
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts import firestore_query_shapes as export_mod
from tests.support.firestore_index_rules import required_index
from tests.support.firestore_query_driver_registry import COVERED_BY, DRIVERS, SKIPS
from tests.support.firestore_query_drivers import (
    FROZEN_NOW,
    DriverEntry,
    DriverResult,
    _FrozenDate,
    _FrozenDateTime,
    calling_key,
    discover_query_functions,
    function_body_digest,
    run_driver,
)
from tests.support.firestore_shape_recorder import RecordingFirestore, install_recorder

import database.conversations

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ROOT = BACKEND_ROOT / 'database'
LEDGER_PATH = BACKEND_ROOT / 'tests' / 'support' / 'firestore_query_known_gaps.json'
MANIFEST_PATH = BACKEND_ROOT.parent / 'firestore.indexes.json'


@pytest.fixture(scope='module')
def two_captures() -> tuple[dict[str, DriverResult], dict[str, DriverResult]]:
    """Two independently fresh captures, prepared once for the module."""
    return export_mod.run_drivers(), export_mod.run_drivers()


@pytest.fixture(scope='module')
def driver_results(two_captures) -> dict[str, DriverResult]:
    return two_captures[0]


@pytest.fixture(scope='module')
def export_pair(two_captures) -> tuple[str, str]:
    manifest = export_mod.load_manifest(MANIFEST_PATH)
    first = export_mod.build_export(two_captures[0], manifest)
    second = export_mod.build_export(two_captures[1], manifest)
    return json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)


@pytest.fixture(scope='module')
def export_payload(driver_results) -> dict:
    manifest = export_mod.load_manifest(MANIFEST_PATH)
    return export_mod.build_export(driver_results, manifest)


@pytest.fixture(scope='module')
def ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text())


def _fake_module(monkeypatch: pytest.MonkeyPatch, name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _entry(
    entry_id: str,
    *,
    served: bool,
    uncertain: bool = False,
    required: dict | None = None,
    reason: str = '',
    signature: dict | None = None,
) -> dict:
    candidate = {'collectionGroup': 'c', 'queryScope': 'COLLECTION', 'fields': [], 'composite': True}
    sig = signature if signature is not None else {'collection_group': 'c'}
    return {
        'id': entry_id,
        'signature': sig,
        'candidate_index': candidate,
        'required_index': required,
        'served': served,
        'uncertain': uncertain,
        'reason': reason,
    }


def _real_count_verdict(manifest: dict) -> dict:
    """Run the real get_conversations_count and export the verdict of its count shape."""
    client = RecordingFirestore()
    with install_recorder(client):
        with client.recording_context('database.conversations.get_conversations_count', {}):
            database.conversations.get_conversations_count('shape-user', start_date=FROZEN_NOW)
    shape = client.shapes[0]
    assert shape.orders == ()
    required = required_index(shape)
    assert required is not None
    assert dict(required.fields)['created_at'] == 'ASCENDING'
    return export_mod.shape_verdict(shape, manifest)


@pytest.fixture(scope='module')
def discovered_keys() -> set[str]:
    return {row['key'] for row in discover_query_functions(DATABASE_ROOT)}


def test_registry_covers_all_discovered_functions(discovered_keys):
    registry = set(DRIVERS) | set(COVERED_BY) | set(SKIPS)
    missing = sorted(discovered_keys - registry)
    extra = sorted(registry - discovered_keys)
    assert not missing, f'discovered querying functions without registry entries: {missing}'
    assert not extra, f'registry entries that are not discovered querying functions: {extra}'


def test_covered_by_references_resolve():
    for key, entry in COVERED_BY.items():
        assert entry.covered_by, f'{key}: covered_by list is empty'
        for driver in entry.covered_by:
            assert driver in DRIVERS, f'{key}: covering driver {driver} is not a DriverEntry'


def test_registry_domains_and_neutral_reasons_well_formed():
    for key, entry in DRIVERS.items():
        for name, values in entry.domains.items():
            assert values, f'{key}: domain {name} is empty'
        for name, spec in entry.neutrals.items():
            assert (
                isinstance(spec, tuple) and len(spec) == 2 and str(spec[1]).strip()
            ), f'{key}: neutral {name} lacks a reason'


def test_registry_sections_are_disjoint():
    assert not (set(DRIVERS) & set(COVERED_BY))
    assert not (set(DRIVERS) & set(SKIPS))
    assert not (set(COVERED_BY) & set(SKIPS))


def _discover(tmp_path: Path, sources: dict[str, str]) -> dict[str, dict]:
    for filename, source in sources.items():
        (tmp_path / filename).write_text(textwrap.dedent(source))
    return {row['key']: row for row in discover_query_functions(tmp_path)}


def test_sentinel_flags_query_reassigned_in_if_branch(tmp_path):
    rows = _discover(
        tmp_path,
        {'mod.py': """
                def listing(db, flag):
                    query = db.collection('c')
                    if flag:
                        query = query.where(field='f', op='==', value=1)
                    return list(query.stream())
            """},
    )
    assert any(key.endswith('.mod.listing') for key in rows)


def test_sentinel_flags_nested_function_queries(tmp_path):
    rows = _discover(
        tmp_path,
        {'mod.py': """
                def outer(db):
                    def inner(query):
                        return query.stream()
                    return inner(db.collection('c'))
            """},
    )
    assert any(key.endswith('.mod.outer') for key in rows)


def test_sentinel_flags_builder_and_terminal_pair(tmp_path):
    rows = _discover(
        tmp_path,
        {'mod.py': """
                def _build(db, marker):
                    return db.collection('c').where(field='f', op='==', value=marker)

                def get_page(db, marker):
                    return _build(db, marker).get()
            """},
    )
    assert any(key.endswith('.mod._build') for key in rows)
    assert any(key.endswith('.mod.get_page') for key in rows)


def test_sentinel_excludes_document_getters(tmp_path):
    rows = _discover(
        tmp_path,
        {'mod.py': """
                def get_doc(ref):
                    return ref.get()

                def get_snapshot(document):
                    return document.get()
            """},
    )
    assert not any(key.endswith('.mod.get_doc') for key in rows)
    assert not any(key.endswith('.mod.get_snapshot') for key in rows)


@pytest.mark.parametrize('driver_key', sorted(DRIVERS))
def test_driver_has_no_errors(driver_results, driver_key):
    result = driver_results[driver_key]
    assert not result.errors, '; '.join(f'{e.combo} -> {e.error}' for e in result.errors[:3])
    assert result.shapes, f'{driver_key} recorded no query shapes'


def test_no_unexpected_callers(driver_results):
    registry = set(DRIVERS) | set(COVERED_BY) | set(SKIPS)
    unexpected = sorted(
        {
            shape.calling_function
            for result in driver_results.values()
            for shape in result.shapes
            if calling_key(shape.calling_function) not in registry
        }
    )
    assert not unexpected, f'runtime callers missing registry entries: {unexpected}'


def test_covered_by_helpers_observed_in_named_driver(driver_results):
    """Each observable helper must record inside at least one named covered_by driver."""
    missing = []
    for key, entry in COVERED_BY.items():
        if not entry.expect_observed:
            continue
        observed = any(
            calling_key(shape.calling_function) == calling_key(key)
            for driver in entry.covered_by
            for shape in driver_results[driver].shapes
        )
        if not observed:
            missing.append(key)
    assert not missing, f'covered-by helpers not observed in any named covering driver: {missing}'


def test_digest_pinned_entries_unchanged():
    """Reviewed bodies of non-observed covered-by helpers and skips are digest-pinned."""
    bad = []
    for key, entry in COVERED_BY.items():
        if entry.expect_observed:
            continue
        if not entry.body_digest:
            bad.append(f'{key}: expect_observed=False without a body digest')
        elif entry.body_digest != function_body_digest(key):
            bad.append(f'{key}: body changed since review — re-review coverage')
    for key, entry in SKIPS.items():
        if entry.body_digest is None:
            bad.append(f'{key}: skip without a body digest')
        elif entry.body_digest != function_body_digest(key):
            bad.append(f'{key}: body changed since skip review — re-review the skip')
    assert not bad, '; '.join(bad)


def _mutating_driver_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    module = _fake_module(monkeypatch, 'driver_fixtures_mutating')

    def mutating(payload, flag, client):
        payload['items'].append(flag)
        payload['depth']['n'] += 1
        return list(client.collection('iso_a').stream())

    def seeding(client):
        client.documents['users/u/private/1'] = {'secret': 1}
        return list(client.collection('iso_b').stream())

    def probing(client):
        snap = client.document('users/u/private/1').get()
        module.seen.append(snap.to_dict())
        return list(client.collection('iso_c').stream())

    def wasteful(client):
        client.queue_results([client.snapshot('users/u/c/1', {'x': 1})])
        client.queue_results([client.snapshot('users/u/c/2', {'x': 2})])
        return list(client.collection('iso_d').stream())

    def networky(client):
        try:
            socket.socket().connect_ex(('127.0.0.1', 6379))
        except Exception:
            pass
        return list(client.collection('iso_e').stream())

    module.mutating = mutating
    module.seeding = seeding
    module.probing = probing
    module.wasteful = wasteful
    module.networky = networky
    module.seen = []
    return module


def test_driver_deep_copies_arguments_across_trials(monkeypatch):
    module = _mutating_driver_module(monkeypatch)
    entry = DriverEntry(
        'driver_fixtures_mutating.mutating',
        base={'payload': {'items': [], 'depth': {'n': 0}}},
        domains={'flag': [True, False]},
        trials=2,
    )
    first = run_driver(entry)
    assert not first.errors
    assert entry.base['payload'] == {'items': [], 'depth': {'n': 0}}, 'registry base was mutated'
    second = run_driver(entry)
    assert not second.errors
    assert [s.signature() for s in first.shapes] == [s.signature() for s in second.shapes]


def test_registry_body_digests_are_frozen_literals():
    """BODY_DIGEST must be a literal dict matching every digest-pinned entry."""
    registry_path = BACKEND_ROOT / 'tests' / 'support' / 'firestore_query_driver_registry.py'
    tree = ast.parse(registry_path.read_text())
    digest_node = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'BODY_DIGEST' for target in node.targets)
    )
    assert isinstance(digest_node, ast.Dict), 'BODY_DIGEST must be a literal dict'
    pinned = ast.literal_eval(digest_node)
    expected = {key: entry.body_digest for key, entry in {**COVERED_BY, **SKIPS}.items() if entry.body_digest}
    assert pinned == expected


def test_function_body_digest_tracks_signature_and_body(tmp_path):
    mod = tmp_path / 'mod.py'
    mod.write_text('def read(flag=False):\n    return []\n')
    original = function_body_digest('database.mod.read', tmp_path)
    mod.write_text('def read(flag=False):\n    return [1]\n')
    assert function_body_digest('database.mod.read', tmp_path) != original
    mod.write_text('def read(flag=True):\n    return []\n')
    assert function_body_digest('database.mod.read', tmp_path) != original


def test_drivers_do_not_share_seeded_documents(monkeypatch):
    module = _mutating_driver_module(monkeypatch)
    results = {
        'a': run_driver(DriverEntry('driver_fixtures_mutating.seeding')),
        'b': run_driver(DriverEntry('driver_fixtures_mutating.probing')),
    }
    assert not results['a'].errors and not results['b'].errors
    assert module.seen == [None], 'probe driver saw a document seeded by another driver'


def test_leftover_queued_responses_fail(monkeypatch):
    _mutating_driver_module(monkeypatch)
    result = run_driver(DriverEntry('driver_fixtures_mutating.wasteful'))
    assert any('leftover queued responses' in error.error for error in result.errors)


def test_frozen_clock_preserves_native_isinstance():
    native_dt = datetime(2020, 5, 4, 3, 2, 1)
    native_d = date(2020, 5, 4)
    assert isinstance(native_dt, _FrozenDateTime)
    assert isinstance(native_dt, _FrozenDate)
    assert isinstance(native_d, _FrozenDate)
    assert not isinstance(native_d, _FrozenDateTime)
    assert _FrozenDateTime.now(tz=timezone.utc) == FROZEN_NOW
    assert _FrozenDateTime.utcnow() == FROZEN_NOW.replace(tzinfo=None)
    assert _FrozenDate.today().isoformat() == FROZEN_NOW.date().isoformat()
    coerced = datetime.fromisoformat(FROZEN_NOW.isoformat())
    assert coerced == FROZEN_NOW


def test_no_socket_attempts_in_driver_run():
    """A cache-wrapped driver must run without any socket connect, loopback included."""
    registered = DRIVERS['database.apps.search_apps_db']
    entry = DriverEntry(
        registered.function,
        base=dict(registered.base),
        domains={
            'category': [None],
            'capability': [None],
            'my_apps': [False],
            'installed_apps': [False],
            'enabled_app_ids': [None],
        },
        patchers=registered.patchers,
    )
    result = run_driver(entry)
    assert not result.errors
    assert result.shapes


def test_swallowed_socket_attempt_still_fails(monkeypatch):
    """Serving code that catches the blocked connect still leaves a recorded attempt."""
    _mutating_driver_module(monkeypatch)
    result = run_driver(DriverEntry('driver_fixtures_mutating.networky'))
    assert result.shapes
    assert any('network connection attempt' in error.error for error in result.errors)


def test_ledger_is_well_formed(ledger):
    assert ledger['schema_version'] == 1
    ids = [row['id'] for row in ledger['known_gaps']] + [row['id'] for row in ledger['uncertain']]
    assert len(ids) == len(set(ids)), 'duplicate ids in the ledger'
    for row in ledger['known_gaps'] + ledger['uncertain']:
        assert set(row) >= {'id', 'shape', 'required_index'}
        assert row['shape']['collection_group']


def test_known_gaps_match_checked_in_ledger(export_payload, ledger):
    computed = export_mod.evaluate_shapes(export_payload['shapes'])
    sections = export_mod.compare_ledgers(computed, ledger)
    message = export_mod.format_guard_failure(sections)
    assert not message, message


def _sig_id(signature: dict) -> str:
    return export_mod._signature_id(signature)


def test_new_certain_gap_fails():
    computed = export_mod.evaluate_shapes([_entry('a1', served=False)])
    sections = export_mod.compare_ledgers(computed, {'schema_version': 1, 'known_gaps': [], 'uncertain': []})
    assert sections['new_gaps'] == ['a1']
    assert not sections['stale_gaps']


def test_stale_gap_fails():
    sig = {'collection_group': 'c'}
    computed = export_mod.evaluate_shapes([_entry('a1', served=True)])
    ledger = {
        'schema_version': 1,
        'known_gaps': [{'id': _sig_id(sig), 'shape': sig, 'required_index': {}}],
        'uncertain': [],
    }
    sections = export_mod.compare_ledgers(computed, ledger)
    assert sections['stale_gaps'] == [_sig_id(sig)]


def test_served_shape_with_ledger_gap_is_stale():
    gap = _entry('a1', served=False)
    assert export_mod.evaluate_shapes([gap])['known_gaps']
    served = dict(gap, served=True)
    assert not export_mod.evaluate_shapes([served])['known_gaps']


def test_changed_required_index_fails():
    sig = {'collection_group': 'c'}
    new = {'collectionGroup': 'c', 'queryScope': 'COLLECTION', 'fields': [{'fieldPath': 'b'}]}
    computed = export_mod.evaluate_shapes([_entry(_sig_id(sig), served=False, required=new, signature=sig)])
    ledger = {
        'schema_version': 1,
        'known_gaps': [{'id': _sig_id(sig), 'shape': sig, 'required_index': {'fields': [{'fieldPath': 'a'}]}}],
        'uncertain': [],
    }
    sections = export_mod.compare_ledgers(computed, ledger)
    assert sections['changed_required'] == [_sig_id(sig)]
    assert not sections['new_gaps']
    assert not sections['stale_gaps']
    assert not sections['invalid_ledger']


def test_tampered_stored_shape_fails():
    """A stored shape that does not hash to its own id is an invalid row."""
    sig = {'collection_group': 'c'}
    computed = export_mod.evaluate_shapes([_entry(_sig_id(sig), served=False, signature=sig)])
    ledger = {
        'schema_version': 1,
        'known_gaps': [{'id': _sig_id(sig), 'shape': {'collection_group': 'tampered'}, 'required_index': {}}],
        'uncertain': [],
    }
    sections = export_mod.compare_ledgers(computed, ledger)
    assert sections['invalid_ledger']
    assert sections['changed_shape'] == [_sig_id(sig)]


def test_duplicate_ledger_ids_fail():
    sig = {'collection_group': 'c'}
    row = {'id': _sig_id(sig), 'shape': sig, 'required_index': {}}
    ledger = {'schema_version': 1, 'known_gaps': [row, dict(row)], 'uncertain': []}
    sections = export_mod.compare_ledgers({'known_gaps': {}, 'uncertain': {}}, ledger)
    assert any('duplicate id' in problem for problem in sections['invalid_ledger'])


def test_id_in_both_ledger_sections_fails():
    sig = {'collection_group': 'c'}
    row = {'id': _sig_id(sig), 'shape': sig, 'required_index': {}}
    ledger = {
        'schema_version': 1,
        'known_gaps': [row],
        'uncertain': [dict(row, reason='or')],
    }
    sections = export_mod.compare_ledgers({'known_gaps': {}, 'uncertain': {}}, ledger)
    assert any('both ledger sections' in problem for problem in sections['invalid_ledger'])


def test_new_uncertainty_fails():
    sig = {'collection_group': 'c'}
    computed = export_mod.evaluate_shapes(
        [_entry(_sig_id(sig), served=False, uncertain=True, reason='or', signature=sig)]
    )
    sections = export_mod.compare_ledgers(computed, {'schema_version': 1, 'known_gaps': [], 'uncertain': []})
    assert sections['new_uncertain'] == [_sig_id(sig)]


def test_matching_uncertain_ledger_passes():
    sig = {'collection_group': 'c'}
    computed = export_mod.evaluate_shapes(
        [_entry(_sig_id(sig), served=False, uncertain=True, reason='or', signature=sig)]
    )
    ledger = export_mod.build_ledger(computed)
    sections = export_mod.compare_ledgers(computed, ledger)
    assert not export_mod.format_guard_failure(sections)


def test_changed_uncertain_metadata_fails():
    sig = {'collection_group': 'c'}
    computed = export_mod.evaluate_shapes(
        [_entry(_sig_id(sig), served=False, uncertain=True, reason='or-group', signature=sig)]
    )
    computed_row = computed['uncertain'][_sig_id(sig)]
    ledger = {
        'schema_version': 1,
        'known_gaps': [],
        'uncertain': [dict(computed_row, reason='different-reason')],
    }
    sections = export_mod.compare_ledgers(computed, ledger)
    assert sections['changed_uncertain'] == [_sig_id(sig)]
    assert not sections['changed_required']
    assert not sections['invalid_ledger']


def test_manifest_index_resolving_uncertainty_requires_pruning():
    sig = {'collection_group': 'c'}
    resolved = _entry(_sig_id(sig), served=True, uncertain=True, reason='or', signature=sig)
    computed = export_mod.evaluate_shapes([resolved])
    assert not computed['uncertain']
    ledger = {
        'schema_version': 1,
        'known_gaps': [],
        'uncertain': [{'id': _sig_id(sig), 'shape': sig, 'required_index': {}, 'reason': 'or'}],
    }
    sections = export_mod.compare_ledgers(computed, ledger)
    assert sections['stale_uncertain'] == [_sig_id(sig)]


def test_uncertain_but_served_is_not_ledger_debt():
    sig = {'collection_group': 'c'}
    computed = export_mod.evaluate_shapes([_entry(_sig_id(sig), served=True, uncertain=True, signature=sig)])
    assert computed == {'known_gaps': {}, 'uncertain': {}}


def test_real_shape_manifest_mutation():
    """Adding precisely the required index flips a real gap to stale."""
    unserved = _real_count_verdict({'indexes': []})
    assert not unserved['served']
    computed = export_mod.evaluate_shapes([unserved])
    ledger = export_mod.build_ledger(computed)
    assert not export_mod.format_guard_failure(export_mod.compare_ledgers(computed, ledger))

    required = unserved['required_index']
    assert required is not None
    served_manifest = {'indexes': [required]}
    served = _real_count_verdict(served_manifest)
    assert served['served']
    sections = export_mod.compare_ledgers(export_mod.evaluate_shapes([served]), ledger)
    assert sections['stale_gaps'] == [unserved['id']]

    tampered = copy.deepcopy(ledger)
    tampered['known_gaps'][0]['required_index'] = {'collectionGroup': 'other'}
    sections = export_mod.compare_ledgers(computed, tampered)
    assert sections['changed_required'] == [unserved['id']]


def test_export_schema_and_counts(export_payload):
    assert export_payload['schema_version'] == 1
    assert export_payload['counts']['drivers'] == len(DRIVERS)
    assert len(export_payload['drivers']) == len(DRIVERS)
    assert export_payload['shapes']
    for entry in export_payload['shapes'][:50]:
        assert set(entry) >= {
            'id',
            'signature',
            'shape',
            'driver_function',
            'parameter_combo',
            'candidate_index',
            'required_index',
            'served',
            'uncertain',
            'reason',
        }
        assert len(entry['id']) == 16


def test_export_is_deterministic(export_pair):
    assert export_pair[0] == export_pair[1]


def test_export_main_writes_exact_path(tmp_path, driver_results, monkeypatch, capsys):
    """Real ``main()`` path — argv, manifest, export build, exact-path write.

    The driver capture itself is supplied by the module fixture: a real subset
    feeds the CLI path so the test stays inside the fast-unit duration budget,
    while determinism of the full payload is checked by test_export_is_deterministic.
    """
    subset = dict(list(driver_results.items())[:3])
    monkeypatch.setattr(export_mod, 'run_drivers', lambda: subset)
    out = tmp_path / 'export.json'
    assert export_mod.main(['--export', str(out), '--manifest', str(MANIFEST_PATH)]) == 0
    payload = json.loads(out.read_text())
    assert payload['schema_version'] == 1
    expected = export_mod.build_export(subset, export_mod.load_manifest(MANIFEST_PATH))
    assert payload == expected
    out2 = tmp_path / 'export2.json'
    assert export_mod.main(['--export', str(out2), '--manifest', str(MANIFEST_PATH)]) == 0
    assert out.read_bytes() == out2.read_bytes()
    capsys.readouterr()
