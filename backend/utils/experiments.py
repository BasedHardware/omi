"""Randomized assignment for product experiments.

## Why this exists at all

The 2026-08-26 macOS churn cohort found four behavioral "levers" — recording
used, notifications received, chat used — with crude retention risk ratios of
1.9-2.2. Adjusting for week-1 active-day count collapsed every one of them to
roughly 1.05-1.11. The signal was engagement depth; the feature touches were
markers of it.

The general lesson is that at Omi almost any observational comparison between
users who did X and users who did not is dominated by one latent engagement
variable, and eligibility for almost any intervention correlates with it. A
non-randomized rollout therefore produces a real, statistically significant,
and completely meaningless number. Randomization is the only thing that makes
an intervention's effect knowable, so it has to be cheap enough that nobody is
tempted to skip it.

## The two functions that matter

``assigned_variant`` draws deterministically; ``enroll`` persists the draw and
records it in PostHog. Everything else here is support.

## Three decisions worth defending

**Persisted, not recomputed.** The draw is a pure hash, but the *assignment* is
a Firestore document. A pure hash silently re-randomizes the whole population
if anyone edits the salt, and — decisively for time-windowed experiments — it
cannot reconstruct a roster at all when eligibility is a property of a moment
("72-96h after signup, has not returned"). That predicate is false before the
window and false after it, so there is no later state to re-derive it from. One
document per enrolled user also makes a retried batch job idempotent for free.

**Both arms are enrolled through the same code path at the same moment.** The
classic way to ruin an experiment is to build the roster from something only
the treatment group does — an exposure event, an email open, a flag evaluation.
The holdout then never appears and silently leaves the denominator. Here,
enrollment happens before treatment is delivered and is identical for both
arms, so the control group's existence never depends on the user doing
anything. For an email experiment this is not a nicety: a holdout user may
never open the app again, so no client-side mechanism could observe them.

**Analysis is intention-to-treat.** ``enroll`` is the denominator. Delivery
outcomes (sent, bounced, opened) are recorded but are descriptive only.
Conditioning the comparison on opens would re-import the exact latent
engagement confounder this module exists to defeat — openers are the engaged
users — inside a design that had already solved it.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from utils.product_telemetry import emit_product_event

logger = logging.getLogger(__name__)

ENROLLED_EVENT = 'Experiment Enrolled'
CONTROL = 'control'
TREATMENT = 'treatment'

# A draw resolution of 10_000 makes splits expressible to a basis point, which
# is finer than any split we can power at this volume, and keeps the bucket
# arithmetic in exact integers.
_BUCKET_RESOLUTION = 10_000


@dataclass(frozen=True)
class Enrollment:
    """The result of attempting to enroll one user."""

    uid: str
    experiment_id: str
    variant: str
    newly_enrolled: bool

    @property
    def is_treatment(self) -> bool:
        return self.variant == TREATMENT


def bucket_of(experiment_id: str, uid: str) -> int:
    """Deterministic bucket in [0, 10000) for this (experiment, user).

    The experiment id **is** the salt. That is deliberate: it means a new
    experiment automatically re-randomizes (so a user unlucky in one experiment
    is not systematically unlucky in the next), while an existing experiment
    can never be accidentally re-randomized by someone editing a separate salt
    constant. The corollary is a rule: **never rename a running experiment.**
    """
    digest = hashlib.sha256(f'{experiment_id}:{uid}'.encode('utf-8')).digest()
    return int.from_bytes(digest[:4], 'big') % _BUCKET_RESOLUTION


def assigned_variant(experiment_id: str, uid: str, *, treatment_share: float = 0.5) -> str:
    """Draw a variant. Pure, deterministic, and side-effect free."""
    if not 0.0 <= treatment_share <= 1.0:
        raise ValueError('treatment_share must be within [0, 1]')
    return TREATMENT if bucket_of(experiment_id, uid) < round(treatment_share * _BUCKET_RESOLUTION) else CONTROL


def _assignment_ref(client: Any, experiment_id: str, uid: str) -> Any:
    return client.collection('experiments').document(experiment_id).collection('assignments').document(uid)


def existing_assignment(
    experiment_id: str, uid: str, *, firestore_client: Any | None = None
) -> Optional[Mapping[str, Any]]:
    from database._client import db

    client = firestore_client or db
    try:
        snapshot = _assignment_ref(client, experiment_id, uid).get()
    except Exception:
        logger.exception('experiments: assignment read failed experiment=%s', experiment_id)
        return None
    return (snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else None


def enroll(
    *,
    experiment_id: str,
    uid: str,
    treatment_share: float = 0.5,
    eligibility: Optional[Mapping[str, Any]] = None,
    source: str = '',
    firestore_client: Any | None = None,
) -> Optional[Enrollment]:
    """Assign ``uid`` to an arm, persist it, and record it in PostHog.

    Idempotent: a user already enrolled keeps their original variant and the
    returned ``Enrollment`` has ``newly_enrolled == False``. Callers use that
    flag to avoid re-delivering treatment on a job retry.

    Returns None when the assignment could not be persisted. That is a **hard
    failure and the caller must not deliver treatment** — an undelivered
    treatment is a lost data point, but a delivered-and-unrecorded treatment
    silently corrupts the control arm for the life of the experiment.

    The eligibility snapshot is stored because the predicate is expected to
    change over an experiment's life; without it, a later analyst cannot tell
    which rule admitted any given user.
    """
    from database._client import db

    client = firestore_client or db

    already = existing_assignment(experiment_id, uid, firestore_client=client)
    if already and already.get('variant'):
        return Enrollment(uid=uid, experiment_id=experiment_id, variant=str(already['variant']), newly_enrolled=False)

    variant = assigned_variant(experiment_id, uid, treatment_share=treatment_share)
    record = {
        'uid': uid,
        'experiment_id': experiment_id,
        'variant': variant,
        'assigned_at': datetime.now(timezone.utc),
        'source': source,
        'eligibility': dict(eligibility or {}),
    }
    try:
        # create() fails when the document exists, making the claim atomic
        # against a concurrent job run without needing a transaction.
        _assignment_ref(client, experiment_id, uid).create(record)
    except Exception:
        # Either a genuine write failure or a race we lost. Re-read: if the
        # winner already wrote an assignment, adopt it rather than failing.
        concurrent = existing_assignment(experiment_id, uid, firestore_client=client)
        if concurrent and concurrent.get('variant'):
            return Enrollment(
                uid=uid, experiment_id=experiment_id, variant=str(concurrent['variant']), newly_enrolled=False
            )
        logger.exception('experiments: enrollment write failed experiment=%s', experiment_id)
        return None

    # Emitted for BOTH arms, in the same code path, before treatment is
    # delivered. This is what keeps the holdout visible in analysis.
    emit_product_event(
        uid=uid,
        event=ENROLLED_EVENT,
        properties={'experiment_id': experiment_id, 'variant': variant, 'source': source or None},
    )
    return Enrollment(uid=uid, experiment_id=experiment_id, variant=variant, newly_enrolled=True)


def record_delivery(
    *,
    experiment_id: str,
    uid: str,
    outcome: str,
    detail: Optional[Mapping[str, Any]] = None,
    firestore_client: Any | None = None,
) -> None:
    """Attach a delivery outcome to an existing assignment.

    Descriptive only — never a filter in the confirmatory analysis. See the
    intention-to-treat note in the module docstring.
    """
    from database._client import db

    client = firestore_client or db
    try:
        _assignment_ref(client, experiment_id, uid).set(
            {
                'delivery': {
                    'outcome': outcome,
                    'recorded_at': datetime.now(timezone.utc),
                    **(dict(detail) if detail else {}),
                }
            },
            merge=True,
        )
    except Exception:
        logger.exception('experiments: delivery record failed experiment=%s', experiment_id)


def enrollment_counts(
    experiment_id: str, *, variants: Sequence[str] = (CONTROL, TREATMENT), firestore_client: Any | None = None
) -> dict[str, int]:
    """Per-arm enrollment counts, for operational monitoring only.

    Deliberately **not** an outcome query. Reading outcomes on demand is how
    peeking starts; outcomes are read on the pre-registered readout dates
    through the analysis query, not from here.
    """
    from database._client import db

    client = firestore_client or db
    counts = {variant: 0 for variant in variants}
    try:
        collection = client.collection('experiments').document(experiment_id).collection('assignments')
        for document in collection.stream():
            variant = (document.to_dict() or {}).get('variant')
            if variant in counts:
                counts[variant] += 1
    except Exception:
        logger.exception('experiments: count failed experiment=%s', experiment_id)
    return counts
