"""Dual-backend contract for the macOS Beta break-glass (ADR-0044 facade + ADR-0002 store port).

`database/desktop_beta_breakglass.py` is the incident lever: when the build Beta testers are running is
broken, it moves the ``macos-beta`` pointer off it — backwards to a previously shipped manifest
(rollback) or forwards to an unqualified emergency build (rollout) — and in the SAME commit closes the
admission gate and writes an audit record. One shape carries all of it:

    transaction   `_commit` reads FOUR documents before it writes any: the admission control, the Beta
                  pointer, the audit record for this request, and the target manifest. Then, atomically,
                  it creates the audit, optionally creates the emergency manifest, pauses admission and
                  sets the pointer.

What the wrong translation costs a user, per read:

*The pointer read* is a compare-and-swap on ``release_id`` and ``generation``. Break-glass runs when
several people are already reacting to the same incident, so two operators firing off the same view is
the expected case, not the exotic one. If the loser is not refused, the last write wins and the pointer
can land back on the build everybody is trying to get users OFF — or on a third build nobody decided
on. The generation is what catches the ABA case where the pointer moved away and back, so the release
id alone looks untouched.

*The audit read* is replay protection keyed by the GitHub Actions attempt URL. A re-run of a
break-glass workflow (the natural reflex when a job's response is lost) must not apply a second time
and must not fabricate a second audit row for one human decision. The audit is also the only record of
which binary was pushed under emergency authority — a rollout that commits the pointer without the
audit is an unattributable forced update.

*The admission read + the pause* are the interlock. Break-glass without the pause is a break-glass that
stays open: the Beta pipeline promotes the next candidate minutes later and users are shipped a wrong
binary again, on top of an active incident. The pause is written in the same transaction as the pointer
and bumps ``control_generation`` so any admission already in flight loses its compare-and-swap too.

*The target-manifest read* is what keeps the emergency channel honest: a rollback may only land on a
build with real evidence (never on another emergency artifact), an emergency rollout must carry
``qualification_tier: emergency`` with ``qualification_passed: False`` — the recorded truth that this
build did not qualify — and it must have a HIGHER build number, because a Sparkle client will not
install a downgrade and users would be stranded on the broken build with the incident marked handled.

Shapes NOT covered: none. `transaction` is the only at-risk shape the guard counts in this module.

Isolation: ``macos-beta`` and ``desktop_beta_admission/control`` are SINGLETON documents with fixed ids
— the module hard-codes them — so isolation comes from clearing exactly those paths before and after
each test, never the collections. Release manifests and audit records use run-unique ids. **This suite
must not run concurrently with `test_desktop_update_channels_contract.py`**, which drives the same two
singletons.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest

CHANNELS = 'desktop_update_channels'
MANIFESTS = 'desktop_release_manifests'
AUDITS = 'desktop_beta_breakglass_audits'
ADMISSION = 'desktop_beta_admission/control'
BETA = f'{CHANNELS}/macos-beta'

_SLOTS = range(8)


def _release_id(series: int, slot: int) -> str:
    return f'v0.{series}.{slot}+{series * 100 + slot}-macos'


def _manifest(series: int, slot: int, *, tier: str = 'signed-smoke', **overrides):
    """A canonical v1 release manifest for one run-unique build.

    The evidence asset is pinned per tier by `desktop_release_manifest.validate_manifest`, so a manifest
    can only be built for the evidence class it claims — including ``emergency``, whose recorded truth
    is ``qualification_passed: False``.
    """
    release_id = _release_id(series, slot)
    evidence = {
        'T2': (f'qualification-evidence-{release_id}.json', True),
        'signed-smoke': ('desktop-smoke-result-beta.json', False),
        'emergency': ('desktop-smoke-result.json', False),
    }[tier]
    version = f'0.{series}.{slot}'
    build = series * 100 + slot
    manifest = {
        'schema_version': 1,
        'release_id': release_id,
        'platform': 'macos',
        'version': version,
        'build_number': build,
        'app_source_sha': (uuid.uuid4().hex + uuid.uuid4().hex)[:40],
        'zip_url': f'https://github.com/BasedHardware/omi/releases/download/{release_id}/Omi.zip',
        'zip_sha256': 'sha256:' + 'b' * 64,
        'dmg_url': f'https://github.com/BasedHardware/omi/releases/download/{release_id}/omi.dmg',
        'dmg_sha256': 'sha256:' + 'c' * 64,
        'ed_signature': 'sparkle-signature',
        'qualification_evidence_asset': evidence[0],
        'qualification_evidence_sha256': 'sha256:' + 'd' * 64,
        'qualification_tier': tier,
        'qualification_passed': evidence[1],
        'backend_mode': 'app_only',
        'compatibility_contract': {
            'schema_version': 1,
            'app_release_id': release_id,
            'app_version': version,
            'app_build_number': build,
            'backend_mode': 'app_only',
            'environment_contract_version': 'desktop-backend-env-v1',
        },
        'environment_contract_version': 'desktop-backend-env-v1',
        'created_at': '2026-08-18T09:00:00Z',
        'published_at': '2026-08-18T09:00:00Z',
        'changelog': ['Contract run'],
        'mandatory': False,
    }
    manifest.update(overrides)
    return manifest


def _digest(manifest: dict) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return 'sha256:' + hashlib.sha256(canonical).hexdigest()


@pytest.fixture
def breakglass(bind_store):
    """A run-unique release series, with the two singleton documents cleared either side."""
    run = uuid.uuid4().hex[:8]
    series = int(run[:4], 16)
    audits: list[str] = []
    singletons = (BETA, ADMISSION)

    for path in singletons:
        bind_store.delete(path)

    yield {'run': run, 'series': series, 'store': bind_store, 'audits': audits}

    for path in singletons:
        bind_store.delete(path)
    for slot in _SLOTS:
        bind_store.delete(f'{MANIFESTS}/{_release_id(series, slot)}')
    for audit_id in audits:
        bind_store.delete(f'{AUDITS}/{audit_id}')


def _doc(breakglass, path: str):
    stored = breakglass['store'].get(path)
    return stored.data if stored is not None and stored.exists else None


def _request(breakglass, *, current: int, target: int, generation: int, attempt: int = 1, **overrides):
    """One signed break-glass request, with its audit id recorded for teardown.

    ``request_id`` is the GitHub Actions attempt URL and is hashed into the audit document id — it IS
    the replay key, so it stays run-unique unless a test deliberately replays it.
    """
    series = breakglass['series']
    run_number = int(breakglass['run'][:6], 16) + 1
    request = {
        'current_release_id': _release_id(series, current),
        'target_release_id': _release_id(series, target),
        'expected_generation': generation,
        'actor': 'release-oncall',
        'reason': 'beta build crashes on launch for every tester',
        'incident_url': 'https://github.com/BasedHardware/omi/issues/12345',
        'request_id': f'https://github.com/BasedHardware/omi/actions/runs/{run_number}/attempts/{attempt}',
        'normal_path_unavailable': 'the beta promotion workflow cannot run during the incident',
    }
    request.update(overrides)
    breakglass['audits'].append(hashlib.sha256(request['request_id'].encode()).hexdigest())
    return request


def _beta_running(breakglass, slot: int):
    """Put Beta on a normally-admitted build with the admission gate OPEN, as before an incident.

    Driven through the real admission path rather than seeded, because the state break-glass has to
    interact with — an open gate at a known ``control_generation``, a pointer at generation 1 — is
    produced by that path and nothing else.
    """
    import database.desktop_update_channels as channels_db

    manifest = _manifest(breakglass['series'], slot)
    channels_db.reserve_beta_candidate(manifest['release_id'])
    generation = channels_db.set_beta_admission_enabled(True)['control_generation']
    channels_db.admit_qualified_beta_manifest(manifest, control_generation=generation)
    return manifest


def _register(breakglass, slot: int, *, tier: str = 'signed-smoke'):
    import database.desktop_update_channels as channels_db

    manifest = _manifest(breakglass['series'], slot, tier=tier)
    channels_db.register_release_manifest(manifest)
    return manifest


# --- transaction: rollback --------------------------------------------------------------------------


def test_a_rollback_moves_beta_back_closes_the_gate_and_records_who_did_it(breakglass):
    """One commit, four documents. The pointer moves to the previous build, admission is paused, and the
    audit names the actor, the incident and the exact manifest digest that was pushed. Any one of those
    landing without the others is either an unattributable forced update or a gate left open."""
    import database.desktop_beta_breakglass as breakglass_db

    broken = _beta_running(breakglass, 3)
    good = _register(breakglass, 1)
    request = _request(breakglass, current=3, target=1, generation=1)

    result = breakglass_db.rollback_beta(request)

    assert result['pointer']['release_id'] == good['release_id']
    assert result['pointer']['generation'] == 2
    assert _doc(breakglass, BETA)['release_id'] == good['release_id']
    assert _doc(breakglass, BETA)['build_number'] == good['build_number'] < broken['build_number']

    control = _doc(breakglass, ADMISSION)
    assert control['promotion_enabled'] is False, 'the gate must close in the same commit'
    assert control['control_generation'] == 3, 'and bump, so an admission in flight loses its CAS'

    audit = _doc(breakglass, f"{AUDITS}/{breakglass['audits'][0]}")
    assert audit['operation'] == 'rollback'
    assert audit['actor'] == 'release-oncall'
    assert audit['incident_url'] == request['incident_url']
    assert audit['target_manifest_sha256'] == _digest(good), 'the audit pins WHICH binary was pushed'
    assert audit['resulting_generation'] == 2


def test_the_gate_stays_closed_until_a_human_reopens_it(breakglass):
    """The interlock, asserted through the pipeline that would otherwise undo the rollback. Without the
    pause committed atomically with the pointer, the next Beta candidate is admitted minutes later and
    users are shipped a wrong binary again on top of a live incident."""
    import database.desktop_beta_breakglass as breakglass_db
    import database.desktop_update_channels as channels_db

    _beta_running(breakglass, 3)
    good = _register(breakglass, 1)
    breakglass_db.rollback_beta(_request(breakglass, current=3, target=1, generation=1))

    next_candidate = _manifest(breakglass['series'], 4)
    channels_db.reserve_beta_candidate(next_candidate['release_id'])

    with pytest.raises(ValueError, match='beta admission is disabled'):
        channels_db.admit_qualified_beta_manifest(next_candidate, control_generation=4)

    assert _doc(breakglass, BETA)['release_id'] == good['release_id'], 'the rolled-back build stays'


def test_a_replayed_break_glass_request_is_refused_and_changes_nothing(breakglass):
    """The audit read. Re-running the workflow is the reflex when a response is lost; the attempt URL is
    the replay key, so the second run must be refused before any write and must not add a second audit
    row for one human decision."""
    import database.desktop_beta_breakglass as breakglass_db

    _beta_running(breakglass, 3)
    good = _register(breakglass, 1)
    request = _request(breakglass, current=3, target=1, generation=1)
    breakglass_db.rollback_beta(request)
    control_before = _doc(breakglass, ADMISSION)['control_generation']

    with pytest.raises(ValueError, match='request was already used'):
        breakglass_db.rollback_beta(request)

    assert _doc(breakglass, BETA)['release_id'] == good['release_id']
    assert _doc(breakglass, BETA)['generation'] == 2, 'a replay must not move the pointer again'
    assert _doc(breakglass, ADMISSION)['control_generation'] == control_before


def test_a_second_operator_firing_off_the_same_view_is_refused_and_the_first_rollback_survives(breakglass):
    """Two responders to one incident, both holding the pre-incident pointer. Exactly one may win: if
    the loser is not refused, the pointer ends up on whichever write landed last, which can be a build
    nobody chose — while the incident is being reported as handled."""
    import database.desktop_beta_breakglass as breakglass_db

    _beta_running(breakglass, 3)
    first_target = _register(breakglass, 1)
    _register(breakglass, 2)
    breakglass_db.rollback_beta(_request(breakglass, current=3, target=1, generation=1))

    loser = _request(breakglass, current=3, target=2, generation=1, attempt=2)
    with pytest.raises(ValueError, match='current release mismatch'):
        breakglass_db.rollback_beta(loser)

    assert _doc(breakglass, BETA)['release_id'] == first_target['release_id']
    assert _doc(breakglass, BETA)['generation'] == 2
    assert _doc(breakglass, f"{AUDITS}/{breakglass['audits'][1]}") is None, 'a refused request leaves no audit'


def test_the_generation_catches_a_pointer_that_moved_away_and_back(breakglass):
    """ABA — what the release-id check alone cannot see.

    An operator reads (build 3, generation 1). While they prepare, the pointer is rolled back to 1 and
    then forward to 3 again by someone else. The release id matches their view, so identity alone would
    let them apply a decision that a later one already superseded. Only the generation refuses.
    """
    import database.desktop_beta_breakglass as breakglass_db

    running = _beta_running(breakglass, 3)
    _register(breakglass, 1)
    _register(breakglass, 2)
    breakglass_db.rollback_beta(_request(breakglass, current=3, target=1, generation=1))
    breakglass_db.rollback_beta(_request(breakglass, current=1, target=3, generation=2, attempt=2))

    stale = _request(breakglass, current=3, target=2, generation=1, attempt=3)
    with pytest.raises(ValueError, match='generation mismatch'):
        breakglass_db.rollback_beta(stale)

    assert _doc(breakglass, BETA)['release_id'] == running['release_id']
    assert _doc(breakglass, BETA)['generation'] == 3, 'the stale operator must not have written'
    assert _doc(breakglass, f"{AUDITS}/{breakglass['audits'][2]}") is None


def test_a_rollback_target_has_to_be_a_registered_build(breakglass):
    """The target-manifest read. A pointer aimed at a manifest that does not exist makes the update
    resolution raise for every Beta client — the incident response would take the channel down."""
    import database.desktop_beta_breakglass as breakglass_db

    running = _beta_running(breakglass, 3)

    with pytest.raises(ValueError, match='rollback target manifest does not exist'):
        breakglass_db.rollback_beta(_request(breakglass, current=3, target=7, generation=1))

    assert _doc(breakglass, BETA)['release_id'] == running['release_id']
    assert _doc(breakglass, ADMISSION)['promotion_enabled'] is True, 'a refused break-glass changes nothing'
    assert _doc(breakglass, f"{AUDITS}/{breakglass['audits'][0]}") is None


def test_a_rollback_cannot_land_on_an_emergency_build(breakglass):
    """Rolling back means going to a build with real evidence. An emergency artifact records
    ``qualification_passed: False``; landing on one would leave Beta testers on an unqualified build and
    call it a recovery."""
    import database.desktop_beta_breakglass as breakglass_db

    running = _beta_running(breakglass, 3)
    _register(breakglass, 1, tier='emergency')

    with pytest.raises(ValueError, match='must not be an emergency manifest'):
        breakglass_db.rollback_beta(_request(breakglass, current=3, target=1, generation=1))

    assert _doc(breakglass, BETA)['release_id'] == running['release_id']
    assert _doc(breakglass, ADMISSION)['promotion_enabled'] is True


# --- transaction: emergency rollout -------------------------------------------------------------------


def test_an_emergency_rollout_registers_the_build_and_ships_it_in_one_commit(breakglass):
    """The forward escape hatch: no previous build is safe, so an unqualified fix is pushed. The manifest
    is CREATED inside the same transaction that moves the pointer, pauses the gate and writes the audit —
    a manifest retained without the pointer move would be an unqualified build sitting in the registry,
    and a pointer move without the manifest would break resolution for every Beta client."""
    import database.desktop_beta_breakglass as breakglass_db

    _beta_running(breakglass, 3)
    emergency = _manifest(breakglass['series'], 5, tier='emergency')
    request = _request(breakglass, current=3, target=5, generation=1)

    result = breakglass_db.emergency_rollout_beta(request, emergency)

    assert result['pointer']['release_id'] == emergency['release_id']
    assert _doc(breakglass, f"{MANIFESTS}/{emergency['release_id']}") == emergency
    assert _doc(breakglass, BETA)['generation'] == 2
    assert _doc(breakglass, ADMISSION)['promotion_enabled'] is False

    audit = _doc(breakglass, f"{AUDITS}/{breakglass['audits'][0]}")
    assert audit['operation'] == 'rollout'
    assert audit['target_manifest_sha256'] == _digest(emergency)
    assert audit['normal_path_unavailable'] == request['normal_path_unavailable']


def test_an_emergency_build_must_carry_a_higher_build_number(breakglass):
    """Read the current pointer's build, or ship an update no client will take. Sparkle does not install
    a downgrade: an emergency build numbered below the broken one would leave every tester on the broken
    build while the incident is recorded as resolved."""
    import database.desktop_beta_breakglass as breakglass_db

    running = _beta_running(breakglass, 3)
    too_low = _manifest(breakglass['series'], 2, tier='emergency')

    with pytest.raises(ValueError, match='must have a higher build'):
        breakglass_db.emergency_rollout_beta(_request(breakglass, current=3, target=2, generation=1), too_low)

    assert _doc(breakglass, BETA)['release_id'] == running['release_id']
    assert _doc(breakglass, f"{MANIFESTS}/{too_low['release_id']}") is None, 'nothing is retained'
    assert _doc(breakglass, ADMISSION)['promotion_enabled'] is True


def test_an_emergency_rollout_cannot_launder_a_build_into_looking_qualified(breakglass):
    """The emergency tier IS the record that this build did not qualify. A rollout carrying normal
    evidence would put an unreviewed build into the registry indistinguishable from one that passed, and
    the next resolution would treat it as a legitimate Beta artifact."""
    import database.desktop_beta_breakglass as breakglass_db

    _beta_running(breakglass, 3)
    laundered = _manifest(breakglass['series'], 5, tier='signed-smoke')

    with pytest.raises(ValueError, match='must preserve failed qualification truth'):
        breakglass_db.emergency_rollout_beta(_request(breakglass, current=3, target=5, generation=1), laundered)

    assert _doc(breakglass, f"{MANIFESTS}/{laundered['release_id']}") is None
    assert _doc(breakglass, BETA)['generation'] == 1


def test_an_emergency_rollout_cannot_contradict_a_manifest_already_registered(breakglass):
    """Read-before-create on the target. If a first attempt already retained this release id, a second
    attempt carrying different bytes must be refused rather than overwrite the artifact whose digest the
    audit of the first attempt recorded."""
    import database.desktop_beta_breakglass as breakglass_db

    _beta_running(breakglass, 3)
    registered = _register(breakglass, 5, tier='emergency')
    rebuilt = {**registered, 'ed_signature': 'rebuilt-under-pressure'}

    with pytest.raises(ValueError, match='immutable manifest collision'):
        breakglass_db.emergency_rollout_beta(_request(breakglass, current=3, target=5, generation=1), rebuilt)

    assert _doc(breakglass, f"{MANIFESTS}/{registered['release_id']}")['ed_signature'] == 'sparkle-signature'
    assert _doc(breakglass, BETA)['generation'] == 1
    assert _doc(breakglass, f"{AUDITS}/{breakglass['audits'][0]}") is None
