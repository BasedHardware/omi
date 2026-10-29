"""Exception-taxonomy coverage contract for the projection assignment walk.

David, 10-29 (simtests): tonight's wedges were raise sites whose exception
class no test had a disposition for. This contract fails when a NEW raise site
appears in the walk's callee modules whose exception class has no handled
disposition — before it can wedge an owner chain in production.

Static list derived from the code: every constructor-raise site in the
assignment-path modules below must raise a class named in ``TAXONOMY``, and
every kind eligible for a permanent chain-head injection must appear in the
poison-head matrix (``test_pipeline_sim_poison_head``). Re-raises of caught
exceptions are exempt: they surface the original site's class.
"""

import ast
from pathlib import Path

from tests.unit.test_pipeline_sim_poison_head import (
    ALL_KINDS,
    POISON_CONFLICT_SUBTYPES,
    POISON_PAYLOAD_KINDS,
    expected_outcome,
)
from utils.sync.assignment_errors import (
    SYNC_ASSIGNMENT_CONFLICT_SUBTYPES,
    SYNC_ASSIGNMENT_CONFLICT_STRUCTURAL,
    SYNC_ASSIGNMENT_CONFLICT_AWAITING_WRITER,
)

BACKEND = Path(__file__).resolve().parents[2]

# The walk's assignment path: the Projector module plus the callees whose
# raises can escape ``assign_parts``/``_assign`` into the walk loop.
SCANNED_MODULES = {
    'utils/batch_pipeline/projection.py': {},
    'utils/batch_pipeline/live_projection.py': {},
    'utils/batch_pipeline/source_audio.py': {},
    'utils/batch_pipeline/projection_parts.py': {},
    'utils/batch_pipeline/context.py': {'_blocked': 'ProjectionBlocked'},
    'utils/batch_pipeline/contracts.py': {},
    'utils/batch_pipeline/artifacts.py': {},
    'database/batch_pipeline_projection_protocol.py': {},
    'database/batch_pipeline_projection_session.py': {},
}

# Exception class -> the walk's disposition for it. Keep in sync with the
# handlers in ``projection.py`` (``_walk_rows``/``_assign``/``assign_parts``)
# and the poison-head matrix's expected outcomes. Note the subclass family:
# ProjectionPredecessorPending and ProjectionGenerationAmbiguous derive from
# ProjectionBlocked, so the walk's specific handlers must stay ordered before
# the generic blocked catch.
TAXONOMY = {
    # Strike rule: structural subtypes and backfill awaiting-writer take the
    # held disposition; fresh awaiting-writer keeps waiting for its writer.
    'SyncAssignmentConflict': 'strike-rule: quarantine_held | wait (subtype + lane)',
    'SyncAssignmentSuperseded': 'supersede (persist_empty superseded receipt)',
    'ProjectionGenerationAmbiguous': 'quarantine_held',
    'BatchPrivacyBlocked': 'privacy: hold (HOLD_REASONS) | privacy_deleted | raise',
    'ProjectionReplay': 'replay (receipt is progress; resume obligations)',
    'ProjectionPredecessorPending': 'predecessor wait (ordered chain, observable)',
    'ProjectionBlocked': 'blocked wait (claim busy / evidence / fences; observable, not dispositioned)',
    'StepDeadline': 'resume next walk step (multipart budget)',
    # Payload-contract violations quarantine-hold via payload_contract_violation;
    # Firestore contention-shaped ValueError stays retryable. A tampered
    # artifact body fails authenticated decryption as InvalidTag — permanent.
    'ValueError': 'payload contract: quarantine_held | contention retry',
    'InvalidTag': 'payload contract: quarantine_held (tampered artifact body)',
    # Artifact authorization refusals (expired voice evidence, privacy
    # generation drift) are observable waits on the sweep, not dispositions.
    'PermissionError': 'authorization wait (observable, retried by the sweep)',
    'TimeoutError': 'transient storage timeout: retryable, never dispositioned',
    'OSError': 'transient storage error: retryable, never dispositioned',
}


def constructor_raise_classes(path: Path, aliases: dict[str, str]):
    """Exception class names raised at constructor-raise sites in one module."""
    tree = ast.parse(path.read_text())
    raised = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        if isinstance(node.exc, ast.Call):
            name = getattr(node.exc.func, 'id', None)
        else:
            name = getattr(node.exc, 'id', None)
        if name is None:
            continue
        resolved = aliases.get(name, name)
        # Constructor calls always count; bare names count when capitalized
        # (``raise error`` re-raises a caught instance, not a new site).
        if isinstance(node.exc, ast.Call) or name[:1].isupper():
            raised.add(resolved)
    return raised


def test_every_raise_site_in_the_walk_callees_has_a_disposition():
    unknown = []
    for relative, aliases in SCANNED_MODULES.items():
        for raised in sorted(constructor_raise_classes(BACKEND / relative, aliases)):
            if raised not in TAXONOMY:
                unknown.append(f'{relative}: {raised}')
    assert not unknown, (
        'New exception raise site(s) without a handled disposition:\n'
        + '\n'.join(unknown)
        + '\nAdd the class to TAXONOMY with the walk disposition, and a case to '
        'test_pipeline_sim_poison_head if a permanent head injection is possible.'
    )


def test_conflict_subtype_sets_are_complete_and_disjoint():
    """The strike rule must classify every bounded subtype — none may fall
    through to the unlabeled retry-forever bucket by accident. The one
    deliberately unclassified subtype waits on every lane (the bridge seam
    retries until its source is tombstoned); a change to that set is a
    contract change this pin makes visible."""
    classified = SYNC_ASSIGNMENT_CONFLICT_STRUCTURAL | SYNC_ASSIGNMENT_CONFLICT_AWAITING_WRITER
    assert not SYNC_ASSIGNMENT_CONFLICT_STRUCTURAL & SYNC_ASSIGNMENT_CONFLICT_AWAITING_WRITER
    assert classified <= SYNC_ASSIGNMENT_CONFLICT_SUBTYPES
    assert (SYNC_ASSIGNMENT_CONFLICT_SUBTYPES - {'other'}) - classified == {'bridge_source_not_tombstone'}


def test_poison_head_matrix_covers_every_eligible_kind():
    """The coverage contract: the taxonomy's injectable kinds all appear in the
    poison-head matrix, so a new raise class cannot skip its head-injection."""
    covered_conflicts = {kind.split(':', 1)[1] for kind in ALL_KINDS if kind.startswith('conflict:')}
    assert (
        covered_conflicts == POISON_CONFLICT_SUBTYPES == (SYNC_ASSIGNMENT_CONFLICT_SUBTYPES | {'other'})
    ), 'every conflict subtype (and the unlabeled fallback) needs a poison-head case'
    covered_payload = {kind for kind in ALL_KINDS if kind.startswith('payload:')}
    assert covered_payload == POISON_PAYLOAD_KINDS
    # Every declared payload violation advances; contention and unlabeled wait.
    for kind in ALL_KINDS:
        for lane in ('backfill', 'fresh'):
            assert expected_outcome(kind, lane) in {'advance', 'wait'}
    assert expected_outcome('contention-value-error', 'backfill') == 'wait'
