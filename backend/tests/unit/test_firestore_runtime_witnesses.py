"""Runtime witnesses for the candidate and memory query-helper call surfaces,
plus the vector-repair wiring sentinel.

The candidates route and memory service witnesses execute the real owning
functions with the query helper monkeypatched to capture signature-bound
arguments; every captured call must fit a named ``CallerProfile`` in the
driver registry. The vector-repair sentinel keeps the pending/expired outbox
queries explicitly non-serving: any new serving-code reference, entrypoint
registration, or deployment wiring fails until its shapes are declared and a
named serving driver exists.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import database.memories as memories_db
import database.task_recommendations as recommendation_db
import routers.candidates as candidates_router
import utils.memory.memory_service as memory_service
from database.candidates import CandidateStatus
from database.firestore_index_registry import firebase_index_manifest
from database.memory_vector_repair_outbox_worker import (
    VectorRepairOutboxWorkerTickConfig,
    run_vector_repair_outbox_worker_tick,
)
from tests.support.firestore_caller_witnesses import (
    CallerWitness,
    HelperCapture,
    install_capture,
    matching_profile_names,
    trial,
    witness_completeness_errors,
)
from tests.support.firestore_conversation_profiles import discover_callers
from tests.support.firestore_index_rules import is_served
from tests.support.firestore_query_driver_registry import DRIVERS
from tests.support.firestore_query_drivers import (
    CallerProfile,
    discover_target_references,
    discover_textual_registrations,
    run_driver,
)
from tests.support.firestore_shape_recorder import RecordingFirestore, install_recorder

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

QUERY_TARGETS = frozenset(
    {
        'database.candidates.list_candidates',
        'database.memories.get_memories',
        'database.memories.list_memory_updated_or_created_index',
    }
)

VECTOR_REPAIR_MODULE = 'database.memory_vector_repair_outbox_worker'
VECTOR_REPAIR_MODULE_PATH = 'database/memory_vector_repair_outbox_worker.py'
VECTOR_REPAIR_LEASE = f'{VECTOR_REPAIR_MODULE}.lease_vector_repair_purge_outbox_records'
VECTOR_REPAIR_TICK = f'{VECTOR_REPAIR_MODULE}.run_vector_repair_outbox_worker_tick'
VECTOR_REPAIR_TARGETS = frozenset({VECTOR_REPAIR_LEASE, VECTOR_REPAIR_TICK})
VECTOR_REPAIR_MODULES = frozenset({VECTOR_REPAIR_MODULE})
VECTOR_REPAIR_FIELDS = {'available_at', 'lease_expires_at'}
VECTOR_REPAIR_ALLOWED_BINDINGS = frozenset(
    {
        f'{VECTOR_REPAIR_MODULE_PATH}:run_vector_repair_outbox_worker_tick:{VECTOR_REPAIR_LEASE}',
    }
)

VECTOR_REPAIR_INVENTORIES = (
    REPO_ROOT / '.github' / 'workflows',
    BACKEND_ROOT / 'deploy',
    BACKEND_ROOT / 'charts',
    BACKEND_ROOT / 'runtime_images.json',
)
VECTOR_REPAIR_NEEDLES = ('memory_vector_repair_outbox_worker', 'vector_repair_outbox_worker_entrypoint')

# Driver captures depend only on the registered entry. Sentinel checks compare
# that same capture against several manifests, so retain the entry alongside
# its result to keep the cache valid across monkeypatched registry entries.
_DRIVER_RESULT_CACHE: dict[tuple[str, int], tuple[object, object]] = {}
_CURRENT_INDEX_MANIFEST = firebase_index_manifest()

_CANDIDATE_STATUSES = [None, *CandidateStatus]
_CANDIDATE_GENERATIONS = (0, 1)
_CANDIDATE_SURFACES = (None, 'suggested')


def _stub(monkeypatch: pytest.MonkeyPatch, owner: object, name: str, value: object) -> None:
    monkeypatch.setattr(owner, name, value, raising=False)


def _stub_candidates_deps(monkeypatch: pytest.MonkeyPatch, generation: int) -> None:
    _stub(
        monkeypatch,
        candidates_router,
        '_require_suggested_rollout',
        lambda uid: SimpleNamespace(account_generation=generation),
    )
    _stub(
        monkeypatch,
        recommendation_db,
        'list_active_override_dedupe_keys',
        lambda uid, now=None, account_generation=None: set(),
    )


def _run_candidates_route(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    for generation in _CANDIDATE_GENERATIONS:
        _stub_candidates_deps(monkeypatch, generation)
        for candidate_status in _CANDIDATE_STATUSES:
            for surface in _CANDIDATE_SURFACES:
                trial(
                    capture,
                    candidates_router.list_candidates,
                    candidate_status=candidate_status,
                    limit=10,
                    offset=0,
                    surface=surface,
                    uid='u1',
                )


def _run_legacy_read(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    trial(capture, memory_service._legacy_read_memories, 'u1', limit=50, offset=10)


def _run_historical_read(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    adapter = memory_service.HistoricalMemoryAdapter(db_client=object())
    trial(capture, adapter.read, 'u1', limit=10, hydrate=False)


def _run_internal_forward(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    trial(
        capture,
        memories_db.get_memories,
        'u1',
        sort='updated_or_created_desc',
        firestore_client=RecordingFirestore(),
    )


def _profiles(target: str):
    return DRIVERS[target].profiles


WITNESSES: dict[str, CallerWitness] = {
    witness.key: witness
    for witness in (
        CallerWitness(
            'routers/candidates.py:list_candidates:database.candidates.list_candidates',
            'database.candidates.list_candidates',
            'database.candidates.list_candidates',
            ('candidate-list', 'candidate-suggested'),
            2,
            _run_candidates_route,
        ),
        CallerWitness(
            'utils/memory/memory_service.py:_legacy_read_memories:database.memories.get_memories',
            'database.memories.get_memories',
            'database.memories.get_memories',
            ('legacy-scoring',),
            1,
            _run_legacy_read,
        ),
        CallerWitness(
            'utils/memory/memory_service.py:HistoricalMemoryAdapter.read:database.memories.list_memory_updated_or_created_index',
            'database.memories.list_memory_updated_or_created_index',
            'database.memories.list_memory_updated_or_created_index',
            ('historical-dual-window',),
            1,
            _run_historical_read,
        ),
        CallerWitness(
            'database/memories.py:get_memories:database.memories.list_memory_updated_or_created_index',
            'database.memories.list_memory_updated_or_created_index',
            'database.memories.list_memory_updated_or_created_index',
            ('historical-dual-window',),
            1,
            _run_internal_forward,
        ),
    )
}


def _profile_named(target: str, names: tuple[str, ...]):
    allowed = {profile.name: profile for profile in _profiles(target)}
    return tuple(allowed[name] for name in names)


def _serving_profiles_covering(target: str, fields: set[str], manifest: dict) -> set[str]:
    """Named serving profiles of ``target`` whose real captured shapes filter
    every required field AND are each proven served by ``manifest``."""
    entry = DRIVERS.get(target)
    if entry is None:
        return set()
    cache_key = (target, id(entry))
    cached = _DRIVER_RESULT_CACHE.get(cache_key)
    if cached is not None and cached[0] is entry:
        result = cached[1]
    else:
        result = run_driver(entry)
        _DRIVER_RESULT_CACHE[cache_key] = (entry, result)
    if result.errors:
        return set()
    covered = set()
    for profile in entry.profiles:
        if not profile.serving:
            continue
        shapes = [
            shape
            for shape in result.shapes
            if shape.parameter_combo.get('caller_profile') == profile.name
            and shape.serving
            and shape.calling_function == VECTOR_REPAIR_LEASE
        ]
        if (
            shapes
            and fields <= {filter_.field for shape in shapes for filter_ in shape.filters}
            and all(is_served(shape, manifest) for shape in shapes)
        ):
            covered.add(profile.name)
    return covered


@pytest.fixture(scope='module')
def discovered_query_callers():
    return discover_callers(BACKEND_ROOT, QUERY_TARGETS)


@pytest.fixture(scope='module')
def discovered_vector_repair_references():
    return discover_target_references(BACKEND_ROOT, VECTOR_REPAIR_TARGETS, modules=VECTOR_REPAIR_MODULES)


@pytest.fixture(scope='module')
def vector_repair_registrations():
    return discover_textual_registrations(VECTOR_REPAIR_INVENTORIES, VECTOR_REPAIR_NEEDLES)


def test_witnesses_cover_discovered_query_callers(discovered_query_callers):
    errors = witness_completeness_errors(discovered_query_callers, WITNESSES)
    assert not errors, '; '.join(errors)


@pytest.mark.parametrize('key', sorted(WITNESSES))
def test_named_witness_matches_runtime_call(key, monkeypatch):
    witness = WITNESSES[key]
    capture = install_capture(monkeypatch, witness)
    witness.run(monkeypatch, capture)
    assert capture.calls, f'{key}: recipe produced no helper call'
    profiles = _profile_named(witness.target, witness.profiles)
    bound = set()
    for call in capture.calls:
        names = matching_profile_names(profiles, call)
        assert names, f'{key}: bound args {call} fit no named profile in {witness.profiles}'
        bound.update(names)
    unexercised = set(witness.profiles) - bound
    assert not unexercised, f'{key}: named profiles never exercised by the real caller: {sorted(unexercised)}'


def test_candidates_surface_trials_match_expected_profiles(monkeypatch):
    witness = WITNESSES['routers/candidates.py:list_candidates:database.candidates.list_candidates']
    capture = install_capture(monkeypatch, witness)
    profiles = _profile_named(witness.target, witness.profiles)
    trials: list[tuple[str | None, CandidateStatus | None, int, dict]] = []
    for generation in _CANDIDATE_GENERATIONS:
        _stub_candidates_deps(monkeypatch, generation)
        for candidate_status in _CANDIDATE_STATUSES:
            for surface in _CANDIDATE_SURFACES:
                trial(
                    capture,
                    candidates_router.list_candidates,
                    candidate_status=candidate_status,
                    limit=10,
                    offset=0,
                    surface=surface,
                    uid='u1',
                )
                trials.append((surface, candidate_status, generation, capture.calls[-1]))
    assert len(trials) == len(_CANDIDATE_GENERATIONS) * len(_CANDIDATE_STATUSES) * len(_CANDIDATE_SURFACES)
    for surface, requested, generation, call in trials:
        names = matching_profile_names(profiles, call)
        if surface == 'suggested':
            assert call['status'] is None, f'suggested surface forwarded status {call["status"]}'
            assert 'candidate-suggested' in names
        else:
            expected = requested.value if isinstance(requested, CandidateStatus) else requested
            assert call['status'] == expected, f'normal surface dropped status {requested}: {call}'
            assert 'candidate-list' in names
        assert call['account_generation'] is not None and call['account_generation'] == generation


def test_suggested_profile_rejects_forwarded_status():
    profiles = _profile_named('database.candidates.list_candidates', ('candidate-suggested',))
    forwarded = {
        'uid': 'u1',
        'candidate_status': CandidateStatus.accepted,
        'status': 'accepted',
        'limit': 10,
        'offset': 0,
        'account_generation': 0,
    }
    names = matching_profile_names(profiles, forwarded)
    assert 'candidate-suggested' not in names, 'a status-forwarding suggested call must not fit the suggested profile'


def test_new_query_caller_fails_completeness(discovered_query_callers):
    mutated = dict(discovered_query_callers)
    mutated['utils/fake.py:new_reader:database.memories.get_memories'] = {
        'target': 'database.memories.get_memories',
        'references': 1,
    }
    assert witness_completeness_errors(mutated, WITNESSES)


def _vector_repair_wiring_errors(references: dict, registrations: dict, manifest: dict | None = None) -> list[str]:
    """Fail-closed: references outside the worker's own module, or any
    entrypoint/scheduler registration, require a named serving profile whose
    real captured shapes serve BOTH the pending (``available_at``) and expired
    (``lease_expires_at``) branches."""
    if manifest is None:
        manifest = _CURRENT_INDEX_MANIFEST
    new_wiring: list[str] = []
    for key in sorted(references):
        if key in VECTOR_REPAIR_ALLOWED_BINDINGS:
            continue
        new_wiring.append(f'{key}: new serving-code reference to a disabled vector-repair entrypoint')
    for path, needles in sorted(registrations.items()):
        new_wiring.append(f'{path}: registers the disabled vector-repair worker via {sorted(needles)}')
    if not new_wiring:
        return []
    coverage = _serving_profiles_covering(
        VECTOR_REPAIR_LEASE, VECTOR_REPAIR_FIELDS, manifest
    ) | _serving_profiles_covering(VECTOR_REPAIR_TICK, VECTOR_REPAIR_FIELDS, manifest)
    if coverage:
        return []
    return [
        *new_wiring,
        'new vector-repair wiring requires a named serving profile whose captured '
        'available_at and lease_expires_at shapes are served by the declared index manifest',
    ]


def test_vector_repair_worker_is_not_wired(discovered_vector_repair_references, vector_repair_registrations):
    assert not _vector_repair_wiring_errors(discovered_vector_repair_references, vector_repair_registrations)


def test_vector_repair_sentinel_flags_new_alias_reference(tmp_path):
    (tmp_path / 'consumer.py').write_text(
        'from database.memory_vector_repair_outbox_worker import lease_vector_repair_purge_outbox_records as lease\n'
        'def tick(uid):\n    return lease(uid, worker_id="w")\n'
    )
    references = discover_target_references(tmp_path, VECTOR_REPAIR_TARGETS, modules=VECTOR_REPAIR_MODULES)
    assert references
    assert _vector_repair_wiring_errors(references, {})


def test_vector_repair_sentinel_flags_wrapper_callback(tmp_path):
    (tmp_path / 'consumer.py').write_text(
        'import database.memory_vector_repair_outbox_worker as worker\n'
        'def tick(uid):\n    return worker.run_vector_repair_outbox_worker_tick(uid)\n'
    )
    references = discover_target_references(tmp_path, VECTOR_REPAIR_TARGETS, modules=VECTOR_REPAIR_MODULES)
    assert _vector_repair_wiring_errors(references, {})


def test_vector_repair_sentinel_flags_dict_registration(tmp_path):
    (tmp_path / 'consumer.py').write_text(
        'from database.memory_vector_repair_outbox_worker import run_vector_repair_outbox_worker_tick\n'
        'JOBS = {"vector_repair": run_vector_repair_outbox_worker_tick}\n'
    )
    references = discover_target_references(tmp_path, VECTOR_REPAIR_TARGETS, modules=VECTOR_REPAIR_MODULES)
    assert _vector_repair_wiring_errors(references, {})


def test_vector_repair_sentinel_flags_getattr_registration(tmp_path):
    (tmp_path / 'consumer.py').write_text(
        'import database.memory_vector_repair_outbox_worker as worker\n'
        'JOB = getattr(worker, "run_vector_repair_outbox_worker_tick")\n'
    )
    references = discover_target_references(tmp_path, VECTOR_REPAIR_TARGETS, modules=VECTOR_REPAIR_MODULES)
    assert _vector_repair_wiring_errors(references, {})


def test_vector_repair_sentinel_flags_textual_schedule(tmp_path):
    schedule = tmp_path / 'workflow.yml'
    schedule.write_text('jobs:\n  repair:\n    run: python -m scripts.vector_repair_outbox_worker_entrypoint\n')
    registrations = discover_textual_registrations([schedule], VECTOR_REPAIR_NEEDLES)
    assert _vector_repair_wiring_errors({}, registrations)


def test_vector_repair_sentinel_internal_reference_allowed(discovered_vector_repair_references):
    assert (
        set(discovered_vector_repair_references) <= VECTOR_REPAIR_ALLOWED_BINDINGS
    ), discovered_vector_repair_references
    assert VECTOR_REPAIR_ALLOWED_BINDINGS <= set(discovered_vector_repair_references)


@pytest.mark.parametrize(
    'owner',
    ['register_worker', '<module>'],
)
def test_vector_repair_sentinel_flags_same_module_tick_registration(owner):
    """A new register/schedule reference to the tick INSIDE the worker module is
    still new wiring: only the existing tick→lease call seam is allowed."""
    key = f'{VECTOR_REPAIR_MODULE_PATH}:{owner}:{VECTOR_REPAIR_TICK}'
    references = {key: {'target': VECTOR_REPAIR_TICK, 'references': 1}}
    assert _vector_repair_wiring_errors(references, {})


def _vector_repair_manifest(*, pending: bool = True, expired: bool = True) -> dict:
    def index(fields: tuple[str, ...]) -> dict:
        return {
            'collectionGroup': 'memory_outbox',
            'queryScope': 'COLLECTION',
            'fields': [
                *[{'fieldPath': field, 'order': 'ASCENDING'} for field in fields],
                {'fieldPath': '__name__', 'order': 'ASCENDING'},
            ],
        }

    indexes = []
    if pending:
        indexes.append(index(('event_type', 'status', 'available_at')))
    if expired:
        indexes.append(index(('event_type', 'status', 'lease_expires_at')))
    return {'indexes': indexes, 'fieldOverrides': []}


def _flip_lease_profiles_serving(monkeypatch, serving: bool) -> None:
    entry = DRIVERS[VECTOR_REPAIR_LEASE]
    flipped = replace(entry, profiles=tuple(replace(profile, serving=serving) for profile in entry.profiles))
    monkeypatch.setitem(DRIVERS, VECTOR_REPAIR_LEASE, flipped)


_NEW_WIRING = {'x.py:f:lease': {'target': VECTOR_REPAIR_LEASE, 'references': 1}}


def test_vector_repair_sentinel_unrelated_fake_profile_never_bypasses(monkeypatch):
    profile = CallerProfile('wired-vector-repair', {field: ['x'] for field in VECTOR_REPAIR_FIELDS}, serving=True)
    monkeypatch.setitem(DRIVERS, 'fake.entry', SimpleNamespace(profiles=(profile,)))
    assert _serving_profiles_covering(VECTOR_REPAIR_LEASE, VECTOR_REPAIR_FIELDS, _vector_repair_manifest()) == set()
    assert _vector_repair_wiring_errors(_NEW_WIRING, {}, _vector_repair_manifest())


def test_vector_repair_sentinel_serving_flip_still_blocked_on_current_manifest(monkeypatch):
    _flip_lease_profiles_serving(monkeypatch, True)
    assert _vector_repair_wiring_errors(_NEW_WIRING, {})


def test_vector_repair_sentinel_accepts_wiring_only_with_both_served_branches(monkeypatch):
    _flip_lease_profiles_serving(monkeypatch, True)
    assert _vector_repair_wiring_errors(_NEW_WIRING, {}, _vector_repair_manifest()) == []
    assert _vector_repair_wiring_errors(_NEW_WIRING, {}, _vector_repair_manifest(pending=False))
    assert _vector_repair_wiring_errors(_NEW_WIRING, {}, _vector_repair_manifest(expired=False))


def test_vector_repair_sentinel_nonserving_profiles_block_even_with_indexes(monkeypatch):
    _flip_lease_profiles_serving(monkeypatch, False)
    assert _vector_repair_wiring_errors(_NEW_WIRING, {}, _vector_repair_manifest())


def test_disabled_vector_repair_tick_emits_no_queries():
    client = RecordingFirestore()
    with install_recorder(client):
        run_vector_repair_outbox_worker_tick(
            db_client=client,
            uid='u1',
            config=VectorRepairOutboxWorkerTickConfig(enabled=False, worker_id='worker-1'),
            authoritative_item_loader=lambda item: None,
            vector_deleter=lambda item: None,
            vector_repairer=lambda item, result: None,
        )
    assert client.shapes == []


def test_vector_repair_nonserving_profiles_retain_both_query_branches():
    result = run_driver(DRIVERS[VECTOR_REPAIR_LEASE])
    fields = {filter_.field for shape in result.shapes for filter_ in shape.filters}
    assert 'available_at' in fields
    assert 'lease_expires_at' in fields
    assert result.shapes and all(shape.serving is False for shape in result.shapes)
