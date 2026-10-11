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
- every recorded *serving* shape is covered by the checked-in manifest
  (zero-serving-debt guard — explicit ``serving=False`` profile rows are
  reported separately, never as debt), and
- the export artifact is deterministic and schema-stable.
"""

from __future__ import annotations

import ast
import inspect
import json
import socket
import sys
import textwrap
import types
from datetime import date, datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any

import pytest

import database.conversations
from scripts import firestore_query_shapes as export_mod
from tests.support.firestore_index_rules import is_served, required_index
from tests.support.firestore_caller_witnesses import (
    WITNESSES,
    matching_profile,
    witness_completeness_errors,
)
from tests.support.firestore_conversation_profiles import PROFILES, discover_conversation_callers
from tests.support.firestore_query_driver_registry import COVERED_BY, DRIVERS, SKIPS
from tests.support.firestore_outside_query_drivers import BODY_DIGEST as OUTSIDE_BODY_DIGEST
from tests.support.firestore_serving_query_inventory import (
    discover_serving_query_functions,
    serving_function_body_digest,
)
from tests.support.firestore_query_drivers import (
    FROZEN_NOW,
    CallerProfile,
    DriverEntry,
    DriverResult,
    _FrozenDate,
    _FrozenDateTime,
    calling_key,
    discover_query_functions,
    function_body_digest,
    run_driver,
)
from tests.support.firestore_shape_recorder import (
    QueryFilter,
    QueryShape,
    RecordingFirestore,
    install_recorder,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ROOT = BACKEND_ROOT / 'database'
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
        'serving': True,
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
    assert shape.orders == (('created_at', 'DESCENDING'),)
    required = required_index(shape)
    assert required is not None
    assert dict(required.fields)['created_at'] == 'DESCENDING'
    return export_mod.shape_verdict(shape, manifest)


@pytest.fixture(scope='module')
def discovered_keys() -> set[str]:
    return {row['key'] for row in discover_serving_query_functions(BACKEND_ROOT)}


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
        assert len({profile.name for profile in entry.profiles}) == len(entry.profiles)
        for profile in entry.profiles:
            assert profile.name
            assert not (profile.domains.keys() & (entry.base.keys() | entry.neutrals.keys() | entry.domains.keys()))
        for domains in [entry.domains, *(profile.domains for profile in entry.profiles)]:
            for name, values in domains.items():
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


@pytest.fixture(scope='module')
def pinned_entry_review_errors():
    bad = []
    for key, entry in COVERED_BY.items():
        if entry.expect_observed:
            continue
        if not entry.body_digest:
            bad.append(f'{key}: expect_observed=False without a body digest')
        elif entry.body_digest != serving_function_body_digest(key):
            bad.append(f'{key}: body changed since review — re-review coverage')
    for key, entry in SKIPS.items():
        if entry.body_digest is None:
            bad.append(f'{key}: skip without a body digest')
        elif entry.body_digest != serving_function_body_digest(key):
            bad.append(f'{key}: body changed since skip review — re-review the skip')
    return bad


@pytest.mark.slow
def test_digest_pinned_entries_unchanged(pinned_entry_review_errors):
    """Reviewed bodies of non-observed covered-by helpers and skips are digest-pinned."""
    assert not pinned_entry_review_errors, '; '.join(pinned_entry_review_errors)


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


def test_named_profiles_deep_copy_arguments_and_keep_export_provenance(monkeypatch):
    _mutating_driver_module(monkeypatch)
    entry = DriverEntry(
        'driver_fixtures_mutating.mutating',
        base={'payload': {'items': [], 'depth': {'n': 0}}},
        profiles=(CallerProfile('one', {'flag': [True]}), CallerProfile('two', {'flag': [False]})),
        trials=2,
    )
    first = run_driver(entry)
    second = run_driver(entry)
    assert not first.errors and not second.errors
    assert entry.base['payload'] == {'items': [], 'depth': {'n': 0}}
    assert [shape.to_dict() for shape in first.shapes] == [shape.to_dict() for shape in second.shapes]
    assert [shape.parameter_combo['caller_profile'] for shape in first.shapes] == ['one', 'one', 'two', 'two']
    assert all(shape.driver_function == entry.function for shape in first.shapes)


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
    assert pinned | OUTSIDE_BODY_DIGEST == expected


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


def test_export_has_zero_serving_debt(export_payload):
    """The whole recorded serving surface is covered by the checked-in manifest."""
    computed = export_mod.evaluate_shapes(export_payload['shapes'])
    message = export_mod.format_guard_failure(computed)
    assert not message, message


def _sig_id(signature: dict) -> str:
    return export_mod._signature_id(signature)


def test_new_certain_serving_gap_fails():
    computed = export_mod.evaluate_shapes([_entry('a1', served=False)])
    message = export_mod.format_guard_failure(computed)
    assert 'a1' in message
    assert 'UNSERVED serving shapes' in message


def test_serving_uncertain_row_fails():
    sig = {'collection_group': 'c'}
    computed = export_mod.evaluate_shapes(
        [_entry(_sig_id(sig), served=False, uncertain=True, reason='or', signature=sig)]
    )
    message = export_mod.format_guard_failure(computed)
    assert _sig_id(sig) in message
    assert 'UNRESOLVED uncertain' in message


def test_uncertain_and_certain_same_id_reports_certain():
    """A certain serving gap wins over an uncertain row sharing the stable id."""
    sig = {'collection_group': 'c'}
    certain = _entry('dup', served=False, signature=sig)
    uncertain = _entry('dup', served=False, uncertain=True, reason='r', signature=sig)
    for entries in ([certain, uncertain], [uncertain, certain]):
        computed = export_mod.evaluate_shapes(entries)
        assert 'dup' in computed['known_gaps']
        assert 'dup' not in computed['uncertain']


def test_nonserving_unserved_is_reported_not_debt():
    entry = dict(_entry('n1', served=False), serving=False)
    computed = export_mod.evaluate_shapes([entry])
    assert 'n1' in computed['nonserving']
    assert not export_mod.format_guard_failure(computed)
    assert 'n1' in export_mod.format_nonserving_rows(computed)


def test_nonserving_cannot_mask_serving_debt():
    """A serving row sharing an id with a non-serving row is still debt."""
    nonserving = dict(_entry('masked', served=False), serving=False)
    serving = _entry('masked', served=False)
    for entries in ([nonserving, serving], [serving, nonserving]):
        computed = export_mod.evaluate_shapes(entries)
        assert 'masked' in computed['known_gaps']
        assert 'masked' not in computed['nonserving']


def test_flipping_nonserving_row_to_serving_fails():
    """A non-serving row smuggled into the serving surface fails the guard."""
    entry = dict(_entry('flip', served=False), serving=False)
    assert not export_mod.format_guard_failure(export_mod.evaluate_shapes([entry]))
    flipped = dict(entry, serving=True)
    assert 'flip' in export_mod.format_guard_failure(export_mod.evaluate_shapes([flipped]))


def test_served_shapes_produce_no_debt():
    assert not export_mod.format_guard_failure(export_mod.evaluate_shapes([_entry('a1', served=True)]))


def test_uncertain_but_served_is_not_debt():
    sig = {'collection_group': 'c'}
    computed = export_mod.evaluate_shapes([_entry(_sig_id(sig), served=True, uncertain=True, signature=sig)])
    assert computed == {'known_gaps': {}, 'uncertain': {}, 'nonserving': {}}


def test_real_bounded_count_rejects_an_ascending_only_manifest():
    manifest = {
        'indexes': [
            {
                'collectionGroup': 'conversations',
                'queryScope': 'COLLECTION',
                'fields': [
                    {'fieldPath': field, 'order': 'ASCENDING'} for field in ('discarded', 'created_at', '__name__')
                ],
            }
        ],
    }
    assert not _real_count_verdict(manifest)['served']


def test_real_shape_manifest_mutation():
    """Removing the required index flips a real served shape to debt."""
    unserved = _real_count_verdict({'indexes': []})
    assert not unserved['served']
    message = export_mod.format_guard_failure(export_mod.evaluate_shapes([unserved]))
    assert unserved['id'] in message

    required = unserved['required_index']
    assert required is not None
    served = _real_count_verdict({'indexes': [required]})
    assert served['served']
    assert not export_mod.format_guard_failure(export_mod.evaluate_shapes([served]))


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
            'serving',
            'uncertain',
            'reason',
        }
        assert len(entry['id']) == 16


def test_export_is_deterministic(export_pair):
    assert export_pair[0] == export_pair[1]


def test_evaluate_shapes_served_duplicate_does_not_erase_unserved():
    """A served representative must not drop an unserved one sharing the stable id."""
    sig = {'collection_group': 'c'}
    gap = _entry('dup-certain', served=False, signature=sig)
    served = _entry('dup-certain', served=True, signature=sig)
    for entries in ([served, gap], [gap, served]):
        assert 'dup-certain' in export_mod.evaluate_shapes(entries)['known_gaps']
    uncertain_gap = _entry('dup-uncertain', served=False, uncertain=True, reason='r', signature=sig)
    served_uncertain = _entry('dup-uncertain', served=True, uncertain=True, reason='r', signature=sig)
    for entries in ([served_uncertain, uncertain_gap], [uncertain_gap, served_uncertain]):
        assert 'dup-uncertain' in export_mod.evaluate_shapes(entries)['uncertain']


def test_same_signature_singleton_and_multi_in_retain_refused_case():
    """Stable ids exclude in-list cardinality, but service now depends on it."""
    fields = lambda *prefix: [
        *[{'fieldPath': field, 'order': 'ASCENDING'} for field in prefix],
        {'fieldPath': 'created_at', 'order': 'ASCENDING'},
        {'fieldPath': '__name__', 'order': 'ASCENDING'},
    ]
    manifest = {
        'indexes': [
            {'collectionGroup': 'conversations', 'queryScope': 'COLLECTION', 'fields': fields('status', 'a')},
            {'collectionGroup': 'conversations', 'queryScope': 'COLLECTION', 'fields': fields('status', 'b')},
        ],
        'fieldOverrides': [],
    }

    def make(values):
        return QueryShape(
            collection_group='conversations',
            filters=(
                QueryFilter('a', '==', 1),
                QueryFilter('b', '==', 1),
                QueryFilter('status', 'in', values),
            ),
            orders=(('created_at', 'ASCENDING'),),
        )

    singleton = export_mod.shape_verdict(make([1]), manifest)
    multi = export_mod.shape_verdict(make([1, 2]), manifest)
    assert singleton['id'] == multi['id']
    assert singleton['served'] is True
    assert multi['served'] is False
    for entries in ([singleton, multi], [multi, singleton]):
        computed = export_mod.evaluate_shapes(entries)
        assert singleton['id'] in computed['uncertain']


@pytest.fixture(scope='module')
def conversation_caller_inventory():
    return discover_conversation_callers(BACKEND_ROOT)


def test_conversation_caller_profiles_are_complete(conversation_caller_inventory):
    """Discovered bindings must match the named runtime witnesses exactly."""
    errors = witness_completeness_errors(conversation_caller_inventory)
    assert not errors, '; '.join(errors)
    bound = set()
    for witness in WITNESSES.values():
        names = {profile.name for profile in PROFILES[witness.target]}
        assert witness.profiles and set(witness.profiles) <= names
        bound.update(witness.profiles)
    assert bound == {profile.name for profiles in PROFILES.values() for profile in profiles}


@pytest.mark.parametrize('change', ['new-caller', 'wrapper-reference', 'assigned-alias'])
def test_conversation_caller_sentinel_detects_new_references(tmp_path, change):
    """A new call site — direct, wrapped, or aliased — is a new discovered
    binding that completeness checking then flags as missing a witness."""
    path = tmp_path / 'consumer.py'
    path.write_text(
        'from database.conversations import get_conversations as listing\n' 'def read(uid):\n    return listing(uid)\n'
    )
    before = discover_conversation_callers(tmp_path)
    if change == 'new-caller':
        path.write_text(path.read_text() + '\ndef new_read(uid):\n    return listing(uid, starred=True)\n')
    elif change == 'wrapper-reference':
        path.write_text(path.read_text() + '\ndef wrapper(uid):\n    return run_blocking(pool, listing, uid)\n')
    else:
        path.write_text(path.read_text() + '\nalias = listing\ndef aliased(uid):\n    return alias(uid)\n')
    after = discover_conversation_callers(tmp_path)
    assert len(after) == len(before) + 1, (before, after)
    new_keys = set(after) - set(before)
    assert all(row['target'] == 'database.conversations.get_conversations' for row in after.values())
    errors = witness_completeness_errors(after, {})
    assert new_keys and all(any(key in error for error in errors) for key in new_keys)


@pytest.mark.parametrize(
    'widened',
    [
        {'categories': ['work']},
        {'date_field': 'started_at'},
        {'starred': True, 'include_discarded': True},
    ],
)
def test_widened_argument_domains_fail_runtime_profile_membership(widened):
    """A caller passing an argument outside every named profile's declared
    domain must fail the runtime capture guard."""
    signature = inspect.signature(database.conversations.get_conversations)
    bound = signature.bind('u1', **widened)
    bound.apply_defaults()
    names = (profile.name for profile in PROFILES['database.conversations.get_conversations'])
    assert matching_profile('database.conversations.get_conversations', dict(bound.arguments), tuple(names)) is None


def test_every_conversation_profile_is_exported_and_served(driver_results, export_payload):
    for target, profiles in PROFILES.items():
        result = driver_results[target]
        assert not result.errors
        assert {shape.parameter_combo['caller_profile'] for shape in result.shapes} == {p.name for p in profiles}
        exported = [row for row in export_payload['shapes'] if row['driver_function'] == target]
        assert exported and all(row['served'] for row in exported), target
        assert {row['parameter_combo']['caller_profile']['value'] for row in exported} == {p.name for p in profiles}
        for shape in result.shapes:
            combo = shape.parameter_combo
            if combo['caller_profile'].startswith('main-'):
                assert combo['categories'] is None
                assert not (len(combo.get('sources') or []) > 1 and len(combo.get('statuses') or []) > 1)
                if combo['caller_profile'].startswith('main-list'):
                    assert combo['statuses']


@pytest.mark.parametrize(
    'helper,status_sizes', [('get_conversations_count', [0, 1, 2]), ('get_conversations_without_photos', [1, 2])]
)
def test_main_conversation_profiles_preserve_the_entire_accepted_matrix(driver_results, helper, status_sizes):
    combos = [
        shape.parameter_combo
        for shape in driver_results[f'database.conversations.{helper}'].shapes
        if shape.parameter_combo['caller_profile'].startswith('main-')
    ]
    actual = {
        (
            combo['include_discarded'],
            len(combo['statuses'] or []),
            len(combo['sources'] or []),
            bool(combo['folder_id']),
            combo['starred'],
            bool(combo['start_date']),
            bool(combo['end_date']),
        )
        for combo in combos
    }
    expected = {
        values
        for values in product(
            [False, True], status_sizes, [0, 1, 2], [False, True], [None, False, True], [False, True], [False, True]
        )
        if not (values[1] > 1 and values[2] > 1)
    }
    assert actual == expected


@pytest.mark.parametrize('field', ['source', 'starred', 'folder_id'])
def test_shared_desc_indexes_have_necessary_singleton_count_witnesses(driver_results, field):
    manifest = export_mod.load_manifest(MANIFEST_PATH)
    witnesses = [
        shape
        for shape in driver_results['database.conversations.get_conversations_count'].shapes
        if shape.aggregations
        and shape.orders == (('created_at', 'DESCENDING'),)
        and {predicate.field for predicate in shape.filters} == {field, 'created_at'}
    ]
    assert witnesses, f'{field}: accepted dated count with this sole equality must be recorded'
    without = {
        **manifest,
        'indexes': [
            entry
            for entry in manifest['indexes']
            if not (
                entry['collectionGroup'] == 'conversations'
                and entry['queryScope'] == 'COLLECTION'
                and [item['fieldPath'] for item in entry['fields']] == [field, 'created_at', '__name__']
                and entry['fields'][1].get('order') == 'DESCENDING'
                and entry['fields'][2].get('order') == 'DESCENDING'
            )
        ],
    }
    assert all(is_served(shape, manifest) for shape in witnesses)
    assert all(not is_served(shape, without) for shape in witnesses)


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
