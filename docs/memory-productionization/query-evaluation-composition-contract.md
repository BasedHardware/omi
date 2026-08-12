# Query-evaluation composition-root contract

Status: P5 production-neutral composition root plus real PostgreSQL
result/pair/grounding adapters, 2026-08-12; graph-query input adapter and
activation absent

## Purpose

Provide exactly one production-neutral construction site for the authorized
owner-query evaluation chain:

```text
authorized graph loader + reader-scoped trace codec
  -> owner-projected evidence source
  -> atomic result-plus-grounding producer
  -> sequential paired/repeated coordinator
```

The composition returns only the paired coordinator. Callers cannot obtain the
intermediate evidence source or single-result producer and cannot substitute
the generic ungrounded replay path. This is dependency assembly, not runtime
activation.

## Injected dependencies

The root accepts one exact plain configuration containing:

- the authorized owner-graph load function;
- the reader-scoped opaque trace-ref encoder;
- the sealed isolated result repository;
- the sealed atomic result-plus-grounding repository; and
- the class-blind query model callback.

Every value remains externally owned. The root reads no environment variable,
file, clock, secret, credential, database, queue, cache, network, route, or
process state. It creates no pool, retry loop, concurrency primitive, logger,
worker, server, or grant.

The outer configuration rejects extras, accessors, proxies, classes, and
missing fields before any child constructor. Child constructors then apply
their existing private-brand and callable checks. The exact dependency objects
are passed once; no wrapper may inspect or alter queries, candidates, model
results, provenance, pair rows, or outcomes.

## Construction fence

Production modules outside the three low-level implementation files and the
single registered composition root may not import:

- `memory-owner-query-evidence-source`;
- `memory-authorized-query-grounding-producer`; or
- `memory-paired-query-grounding-coordinator`.

Tests remain exempt. A dedicated import-graph path fence rejects named,
namespace, alias, side-effect, and dynamic imports by module specifier, so a
future route or worker must call the composition instead of assembling a second
path. The composition module may export only its root factory and configuration
type; it does not re-export low-level constructors or sensitive ports.

## Pre-registered acceptance tests

1. One real hermetic assembly completes one baseline/candidate pair through the
   owner source, atomic grounding stage, pair persistence, and opaque receipt;
   exact restart uses zero model calls.
2. The returned object exposes only `run`; source, producer, loader, codec,
   model callback, result repository, and grounding repository are absent.
3. Model input remains class-blind and output receipts remain free of owner,
   query, answer, evidence, trace, subject class, graph/source, strategy/model,
   response, and error content.
4. An empty owner projection completes and pairs with zero model calls.
5. Outer extras/accessors/proxies/classes and forged repositories fail at
   construction without executing a getter or dependency.
6. A planted non-test route importing each low-level module through namespace,
   alias, side-effect, or dynamic syntax makes import lint fail; imports from the
   registered root pass. Stale/renamed root paths fail the lint fixture.
7. Existing producer, source, coordinator, repository, import-graph, migration,
   broad, isolated-epoch, and `git diff --check` gates remain green.

## Pre-registered success criterion

The slice lands only if the end-to-end hermetic assembly stages one grounded
baseline/candidate pair and exact restart returns the same opaque pair ref with
zero model calls, while the import fence mechanically rejects a second
low-level composition from a non-test route. This proves assembly identity and
replay discipline only; it does not prove a production database, secret,
provider, answer, truth grade, or policy decision.

## Landed composition

`apps/service/composition/memory-query-evaluation.ts` is the sole assembly
site. It validates one exact injected configuration, requires branded result
and grounding repositories, constructs the owner source, atomic grounding
producer, and paired coordinator once, and returns only the coordinator. It
contains no environment, database, model credential, secret, route, worker,
cache, scheduler, retry, or logging behavior.

The import graph now fences all three low-level query-evaluation modules to
their implementations and this composition root. Adversarial fixtures prove a
route cannot bypass the root through named, aliased, namespace, side-effect, or
dynamic imports, and a copied composition file is rejected. Importing the root
from the same route fixture passes.

The end-to-end hermetic test staged one finalized grounded baseline/candidate
pair and returned one opaque receipt; exact restart returned the same pair ref
with zero model calls. The returned object exposes only `run`, model input stays
class-blind, and an empty owner projection pairs with zero model/codec calls.

Verification: 3 focused composition tests passed; composition plus coordinator
passed 11 tests with 80 expectations; the full source/producer/coordinator/
repository/migration chain passed 54 tests with 1,380 expectations. The import
fence suite passed 18 tests with 43 expectations. The broad platform gate
passed 1,293 tests with 9,406 expectations across 178 files, and the isolated
epoch gate passed 18 tests with 141 expectations. The first post-broad epoch
attempt cleared one known dangling test process and timed out in cleanup; its
immediate isolated rerun passed. Import graph and diff checks passed; the known
occupied fixed-port dev-server test remained excluded.

## Explicit exclusions

- no concrete PostgreSQL graph-query input adapter or query-input migration;
- result, pair, and atomic result-plus-grounding PostgreSQL adapters are landed
  and real-database qualified but remain route-free and inactive;
- no production codec root, model credential, API-key scheduler, worker, route,
  grant, cache, Listen mapping, deployment, or traffic;
- no statistics, contamination conclusion, blind sheet, human grading request,
  promotion, default, or cohort action;
- no `subject:*`, bystander/privacy, identity authority, compose voice, or data
  disposition change.
