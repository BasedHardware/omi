# Backend-authoritative memory platform

Omi's backend is the authority for personal memory. Clients, local capture apps, and MCP adapters are consumers or replicas; none of them is a second durable writer.

## Authority boundary

The canonical backend store is the per-user Firestore `memory_items` collection and its apply-control commit chain. A committed memory transition receives its ordering from the backend. Search indexes, compatibility projections, vector indexes, local SQLite databases, and MCP responses are rebuildable or read-only surfaces.

The older fact ledger remains a legacy projection path. New platform integrations use `MemoryService`, canonical visibility policy, and the canonical apply boundary. They must not write `memory_items`, commit records, or projection rows independently.

## API and MCP

The REST capability endpoint is `GET /v1/memory/platform`. It is authenticated with the normal Omi user session and identifies the authority, canonical store, supported API and MCP surfaces, and the local-replica contract.

The hosted MCP server exposes the same contract through the `memory_platform` read tool. Memory reads and writes continue to use the existing scoped MCP tools; the capability tool is discovery only and never returns memory content or credentials.

## zkr boundary

`zkr` is a suitable local evidence-backed replica because its `MemoryDb::apply` path accepts caller-supplied records and its export cursor is bounded by a stable high-water mark. In this platform:

- the backend assigns authoritative ordering;
- local zkr data is a mirror or pending capture buffer, not the authority;
- a replica may apply only backend-acknowledged records;
- retrieval remains evidence-cited and tenant/person scoped;
- retries must be idempotent and conflicting payloads must be rejected.

The capability payload advertises this relationship without pretending that a full zkr transport is already enabled. A transport that accepts pending zkr records must route them through backend ingestion and the canonical apply boundary before exposing them as authoritative memory.

## Ambient capture integration

The Context for Claude design can use the existing capture and onboarding work, but its MCP process should call Omi's backend authority. Its local database may cache capture state or hold pending upload material; it must not become a parallel memory authority. Backend upload, canonical processing, and the existing MCP authorization model determine what is available to an agent.
