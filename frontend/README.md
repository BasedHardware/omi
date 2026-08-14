# core/ — the shared product core

This directory is the new world. Everything under `core/` is post-migration code: the
shared TypeScript product core (domain logic, sync layer, view models, shared surfaces),
the contracts that define every seam, and the codegen that turns contract drift into
build failures. The old client trees (`app/`, `desktop/`, `web/`) are being strangled by
this directory, one surface and one domain at a time, and deleted as they hollow out.

Program tracker: `omi-frontend-unification-and-microapps-project-tracker` (WS-002 owns
this directory's shape; ADR-002/004/005/006/007/008 govern its architecture).

## The three isolation rules (CI-enforced, no exceptions)

1. **`core/` never imports old code.** Not a helper, not a type, not "temporarily". If
   `core/` needs something the old tree has, the knowledge is re-expressed here (usually
   in `packages/adapters-legacy/`) with the old code as reference only.
2. **Old code touches `core/` only through published entry points** (bridge bindings and
   package public APIs). Every such call site in the old tree carries a `core-seam:`
   marker comment, so per-surface cutover progress is a single grep.
3. **All old-backend knowledge lives in `packages/adapters-legacy/`.** Domain and sync
   code target the contracts; adapters make today's backend impersonate them. This
   directory is the designated graveyard — it only ever shrinks, and its deletion is the
   definition of "migration finished".

## Directory map

- `contracts/` — the single source of truth: domain schemas, wire schemas (`/listen`,
  entitlement payload, chat write contract), bridge interfaces, the error taxonomy, the
  id/slug grammar. Pure declarations; no runtime code.
- `codegen/` — generators consuming `contracts/`: TS types, Dart/Swift bridge stubs,
  conformance fixtures. Generated output is committed; CI regenerates and fails on diff.
- `packages/domain` — entities, domain rules, view models. Pure TS, dependency-free.
- `packages/sync` — the ADR-004 layer: durable outbox, projections, reconcile, behind
  `DurableLog`-shaped storage bridges. Never assumes browser storage is durable.
- `packages/adapters-legacy` — see rule 3.
- `packages/surfaces` — shared UI, hosted per ADR-008 (webview on mobile/macOS,
  in-process on Windows, direct on web).
- `packages/testkit` — hermetic harness, failure-class suites (the 15 classes in
  `docs/client-failure-classes.md` of the tracker), conformance corpora.
- `shells/` — new per-platform hosting code (loopback server, webview mounting, bridge
  bindings). The thin patches inside the old apps that *mount* these are the only new
  code allowed to live outside `core/`, and they carry `core-seam:` markers.

## The dual-migration rule

The backend is being rewritten concurrently, pivoting on the same `contracts/`. **Per
domain, only one end of the wire moves at a time**, and the domain's contract is
ratified before whichever side moves first. "The new backend is ready for domain X"
means X's conformance fixtures pass against it — a green suite, not a judgment call.

## For agents working here

- The exemplar to imitate is the tasks slice (`packages/domain/src/tasks`,
  `packages/sync`, `adapters-legacy/src/tasks`, `surfaces`). Copy its patterns; do not
  invent parallel ones.
- Old code is reference material, never an import. When old and new behavior disagree,
  the contract wins; if the contract is silent, stop and surface it — do not decide.
- Every fallback path emits telemetry (`Degraded<T>` — the compiler enforces this;
  do not weaken types to route around it).
- Ids: accept `legacy-UUID | slug` everywhere; generate slugs only (ADR-006).
- Tests are hermetic: no network, no wall clock, no real filesystem outside the harness.
