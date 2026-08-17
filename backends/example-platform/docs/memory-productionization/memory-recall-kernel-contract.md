# Shared memory recall kernel contract

Status: production-neutral core response contract plus dark composition root;
no HTTP/MCP route or activation (2026-08-13).

## Purpose

One kernel for the ratified first-cohort query product:

```text
question in -> grounded answer + citations + typed completeness out
```

`GET /v1/memories` remains the paginated collection. This kernel is the future
`GET /v1/memories/query` (name TBD) and MCP query tool surface, sharing auth
grants and completeness bytes across doors.

## Core

`core/retrieve/memory-recall-kernel.ts` defines `memory-recall-kernel-v1`:

- bounded question digest binding;
- grounded answer text or explicit `query_gap` absence;
- ordered assertions with grounded `tr1_` citations;
- `recall-completeness-v1` envelope (complete / incomplete / degraded / partial).

## Composition

`apps/service/composition/memory-recall-kernel.ts` is the sole assembly site
over the existing authorized query-grounding producer. It returns only the
kernel `answer` operation; routes and MCP tools must call this root.

## Deliberate production gap

No route, MCP tool registration, model default, dream gate bypass, or cohort
activation. P5 shadow evaluation machinery remains separate from product doors.
