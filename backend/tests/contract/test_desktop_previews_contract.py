"""Dual-backend contract for the desktop preview registry (ADR-0044 facade + ADR-0002 store port).

`database/desktop_previews.py` decides which `.dmg` a tester who follows a branch's preview link
actually downloads. It keeps two documents per branch: an **immutable** manifest keyed by
``slug:source_sha`` (the artifact that was built, notarized and stapled) and one **mutable** pointer
keyed by the slug (the artifact currently offered). Everything that moves the pointer or registers an
artifact goes through one shape:

    transaction   `_publish_preview_transaction` reads the artifact and the pointer and then advances
                  the slug; `_delist_preview_transaction` reads the pointer before deleting it. Both
                  are a compare-and-swap on ``generation``.

Why the translation has to be exact, in user terms. The pointer is the answer to "what does this
branch's install link give me". If the in-transaction read is lost, the CAS silently becomes a blind
overwrite: two publishes racing off the same branch both win, and the pointer ends up on whichever
`set` landed last — which is not necessarily the newest commit. A tester then installs a build that
does not contain the change they were asked to verify, reports it working (or broken), and nothing in
the pointer says which binary they actually ran. The delist path fails the other way: a stale
compare-and-delete that is not refused withdraws the download from under a review still in progress,
and since the pointer is the only mutable record, nothing afterwards says what was pulled. The
immutability check is the third read: ``slug:source_sha`` is a promise that that commit produced that
exact `.dmg`, and a second workflow run that rebuilt it differently must be refused rather than
silently replace the artifact whose digest a tester wrote down.

**Writing this suite found a real defect, since fixed.** `_publish_preview_transaction` used to create
the manifest BEFORE it read the pointer. The Python Firestore SDK refuses that client-side
(`ReadAfterWriteError: Attempted read after write in a transaction`), so on the raw-SDK posture — what
upstream deploys — EVERY first publish of a new artifact raised before reaching the network, and only a
re-publish of an already-registered artifact worked. The facade over Mongo applies writes inside the
session and lets the read through, so on-prem never saw it: the defect lived in exactly the half of the
matrix nobody ran. The module's own unit suite drives the transaction with `MagicMock`s, which model no
ordering at all, so nothing caught it either. Both reads now happen first, and
`test_registering_a_brand_new_artifact_works_on_both_backends` is the regression test.

Several tests below still **seed the immutable artifact through the neutral store** rather than through
`publish_preview`. That is not a workaround any more, it is scoping: those tests are about the pointer
compare-and-swap, and seeding the artifact keeps the assertion on the one thing they claim to hold.

Shapes NOT covered: none. `transaction` is the only at-risk shape the guard counts in this module.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

PREVIEW_MANIFESTS = 'desktop_preview_manifests'
PREVIEW_POINTERS = 'desktop_preview_pointers'


def _sha40() -> str:
    return (uuid.uuid4().hex + uuid.uuid4().hex)[:40]


def _artifact(slug: str, source_sha: str, **overrides):
    """A preview payload the way the publisher submits one.

    Every identity field is derived exactly as `normalize_preview_manifest` requires: the bundle id and
    URL scheme come from the slug digest, and the dmg URL is the one canonical immutable artifact path.
    """
    from database.desktop_previews import preview_identity

    identity = preview_identity(slug)
    data = {
        'slug': slug,
        'source_sha': source_sha,
        'dmg_url': f'https://storage.googleapis.com/omi_macos_updates/previews/{slug}/{source_sha}/Omi-Preview.dmg',
        'dmg_sha256': hashlib.sha256(source_sha.encode()).hexdigest(),
        'app_name': f'Omi Preview ({slug})',
        'bundle_id': f'com.omi.preview.{identity}',
        'url_scheme': f'omi-preview-{identity}',
        'built_at': '2026-08-18T09:00:00Z',
        'signer': 'Developer ID Application: Based Hardware Inc',
        'notarization': 'stapled',
        'notes': None,
        'backend_url': None,
    }
    data.update(overrides)
    return data


@pytest.fixture
def previews(bind_store):
    """One branch slug and two commits on it, isolated per run and cleaned up by exact path.

    ``desktop_preview_pointers`` and ``desktop_preview_manifests`` are TOP-LEVEL collections shared
    with every other run on this rig, so the teardown deletes the three documents this run can have
    produced and never touches the collections as a whole.
    """
    run = uuid.uuid4().hex[:8]
    slug = f'preview-{run}'
    first, second = _sha40(), _sha40()

    yield {'slug': slug, 'first': first, 'second': second, 'run': run, 'store': bind_store}

    bind_store.delete(f'{PREVIEW_POINTERS}/{slug}')
    for sha in (first, second):
        bind_store.delete(f'{PREVIEW_MANIFESTS}/{slug}:{sha}')


def _register(previews, sha: str, **overrides) -> dict:
    """Seed the immutable artifact the way the transaction's own create writes it.

    Through the neutral store, not through the module, so that the test that follows is about the
    pointer compare-and-swap alone — the part that decides which binary a tester gets. Registering the
    artifact through `publish_preview` works on both backends now (see the module docstring), but it
    would fold two contracts into one assertion.
    """
    artifact = _artifact(previews['slug'], sha, **overrides)
    previews['store'].set(
        f"{PREVIEW_MANIFESTS}/{previews['slug']}:{sha}", {**artifact, 'created_at': datetime.now(timezone.utc)}
    )
    return artifact


def _pointer(previews):
    stored = previews['store'].get(f"{PREVIEW_POINTERS}/{previews['slug']}")
    return stored.data if stored is not None and stored.exists else None


def _artifact_doc(previews, sha: str):
    stored = previews['store'].get(f"{PREVIEW_MANIFESTS}/{previews['slug']}:{sha}")
    return stored.data if stored is not None and stored.exists else None


# --- transaction: publishing ------------------------------------------------------------------------


def test_publishing_points_the_slug_at_the_registered_artifact(previews):
    """The happy path stated as the tester sees it: the branch's install link now resolves to this
    commit, and to the exact `.dmg` digest registered for it."""
    import database.desktop_previews as previews_db

    artifact = _register(previews, previews['first'])

    result = previews_db.publish_preview(artifact)

    assert result['pointer']['source_sha'] == previews['first']
    assert result['pointer']['generation'] == 1
    assert _pointer(previews)['source_sha'] == previews['first']

    resolved = previews_db.get_current_preview(previews['slug'])
    assert resolved['manifest']['dmg_sha256'] == artifact['dmg_sha256']
    assert resolved['pointer']['generation'] == 1


def test_a_second_publisher_holding_a_stale_generation_is_refused_and_the_incumbent_pointer_survives(previews):
    """The race the transaction exists for.

    Two builds off the same branch finish at once; both read generation 0, both intend to be the
    offered build. Exactly one may win. If the loser is not refused, the pointer is decided by whichever
    `set` committed last, so the link can hand a tester the OLDER binary with no record that it did.
    The loser must be refused AND the winner's pointer must survive at the generation it won at.
    """
    import database.desktop_previews as previews_db

    winner = _register(previews, previews['first'])
    loser = _register(previews, previews['second'])

    previews_db.publish_preview(winner, expected_generation=0)

    with pytest.raises(ValueError, match='generation mismatch'):
        previews_db.publish_preview(loser, expected_generation=0)

    assert _pointer(previews)['source_sha'] == previews['first'], 'the incumbent must keep the slug'
    assert _pointer(previews)['generation'] == 1, 'a refused publish must not consume a generation'
    assert previews_db.get_current_preview(previews['slug'])['manifest']['source_sha'] == previews['first']


def test_the_loser_can_retry_against_the_generation_the_winner_left(previews):
    """The other half of a compare-and-swap: refusal must be recoverable. The refused publisher re-reads
    generation 1 and its retry succeeds — otherwise a single lost race would strand the branch."""
    import database.desktop_previews as previews_db

    previews_db.publish_preview(_register(previews, previews['first']), expected_generation=0)
    loser = _register(previews, previews['second'])

    result = previews_db.publish_preview(loser, expected_generation=1)

    assert result['pointer']['generation'] == 2
    assert previews_db.get_current_preview(previews['slug'])['manifest']['source_sha'] == previews['second']


def test_republishing_the_same_commit_does_not_move_the_generation(previews):
    """A retried publish of the artifact already offered is not a change.

    Only the in-transaction read can tell "already there" from "new". Without it the re-run of a
    workflow burns a generation, and every publisher still holding the previous number is then refused
    for a change that never happened.
    """
    import database.desktop_previews as previews_db

    artifact = _register(previews, previews['first'])

    first = previews_db.publish_preview(artifact)
    again = previews_db.publish_preview(artifact)

    assert again['pointer']['generation'] == first['pointer']['generation'] == 1
    assert again['pointer']['source_sha'] == previews['first']
    assert _pointer(previews)['generation'] == 1


def test_the_same_key_cannot_be_reused_for_a_different_artifact(previews):
    """``slug:source_sha`` is a promise that that commit produced that exact `.dmg`.

    Read inside the transaction, so a second workflow run that rebuilt the same commit differently is
    refused instead of quietly replacing the artifact a tester already downloaded — and the pointer
    must not move either, or the link would advertise a digest nobody registered.
    """
    import database.desktop_previews as previews_db

    registered = _register(previews, previews['first'])
    previews_db.publish_preview(registered)

    with pytest.raises(ValueError, match='different immutable metadata'):
        previews_db.publish_preview(_artifact(previews['slug'], previews['first'], signer='Someone Else'))

    assert _artifact_doc(previews, previews['first'])['signer'] == registered['signer']
    assert _pointer(previews)['generation'] == 1


def test_registering_a_brand_new_artifact_works_on_both_backends(previews):
    """REGRESSION. This is the test that was not here, and the defect it would have caught.

    `_publish_preview_transaction` used to create the manifest and only THEN read the pointer.
    Firestore's Python SDK enforces "all reads before writes" CLIENT-side, so on the raw-SDK posture the
    first publish of any new artifact died with `ReadAfterWriteError` before a single byte reached the
    server: a preview could never be registered at all, only re-published once its manifest happened to
    exist. The neutral facade applies the write inside the Mongo session and lets the read through, so
    on-prem never saw it — a defect that hid in exactly the half of the matrix nobody ran.

    Nothing caught it because the module's unit suite drives this transaction with `MagicMock`s, which
    model no ordering at all. (The repo does ship a fixture that does —
    `tests/unit/fixtures/strict_firestore_transaction.py` — it just is not used here.) Reordering the
    two reads to the top is the fix; this asserts the outcome on both backends instead.
    """
    import database.desktop_previews as previews_db

    fresh = _artifact(previews['slug'], previews['first'])

    published = previews_db.publish_preview(fresh)

    assert published['pointer']['generation'] == 1
    assert published['pointer']['source_sha'] == previews['first']
    assert _artifact_doc(previews, previews['first'])['dmg_sha256'] == fresh['dmg_sha256']
    assert _pointer(previews)['source_sha'] == previews['first']


def test_a_publish_refused_by_the_pointer_CAS_registers_nothing(previews):
    """The rollback, which only means something now that the first publish can happen at all.

    A publish whose compare-and-swap loses must leave NO half-registered artifact: the manifest is
    immutable and keyed by `slug:source_sha`, so a stray record becomes authoritative for every later
    retry of that exact commit — and the retry then compares against it and can never win.
    """
    import database.desktop_previews as previews_db

    previews_db.publish_preview(_artifact(previews['slug'], previews['first']))

    with pytest.raises(ValueError, match='generation mismatch'):
        previews_db.publish_preview(_artifact(previews['slug'], previews['second']), expected_generation=0)

    assert _artifact_doc(previews, previews['second']) is None, 'the rolled-back create must not persist'
    assert _pointer(previews)['source_sha'] == previews['first']


# --- transaction: delisting -------------------------------------------------------------------------


def test_delisting_with_a_stale_generation_is_refused_and_the_build_stays_installable(previews):
    """Compare-and-delete. The pointer is the only thing that makes a preview reachable, so a delist
    that is not fenced on the generation the caller saw withdraws a build from under a review in
    progress — and because the pointer is gone, nothing afterwards records which artifact was pulled."""
    import database.desktop_previews as previews_db

    previews_db.publish_preview(_register(previews, previews['first']))
    previews_db.publish_preview(_register(previews, previews['second']))

    with pytest.raises(ValueError, match='generation mismatch'):
        previews_db.delist_preview(previews['slug'], expected_generation=1)

    assert _pointer(previews)['source_sha'] == previews['second'], 'the pointer must survive a refused delist'
    assert previews_db.get_current_preview(previews['slug']) is not None


def test_delisting_removes_the_pointer_and_retains_the_immutable_artifact(previews):
    """Delisting stops offering a build; it does not rewrite history. The artifact stays resolvable by
    its exact commit, which is how a bug report naming that SHA can still be traced to a binary."""
    import database.desktop_previews as previews_db

    previews_db.publish_preview(_register(previews, previews['first']))

    result = previews_db.delist_preview(previews['slug'], expected_generation=1)

    assert result == {'slug': previews['slug'], 'deleted': True, 'generation': 1}
    assert _pointer(previews) is None
    assert previews_db.get_current_preview(previews['slug']) is None
    assert previews_db.get_preview_manifest(previews['slug'], previews['first'])['source_sha'] == previews['first']


def test_delisting_a_slug_that_was_never_published_reports_nothing_deleted(previews):
    """Read-before-delete again: a slug with no pointer is not an error, and the transaction must not
    fabricate a deletion it did not perform — the caller uses ``deleted`` to decide what to report."""
    import database.desktop_previews as previews_db

    result = previews_db.delist_preview(previews['slug'], expected_generation=0)

    assert result == {'slug': previews['slug'], 'deleted': False, 'generation': None}
    assert _pointer(previews) is None


def test_a_delisted_slug_can_be_republished_from_the_generation_it_reported(previews):
    """Re-publishing after a delist starts a new pointer at generation 1. If the delete did not really
    remove the document, the new publisher's CAS would be measured against a dead generation and the
    branch could never be offered again."""
    import database.desktop_previews as previews_db

    previews_db.publish_preview(_register(previews, previews['first']))
    previews_db.delist_preview(previews['slug'], expected_generation=1)

    result = previews_db.publish_preview(_register(previews, previews['second']), expected_generation=0)

    assert result['pointer']['source_sha'] == previews['second']
    assert result['pointer']['generation'] == 1
    assert previews_db.get_current_preview(previews['slug'])['manifest']['source_sha'] == previews['second']
