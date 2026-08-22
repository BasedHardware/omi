"""Dual-backend contract for the desktop update channels (ADR-0044 facade + ADR-0002 store port).

`database/desktop_update_channels.py` decides which macOS binary every desktop user is offered. Two
kinds of document: **immutable release manifests** (one per build, keyed by its release tag) and two
**mutable channel pointers** — ``macos-stable`` and ``macos-beta`` — each carrying a monotonic
``generation``. A third document, the singleton ``desktop_beta_admission/control``, is the gate the
Beta pipeline has to pass: it names the one reserved candidate and says whether promotion is open.
Everything that moves a pointer or the gate is one shape:

    transaction   `_promote_channel_transaction` (stable), `_admit_qualified_beta_transaction` (beta),
                  `_reserve_beta_candidate_transaction` and `_set_beta_admission_enabled_transaction`
                  (the gate). Each one READS the document it is about to overwrite and refuses unless
                  the caller's view still holds — a compare-and-swap on ``generation``, plus the
                  roll-forward and evidence rules.

What the wrong translation costs a user, per rule:

*The pointer read.* Drop it and the compare-and-swap becomes a blind `set`. Two release jobs racing —
the normal case at the end of a release train — then both "succeed", and the pointer ends on whichever
write landed last. That is not necessarily the newest build: every macOS user on that channel is then
offered an older binary as an update, or a build whose manifest was never the one the operator
approved. Nothing errors; the update simply ships. The generation is what makes the loser detectable
at all, including the ABA case where the pointer moved away and back so the release id alone looks
untouched.

*The manifest read.* The transaction refuses to point a channel at a release that is not registered,
and refuses a build whose evidence is not accepted normal-path evidence. Lose it and a channel can be
aimed at a manifest that does not exist (the update endpoint then 500s for everyone on that channel),
or an **emergency** build — one whose recorded truth is `qualification_passed: False` — can be handed
to the whole Stable population as a routine update.

*The admission-control read.* `_admit_qualified_beta_transaction` reads the gate FIRST, before it
retains anything, so a pause or a newer reservation committed while the (slow, untrusted) GitHub
evidence was being validated necessarily loses. Lose that read and a Beta build keeps shipping after
an operator has closed the gate during an incident — the exact scenario the break-glass module pauses
promotion for — or a candidate nobody reserved gets admitted because its own generation was never
compared.

*Idempotence.* Both promote paths return the incumbent unchanged when the target is already current,
instead of consuming a generation. That is only possible because of the read: a retried CI job that
burns a generation invalidates every other actor's compare-and-swap for a change that never happened.

Shapes NOT covered: none. `transaction` is the only at-risk shape the guard counts in this module.

Isolation: the pointers (``macos-stable`` / ``macos-beta``) and the admission control are SINGLETON
documents with fixed ids — they cannot be randomised. The fixture therefore deletes exactly those
three paths before and after each test, and every release manifest it registers carries a run-unique
version/build so two runs never contend over an immutable record. **This suite must not run
concurrently with `test_desktop_beta_breakglass_contract.py`**, which drives the same two singletons.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid

import pytest

CHANNELS = 'desktop_update_channels'
MANIFESTS = 'desktop_release_manifests'
ADMISSION = 'desktop_beta_admission/control'
STABLE = f'{CHANNELS}/macos-stable'
BETA = f'{CHANNELS}/macos-beta'

# Enough release slots for the longest sequence below; every one is deleted in teardown.
_SLOTS = range(6)


def _release_id(series: int, slot: int) -> str:
    return f'v0.{series}.{slot}+{series * 100 + slot}-macos'


def _manifest(series: int, slot: int, *, tier: str = 'T2', **overrides):
    """A canonical v1 release manifest for one run-unique build.

    The evidence asset name is not decoration: `desktop_release_manifest.validate_manifest` pins one
    exact asset per tier, so a manifest is only constructible for the evidence class it claims.
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


@pytest.fixture
def channels(bind_store):
    """A run-unique release series, with the three singleton documents cleared either side.

    ``macos-stable``, ``macos-beta`` and ``desktop_beta_admission/control`` have FIXED ids — the module
    hard-codes them — so isolation cannot come from unique ids. It comes from clearing exactly those
    three paths (never the collections) before the test as well as after: a previous crashed run would
    otherwise leave a pointer whose generation silently invalidates every assertion here.
    """
    run = uuid.uuid4().hex[:8]
    series = int(run[:4], 16)
    singletons = (STABLE, BETA, ADMISSION)

    for path in singletons:
        bind_store.delete(path)

    yield {'run': run, 'series': series, 'store': bind_store}

    for path in singletons:
        bind_store.delete(path)
    for slot in _SLOTS:
        bind_store.delete(f'{MANIFESTS}/{_release_id(series, slot)}')


def _doc(channels, path: str):
    stored = channels['store'].get(path)
    return stored.data if stored is not None and stored.exists else None


def _register(channels, slot: int, *, tier: str = 'T2'):
    import database.desktop_update_channels as channels_db

    manifest = _manifest(channels['series'], slot, tier=tier)
    channels_db.register_release_manifest(manifest)
    return manifest


def _open_beta_gate(channels, slot: int):
    """Reserve one candidate and open the gate, the way the Beta pipeline does before it admits."""
    import database.desktop_update_channels as channels_db

    channels_db.reserve_beta_candidate(_release_id(channels['series'], slot))
    return channels_db.set_beta_admission_enabled(True)['control_generation']


# --- immutable manifests ----------------------------------------------------------------------------


def test_a_registered_manifest_is_retained_exactly_and_cannot_be_replaced(channels):
    """The manifest is what the app downloads and verifies: URLs, digests, Sparkle signature. It is
    keyed by its release tag and read back on every resolution, so a second registration of that tag
    with different bytes must be refused — otherwise a build that was already shipped and pinned by
    digest can be swapped underneath the users who have it."""
    import database.desktop_update_channels as channels_db

    manifest = _manifest(channels['series'], 0)
    registered = channels_db.register_release_manifest(manifest)

    assert registered == manifest
    assert channels_db.get_release_manifest(manifest['release_id']) == manifest
    assert channels_db.register_release_manifest(manifest) == manifest, 'an exact retry is not a conflict'

    with pytest.raises(ValueError, match='different immutable metadata'):
        channels_db.register_release_manifest({**manifest, 'ed_signature': 'forged'})

    assert _doc(channels, f"{MANIFESTS}/{manifest['release_id']}")['ed_signature'] == 'sparkle-signature'


# --- transaction: the stable pointer ------------------------------------------------------------------


def test_promoting_a_registered_manifest_moves_the_stable_pointer(channels):
    """The happy path stated as a user sees it: the Stable channel now offers this build, and resolves
    to the exact manifest registered for it."""
    import database.desktop_update_channels as channels_db

    manifest = _register(channels, 1)

    pointer = channels_db.promote_channel('macos', 'stable', manifest['release_id'])

    assert pointer['release_id'] == manifest['release_id']
    assert pointer['generation'] == 1
    assert _doc(channels, STABLE)['build_number'] == manifest['build_number']

    resolved = channels_db.get_channel_release('macos', 'stable')
    assert resolved['manifest'] == manifest
    assert resolved['pointer']['generation'] == 1
    assert _doc(channels, BETA) is None, 'promoting Stable must not touch Beta'


def test_a_channel_cannot_be_pointed_at_a_release_that_was_never_registered(channels):
    """The manifest read. A pointer to a missing manifest is not a silent no-op: `get_channel_release`
    raises for every client afterwards, i.e. the update check fails for everyone on the channel."""
    import database.desktop_update_channels as channels_db

    with pytest.raises(ValueError, match='release manifest does not exist'):
        channels_db.promote_channel('macos', 'stable', _release_id(channels['series'], 2))

    assert _doc(channels, STABLE) is None, 'a refused promotion must not create a pointer'


def test_the_stable_pointer_is_roll_forward_only(channels):
    """A downgrade offered as an update. Without the in-transaction read of the current pointer there is
    no current build to compare against, so an older manifest promoted by mistake (or by a re-run of an
    earlier job) would be pushed to every Stable user as if it were new."""
    import database.desktop_update_channels as channels_db

    old = _register(channels, 1)
    new = _register(channels, 3)
    channels_db.promote_channel('macos', 'stable', new['release_id'])

    with pytest.raises(ValueError, match='roll-forward only'):
        channels_db.promote_channel('macos', 'stable', old['release_id'])

    assert _doc(channels, STABLE)['release_id'] == new['release_id'], 'the incumbent build must survive'
    assert _doc(channels, STABLE)['generation'] == 1


def test_the_second_of_two_racing_repoints_is_refused_and_the_winner_survives(channels):
    """Two operators repointing off the same view. A repoint is an explicit compare-and-swap, so the
    loser must be told its view is stale rather than overwrite the winner: whichever build the winner
    chose is the one users are being offered, and a silent second write replaces it with a third."""
    import database.desktop_update_channels as channels_db

    a, b, c = (_register(channels, slot) for slot in (1, 2, 3))
    channels_db.promote_channel('macos', 'stable', a['release_id'])

    winner = channels_db.promote_channel(
        'macos',
        'stable',
        b['release_id'],
        operation='repoint',
        expected_current_release_id=a['release_id'],
        expected_generation=1,
    )
    assert winner['generation'] == 2

    with pytest.raises(ValueError, match='current release mismatch'):
        channels_db.promote_channel(
            'macos',
            'stable',
            c['release_id'],
            operation='repoint',
            expected_current_release_id=a['release_id'],
            expected_generation=1,
        )

    assert _doc(channels, STABLE)['release_id'] == b['release_id'], 'the winner keeps the channel'
    assert _doc(channels, STABLE)['generation'] == 2, 'a refused repoint must not consume a generation'


def test_the_generation_catches_a_pointer_that_moved_away_and_back(channels):
    """ABA — the case the release id alone cannot see, and the reason the generation is read.

    An operator reads (A, generation 1). Meanwhile the channel is repointed to B and back to A. The
    release id matches again, so a check on identity alone would let the stale operator proceed and
    overwrite a decision taken after theirs. Only the generation, read inside the transaction, refuses.
    """
    import database.desktop_update_channels as channels_db

    a, b, c = (_register(channels, slot) for slot in (1, 2, 3))
    channels_db.promote_channel('macos', 'stable', a['release_id'])
    channels_db.promote_channel(
        'macos',
        'stable',
        b['release_id'],
        operation='repoint',
        expected_current_release_id=a['release_id'],
        expected_generation=1,
    )
    channels_db.promote_channel(
        'macos',
        'stable',
        a['release_id'],
        operation='repoint',
        expected_current_release_id=b['release_id'],
        expected_generation=2,
    )

    with pytest.raises(ValueError, match='generation mismatch'):
        channels_db.promote_channel(
            'macos',
            'stable',
            c['release_id'],
            operation='repoint',
            expected_current_release_id=a['release_id'],
            expected_generation=1,
        )

    assert _doc(channels, STABLE)['release_id'] == a['release_id']
    assert _doc(channels, STABLE)['generation'] == 3, 'the stale actor must not have written'


def test_promoting_the_release_already_offered_is_idempotent(channels):
    """A re-run of the release job is not a change. The read is what tells "already current" from
    "new": a promotion that burned a generation would invalidate every other actor's compare-and-swap
    for a pointer that never moved."""
    import database.desktop_update_channels as channels_db

    manifest = _register(channels, 1)
    first = channels_db.promote_channel('macos', 'stable', manifest['release_id'])
    again = channels_db.promote_channel('macos', 'stable', manifest['release_id'])

    # Compared field-wise except ``updated_at``: the idempotent path returns the pointer READ BACK from
    # storage, and BSON datetimes are millisecond-precision, so Mongo hands back the same instant
    # truncated while Firestore preserves microseconds. That is storage resolution, not a pointer move —
    # ``generation`` is what says whether the channel changed, and it must not have.
    assert {key: value for key, value in again.items() if key != 'updated_at'} == {
        key: value for key, value in first.items() if key != 'updated_at'
    }
    assert again['updated_at'] == _doc(channels, STABLE)['updated_at'], 'the incumbent was read back'
    assert _doc(channels, STABLE)['generation'] == 1


def test_an_emergency_build_can_never_be_offered_on_stable(channels):
    """An emergency manifest records `qualification_passed: False` — it exists only to get users off a
    broken build during an incident, through the audited break-glass path. The generic promotion API
    reads the manifest inside the transaction precisely so that build cannot become the routine update
    every Stable user is offered."""
    import database.desktop_update_channels as channels_db

    good = _register(channels, 1)
    emergency = _register(channels, 2, tier='emergency')
    channels_db.promote_channel('macos', 'stable', good['release_id'])

    with pytest.raises(ValueError, match='accepted normal-path evidence'):
        channels_db.promote_channel('macos', 'stable', emergency['release_id'])

    assert _doc(channels, STABLE)['release_id'] == good['release_id']


# --- transaction: the beta admission gate -------------------------------------------------------------


def test_reserving_a_candidate_records_it_without_opening_the_gate(channels):
    """Reserving names the one build allowed to be admitted next. It must NOT enable promotion by
    itself: a reservation is the pipeline saying "this is the candidate", not an operator saying "ship
    it"."""
    import database.desktop_update_channels as channels_db

    tag = _release_id(channels['series'], 1)

    control = channels_db.reserve_beta_candidate(tag)

    assert control['latest_reserved_tag'] == tag
    assert control['promotion_enabled'] is False
    assert control['control_generation'] == 1
    assert _doc(channels, ADMISSION)['latest_reserved_tag'] == tag


def test_a_lower_candidate_cannot_take_the_reservation(channels):
    """Reservations roll forward. The reservation is read inside the transaction so a slow, older
    pipeline run cannot claim the slot back from a newer candidate and have that older build be the one
    Beta testers are offered."""
    import database.desktop_update_channels as channels_db

    channels_db.reserve_beta_candidate(_release_id(channels['series'], 3))

    with pytest.raises(ValueError, match='roll forward'):
        channels_db.reserve_beta_candidate(_release_id(channels['series'], 1))

    control = _doc(channels, ADMISSION)
    assert control['latest_reserved_tag'] == _release_id(channels['series'], 3)
    assert control['control_generation'] == 1, 'a refused reservation must not bump the gate generation'


def test_reserving_the_same_candidate_twice_does_not_move_the_generation(channels):
    """``control_generation`` is the token the admission transaction compares against. A retried
    reservation that bumped it would invalidate a capture already in flight, and the admission of a
    perfectly good candidate would be refused for a change that never happened."""
    import database.desktop_update_channels as channels_db

    tag = _release_id(channels['series'], 1)
    first = channels_db.reserve_beta_candidate(tag)

    assert channels_db.reserve_beta_candidate(tag)['control_generation'] == first['control_generation'] == 1


def test_the_gate_cannot_be_opened_without_a_reservation(channels):
    """Opening admission with nothing reserved would let whatever candidate arrives next be admitted."""
    import database.desktop_update_channels as channels_db

    with pytest.raises(ValueError, match='cannot resume without a reservation'):
        channels_db.set_beta_admission_enabled(True)

    assert _doc(channels, ADMISSION) is None, 'a refused resume must not create an open gate'


def test_pausing_is_recorded_even_before_any_candidate_exists(channels):
    """An explicit pause is a state transition, not an absence. If it were not written, the next
    reservation would create a document and the operator's pause would be gone with no trace."""
    import database.desktop_update_channels as channels_db

    control = channels_db.set_beta_admission_enabled(False)

    assert control['promotion_enabled'] is False
    assert control['latest_reserved_tag'] is None
    assert _doc(channels, ADMISSION)['control_generation'] == 1


def test_pausing_an_already_paused_gate_does_not_move_the_generation(channels):
    """The gate transaction reads its own state first. A repeated pause that bumped the generation would
    invalidate an admission already captured against the previous number — the pipeline would then be
    refused because someone clicked pause twice, not because anything changed."""
    import database.desktop_update_channels as channels_db

    channels_db.reserve_beta_candidate(_release_id(channels['series'], 1))
    paused = channels_db.set_beta_admission_enabled(False)

    assert channels_db.set_beta_admission_enabled(False) == paused
    assert _doc(channels, ADMISSION)['control_generation'] == paused['control_generation']


def test_capture_hands_back_the_generation_the_admission_will_be_checked_against(channels):
    """The capture is taken BEFORE the slow untrusted GitHub reads; the number it returns is what the
    transaction later compares. If capture and transaction disagreed, either every admission would be
    refused or none would be fenced at all."""
    import database.desktop_update_channels as channels_db

    tag = _release_id(channels['series'], 1)
    generation = _open_beta_gate(channels, 1)

    captured = channels_db.capture_beta_admission(tag)

    assert captured['control_generation'] == generation == 2
    assert captured['promotion_enabled'] is True


# --- transaction: admitting a beta candidate ----------------------------------------------------------


def test_an_admitted_candidate_is_retained_and_only_beta_moves(channels):
    """One transaction retains the immutable manifest and advances the Beta pointer. Stable must not
    move, and the generic promotion API must not be able to reach Beta at all — otherwise a build could
    be offered to Beta testers without ever passing the admission gate."""
    import database.desktop_update_channels as channels_db

    generation = _open_beta_gate(channels, 1)
    manifest = _manifest(channels['series'], 1, tier='signed-smoke')

    result = channels_db.admit_qualified_beta_manifest(manifest, control_generation=generation)

    assert result['pointer']['generation'] == 1
    assert result['idempotent'] is False
    assert _doc(channels, f"{MANIFESTS}/{manifest['release_id']}") == manifest
    assert _doc(channels, BETA)['release_id'] == manifest['release_id']
    assert _doc(channels, STABLE) is None, 'admitting a Beta candidate must not move Stable'

    with pytest.raises(ValueError, match='stable-only'):
        channels_db.promote_channel('macos', 'beta', manifest['release_id'])


def test_a_racing_admission_with_a_stale_generation_is_refused_and_the_incumbent_beta_build_survives(channels):
    """The race the gate read exists for, and the loser's obligation.

    The pipeline captures generation G, then spends real time validating GitHub evidence. In that window
    a newer candidate is reserved, which bumps the gate. The late admission must lose: the Beta pointer
    keeps the build testers already have, and the loser's manifest is not retained either — a retained
    manifest for a build that was never admitted is an immutable record that later resolutions treat as
    authoritative.
    """
    import database.desktop_update_channels as channels_db

    stale_generation = _open_beta_gate(channels, 1)
    incumbent = _manifest(channels['series'], 1, tier='signed-smoke')
    channels_db.admit_qualified_beta_manifest(incumbent, control_generation=stale_generation)

    channels_db.reserve_beta_candidate(_release_id(channels['series'], 2))  # the concurrent reservation
    late = _manifest(channels['series'], 2, tier='signed-smoke')

    with pytest.raises(ValueError, match='beta admission generation changed'):
        channels_db.admit_qualified_beta_manifest(late, control_generation=stale_generation)

    assert _doc(channels, BETA)['release_id'] == incumbent['release_id'], 'testers keep the admitted build'
    assert _doc(channels, BETA)['generation'] == 1
    assert _doc(channels, f"{MANIFESTS}/{late['release_id']}") is None, 'the refused candidate is not retained'


def test_a_candidate_nobody_reserved_is_refused(channels):
    """The reservation is the allow-list of exactly one build. Read inside the transaction, so a
    manifest that is otherwise perfectly valid still cannot become the Beta build unless it is the one
    the pipeline reserved."""
    import database.desktop_update_channels as channels_db

    generation = _open_beta_gate(channels, 1)
    unreserved = _manifest(channels['series'], 2, tier='signed-smoke')

    with pytest.raises(ValueError, match='reservation does not match candidate'):
        channels_db.admit_qualified_beta_manifest(unreserved, control_generation=generation)

    assert _doc(channels, BETA) is None
    assert _doc(channels, f"{MANIFESTS}/{unreserved['release_id']}") is None


def test_a_closed_gate_refuses_every_candidate(channels):
    """The interlock the break-glass path depends on. After an incident pause, the pipeline must not be
    able to resume shipping Beta builds on its own — a candidate admitted through a closed gate is the
    incident happening a second time."""
    import database.desktop_update_channels as channels_db

    generation = _open_beta_gate(channels, 1)
    channels_db.set_beta_admission_enabled(False)
    manifest = _manifest(channels['series'], 1, tier='signed-smoke')

    with pytest.raises(ValueError, match='beta admission is disabled'):
        channels_db.admit_qualified_beta_manifest(manifest, control_generation=generation + 1)

    assert _doc(channels, BETA) is None
    assert _doc(channels, f"{MANIFESTS}/{manifest['release_id']}") is None


def test_an_exact_readmission_is_idempotent(channels):
    """A retried admission of the build already offered must report itself as a no-op and leave the
    generation alone, or the retry of a lost response becomes a real state change."""
    import database.desktop_update_channels as channels_db

    generation = _open_beta_gate(channels, 1)
    manifest = _manifest(channels['series'], 1, tier='signed-smoke')
    channels_db.admit_qualified_beta_manifest(manifest, control_generation=generation)

    again = channels_db.admit_qualified_beta_manifest(manifest, control_generation=generation)

    assert again['idempotent'] is True
    assert again['pointer']['generation'] == 1
    assert _doc(channels, BETA)['generation'] == 1


def test_a_rebuilt_candidate_cannot_replace_the_manifest_already_admitted(channels):
    """Same release tag, different bytes. The manifest is read inside the transaction, so the rebuild is
    refused and the Beta pointer stays on the artifact whose digests testers already verified."""
    import database.desktop_update_channels as channels_db

    generation = _open_beta_gate(channels, 1)
    manifest = _manifest(channels['series'], 1, tier='signed-smoke')
    channels_db.admit_qualified_beta_manifest(manifest, control_generation=generation)

    with pytest.raises(ValueError, match='different immutable metadata'):
        channels_db.admit_qualified_beta_manifest(
            {**manifest, 'ed_signature': 'rebuilt'}, control_generation=generation
        )

    assert _doc(channels, f"{MANIFESTS}/{manifest['release_id']}")['ed_signature'] == 'sparkle-signature'
    assert _doc(channels, BETA)['generation'] == 1
