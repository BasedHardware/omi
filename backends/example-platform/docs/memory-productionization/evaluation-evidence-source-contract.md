# Authorized memory evaluation evidence-source contract

Status: P5 production-neutral source boundary, 2026-08-11

## Purpose

Supply offline/shadow evaluation with one immutable copied input without letting
the evaluator inject another account's data or arbitrary untracked bytes. This
is a sensitive internal source boundary, not a product read, model composition,
route, database adapter, or authority path.

## Source request

An already-issued `memories.experiments.shadow` context requests one closed
source kind (`formation_input_snapshot` or `authorized_graph_snapshot`), bounded
opaque source reference, and exact input frontier. The injected source adapter
must return the same owner, account epoch, source kind/reference, and frontier
with one bounded plain-JSON payload.

The facade rejects any coordinate mismatch, hostile container, oversized
payload, or wrong capability. A thrown source becomes closed
`source_unavailable`; raw error text is never retained.

## Copied input

On a valid source result, the facade detaches and deeply freezes the payload and
mints a runtime-branded `copied-memory-evaluation-input-v2`. Its digest binds:

- owner account and account epoch;
- source kind and a digest of the source reference;
- exact input frontier; and
- exact copied payload.

The raw source reference is not exposed to the replay producer or coordinator
outcome. The replay coordinator accepts only this minted object and rechecks its
owner and epoch against the current shadow authority context. Object spreading,
structured cloning, cross-owner reuse, and old v1 copied objects do not mint or
transfer authority.

## Pre-registered acceptance tests

1. Exact source bytes are detached and bound to owner, epoch, source kind/ref,
   and frontier; later caller mutation changes nothing.
2. Wrong capability, owner, epoch, kind, ref, or frontier fails before replay or
   production.
3. A forged or cross-owner copied input is rejected by the coordinator before
   result lookup or model production.
4. Not-found, serialization, stale-context, authorization, and thrown-source
   outcomes remain closed and content-safe.
5. Existing repeat, sequentiality, replay, pairing, and zero-call restart tests
   remain green under the v2 source boundary.
6. Focused/full tests, contract QA, import lint, changed-file TypeScript filter,
   and `git diff --check` pass before the unit is recorded.

## Explicit exclusions

- no PostgreSQL query, migration, pool, role grant, route, worker, scheduler,
  model, cache, filesystem loader, or runtime composition;
- no raw source reference or copied payload in evaluation pair metadata,
  telemetry, errors, or user-visible reads;
- no statistical grading, promotion, subject/bystander/privacy, identity,
  compose-voice, data-disposition, or cohort decision.

