# PostgreSQL Listen attribution-belief one-shot contract

Status: implemented as a route-free, timer-free shadow-evaluation runtime.
It is invoked explicitly and has no production activation surface.

## Purpose

This runtime closes the restart-safe measurement path from a persisted Listen
attribution input to the existing isolated experiment tables. A caller supplies
one already minted baseline/candidate identity-cluster assignment, an opaque
evaluation run coordinate, a bounded repeat count, and an injected calibrator
resolver. The runtime selects no strategy, model, calibrator, probability,
threshold, or product wording.

## Execution and replay

The source input is loaded through the sealed PostgreSQL belief-input
repository under `memories.experiments.shadow` authority. Its exact input ref
and graph-frontier digest must match. The existing offline replay coordinator
runs one baseline and each assigned candidate for each requested repeat,
sequentially, and records exact baseline/candidate pairs in the isolated
experiment plane.

Strategy definitions, policy, assignment bundle, results, and pairs are
content-bound. An exact rerun loads the stored results and performs zero
calibrator calls. Changed run, assignment, input, frontier, result, or response
coordinates cannot silently reuse prior work.

## Safety boundary

The result returned to the caller contains only content-safe pair coordinates,
model-call counts, reuse counts, and closed stop codes. It contains no
transcript, factor payload, calibrated distribution, provider error, prompt, or
answer. The runtime never writes a canonical attribution belief, graph
revision, identity authorization, product projection, or user-facing answer.

Construction opens no database connection and resolves no calibrator. Strict
plain-data parsing rejects proxies, accessors, unbounded repeats, unminted
assignments, and malformed coordinates before the source read.

## Qualification

The real PostgreSQL 18.4 gate starts from a finalized Listen session, persists
its accepted formation and text-free attribution input, runs two paired
repeats, observes four injected calibrator calls, then reruns with four reused
results and zero additional calls. It verifies two baseline rows, two candidate
rows, two pairs, content-free output, and transaction-time grant revocation
before the source read. The same migration/runtime corpus runs under pinned Bun
1.3.14 and Node 24.19.0 controls.

## Explicit nonclaims

This is evaluation infrastructure, not a chosen candidate. It does not claim
that a calibrator is accurate, select owner-belief thresholds, aggregate across
sessions or modalities, grade truth, activate a worker, expose a route, or
change current memory admission/read behavior. Candidate selection still
requires paired measurement and the ratified blind human gate.
