# Attribution-belief shadow producer contract

Status: implemented, inert, shadow-only

The attribution-belief shadow producer makes the existing probabilistic
attribution kernel runnable through the isolated offline experiment plane. It
does not write authoritative beliefs and is not composed into a route, worker
poller, promotion path, memory read, or product answer.

## Input and strategy binding

The copied input is a strict `attribution-belief-shadow-input-v1` payload. It
contains only modality-neutral belief coordinates, opaque observation and
evidence references, exact digests, hypotheses, dependency groups, event time,
and an optional prior belief revision. It cannot provide a calibration
contract.

The minted `identity_cluster` strategy supplies the calibration contract via
its complete execution-contract digest. The producer accepts only the exact
`attribution-belief-shadow-result-v1` result contract. Copied input integrity,
owner, and graph frontier are checked before the calibrator is resolved.

## Calibration and result

The injected calibrator receives the core content-safe calibration request:
owner identity is replaced by an owner-scope digest and no observation text is
present. The existing core validates one complete integer-micro probability
distribution and produces an immutable belief revision plus calibration
receipt.

The producer returns only that belief and receipt. The generic memory
evaluation repository binds the result to the account epoch, copied input,
strategy assignment, evaluation role, run, and repeat. It provides exact
replay/conflict behavior and durable baseline/candidate pairing. An exact
rerun loads persisted results and makes no calibrator call.

## Closed failures

Malformed or mismatched copied input, ineligible strategy, missing calibrator,
and calibrator dependency failures return `dependency_unavailable`. A
malformed probability response returns `model_response_invalid`. Provider
messages, observation text, and owner identifiers are never copied into these
failure outcomes.

## Nonclaims

This unit does not select a calibrator, model, threshold, wording class,
modality adapter, source/subject policy, retention policy, runtime credential,
route, cohort, or activation. It does not weaken typed identity authority or
the mention-local fail-closed path. Held-out calibration, blind zero-wrong
grading, harder-sheet gains, and David's activation gate remain required.
