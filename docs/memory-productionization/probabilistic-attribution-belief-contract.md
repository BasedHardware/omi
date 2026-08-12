# Probabilistic multimodal attribution belief contract

Status: ratified architecture; implementation and activation pending

Decision: David, 2026-08-12 America/New_York

## Purpose

Noisy observations must not be forced into `owner | discard`. Omi processes
policy-eligible evidence broadly, retains exact provenance and uncertainty, and exposes
calibrated beliefs without encoding action consequences. This contract applies to
speech, OCR, images, imported records, and future modalities.

## Separate coordinates

The implementation must not collapse these coordinates:

1. deterministic account lifecycle, retention, policy, and reader authorization;
2. immutable observation and decoder provenance;
3. probabilistic source attribution;
4. probabilistic claim-subject attribution;
5. probabilistic claim truth; and
6. separately composed presentation and agent/action policy.

A probability cannot grant access or defeat deletion. Access remains fail-closed and is
revalidated before selection and release. Conversely, an authorized reader does not make
an uncertain observation true or owner-attributed.

## Belief revision

A canonical attribution-belief revision must bind its account, exact observation/content
digest, candidate hypotheses including unknown, support and counter-evidence refs,
independence groups, prior revision, graph frontier, ambiguity/conflict markers, model and
calibration contracts, and calibrated probability or empirical band. It is immutable and
content-addressed; later evidence appends a new revision.

The aggregator may strengthen or weaken belief from related evidence only when provenance
establishes how the factors depend on one another. A transcript, extraction, summary,
projection, repeated model judgment, and answer derived from the same observation cannot
be counted as independent confirmations. The exact independence accounting and calibrator
are versioned strategy inputs and remain shadow-only until held-out evaluation.

Authenticated user confirmations, rejections, and revocations are strong attributable
evidence but never rewrite the observation. Device possession, capture enrollment,
`is_user`, diarization, voice similarity, first-person grammar, profile consistency, OCR
confidence, and model/frame outputs are evidence factors, not certainty by themselves.

## Presentation and agent use

An external read/presentation policy may map calibrated belief to classes such as:

- `owner_direct`: direct `you/your` wording;
- `owner_qualified`: `you probably/likely` or equivalent calibrated uncertainty;
- `source_attributed`: `someone in this conversation` or `the document says`;
- `clarification_required`; or
- `abstain`.

An uncertain owner attribution must never be rendered as certain. Thresholds are learned
from fresh held-out data, not embedded in this contract. The memory layer returns the same
belief and provenance regardless of the caller's intended consequence. Approvals,
permissions, confirmations, and side-effect rules belong to the consuming product,
agent, or action layer and may evolve without a memory migration.

## Shadow boundary

Shadow is a bounded calibration and rollout mechanism, not permanent uncertain storage.
It runs the complete candidate belief pipeline on finalized, policy-eligible observations
without changing authoritative memories or product answers. Promotion requires frozen
machine gates, repeated read evaluation where applicable, blind truth grading, calibrated
coverage/error evidence, and a new strategy coordinate. Shadow retention remains
controlled by separately ratified privacy and disposition policy.

## Bystander and third-party retention

Policy-permitted third-party observations may enter the owner's private authoritative
memory graph after shadow qualification. They retain their actual or unknown subject,
source provenance, calibrated uncertainty, citations, and restrictive policy labels. They
may support qualified private recall but never silently become owner facts.

This does not weaken capture policy or authorize public sharing, cross-account disclosure,
or a probability-based grant. Exact internal subject vocabulary may evolve, but grammar,
device possession, profile similarity, or a derived model result cannot erase the actual
or unknown third-party subject.

## Compatibility and migration

The current mention-local/source-local fail-closed path remains unchanged until this
belief contract is implemented and qualified. Existing typed identity authorization is
not weakened or reinterpreted as a probability in place. The new belief layer is additive,
versioned, and initially shadow-only. Legacy evidence is not rewritten; it may receive new
attribution hypotheses only as separately versioned derivations with original provenance.

## Acceptance boundary

Before activation, tests and held-out evaluation must prove:

- exact replay and changed-input conflict for every belief revision;
- cross-account, stale-frontier, deletion, and unauthorized support rejection;
- dependency-aware aggregation with no derivative/self-confirmation gain;
- counter-evidence, correction, revocation, and contradiction can lower belief;
- an external wording policy is deterministic for the same belief/policy coordinates;
- no unauthorized or hidden support affects score, ranking, wording, timing, or presence;
- uncertainty calibration and coverage on fresh modality-specific data; and
- zero confidently wrong owner answers on the standing blind floor without collapsing
  useful correct/partly recall.
