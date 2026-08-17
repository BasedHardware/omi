# Product conflict reference contract

Status: P4 invariant-level preregistration, 2026-08-11

## Purpose

This contract implements only the conflict invariants accepted by ADR-006,
ADR-013, WS-007, and FEAT-MEM-004. It defines a strict immutable conflict
occurrence over stable product propositions and an attributable resolution
input that preserves the original alternatives.

It deliberately does not choose the still-open public status/revision
vocabulary, conflict-display policy, user-legible provenance, resolution
control, route, persistence authority, or UI. The types are internal
production-neutral records, not a shared wire.

## Conflict occurrence

An occurrence is owner-local and content-addressed. It contains a sorted,
duplicate-free set of at least two stable proposition ids, one exact graph
frontier, detector-contract and basis digests, and an event time.
The record also binds a canonical digest of the exact normalized alternative
identity snapshot at that frontier. That digest is structural replay
provenance, not authorization.

It has no winner, selected alternative, confidence, score, snippet, model
output, or display status. Constructing an occurrence does not make it visible,
durable, or usable by retrieval. Future usage gating remains part of the
authorized consolidation/product integration.

All supplied proposition identities are reparsed through the existing product
projection contract. Group ids, unknown propositions, and cross-owner
identities are invalid.

## Resolution input

A resolution input references one exact occurrence, copies its immutable
original alternatives, and records a non-empty explicit proposition set plus
an opaque attributable operation reference and resolution-contract digest.
It also binds a canonical digest of the exact normalized proposition/redirect
snapshot that produced the terminal set. Replay must load that historical
snapshot rather than validating against whatever redirect head is current.

Proposed resolved ids traverse the existing bounded owner-local redirect graph
before they enter the record. The explicit stored set therefore names terminal
stable propositions, never a grouping projection. Cyclic, dangling,
cross-owner, excessive-depth, or excessive-fan-out redirect state fails closed.

This record is only an input to a future authorized apply/consolidation
operation. It cannot mutate claims, mark a conflict resolved, or bypass durable
work and account/lifecycle fences by itself.

## Replay, safety, and authority

- Occurrence and resolution-input ids hash every immutable field.
- The reference-snapshot digest hashes the declared frontier and exact sorted
  normalized identity/redirect rows used by the constructor.
- Attributable operation references use only the closed
  `opref1_<64 lowercase hex>` grammar; arbitrary printable content is rejected.
- Exact replay is byte-identical; changed alternatives, frontier, contract,
  basis, attribution, result, or event time produces a different id.
- Parsers accept exact plain data only and bound every string and array.
- Diagnostics contain closed codes only and never include proposition content,
  evidence, source paths, model output, or provider errors.
- Core has no detector, model, store, clock, network, filesystem, environment,
  grant, issuer, or mutation capability.

## Explicit gates

- David decides conflict behavior under partial reader authorization and the
  exact user-facing provenance/control policy.
- A shared wire, route, UI, public lifecycle, repository, PostgreSQL schema,
  worker, and real-user activation require separate contracts and gates.
- Search materialization remains blocked on a ratified service/owner projection
  subject. One reader/app-relative grant must not define a shared durable index.
- Bystander privacy, `subject:*`, compose voice, Listen/speaker authority, data
  disposition, RPO/RTO, blind grading, and cohort policy are unchanged.

## Acceptance

Tests must prove deterministic occurrence and redirect-aware resolution input,
no winner field, original-alternative preservation, merge and split terminal
sets, strict owner/non-dangling/group exclusion, replay identity, closed errors,
hostile plain-data rejection, and bounded inputs. Focused, broad, epoch,
contract, import, strict changed-source TypeScript, and diff gates must pass
before the implementation is recorded.
