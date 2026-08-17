# TRADEOFF MEMO: Authorized application context

Status: disposable draft; not applied to runtime.

## Purpose

The draft explores a module-branded, frozen authorization context created only
after an exact persisted per-application/key grant lookup. It carries content-
free identity and generation digests for cursor replay and final-read fencing.

The follow-up patch closes a review finding by rechecking credential expiry
after the grant lookup and before any store callback.

## Why it is not integrated

Published rulings require independent authenticated scope plus an exact
persisted per-application/key grant. They do not yet define the proposed
principal identity, credential generation, grant version/lifecycle,
authentication strength/expiry, or branded context authority. Those choices
exist only in unpublished ADR-010 material.

Integrating the draft would therefore choose an open authority model.

## Evidence

- Focused authorization and projection tests: 42 passed.
- Independent review found the expiry-after-lookup race; patch 0002 repairs it.
- No production adapter, migration, deployment, or deletion is included.

## Decision needed

David must publish or replace ADR-010's authority model. After that decision,
apply both patches in order, reconcile them with the current application-read
API, rerun all gates, and obtain a new exact-commit review.

