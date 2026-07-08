# INV-MEM-1: Exactly three product memory tiers

**Status:** locked
**Statement:** Product memory has exactly three tiers — `short_term`,
`long_term`, and `archive` — with one canonical product-memory collection and a
default access policy of Short-term + Long-term.

## MUST NOT

- Invent additional user-visible product tiers (e.g. “context-only” as a tier).
- Create separate canonical Short-term and Archive collections.
- Make Archive part of default chat/agent/MCP/third-party memory access without
  an explicit Archive operation and applicable policy.

## Surfaces

- Backend memory APIs and storage
- Chat / agent / MCP memory retrieval
- Mobile and desktop memory UI (tier labels, filter, provenance, delete)

## Guard tests

- Normative architecture and domain model are the contract; backend unit/contract
  tests that pin tier vocabulary and default access must stay green when those
  paths change. See linked docs for the authoritative schema and policy.

## Path globs

- `docs/epics/memory_normative_architecture.md`
- `docs/memory/**`
- `backend/database/memories.py`
- `backend/database/memory_*.py`
- `backend/database/product_memory_items.py`
- `backend/database/short_term_memories.py`
- `backend/utils/memory/**`
- `backend/utils/memory_ingestion/**`
- `backend/utils/mcp_memories.py`
- `backend/routers/memories.py`
- `backend/routers/memory_*.py`
- `app/lib/pages/memories/**`
- `app/lib/backend/schema/memory.dart`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoryGraph/**`
- `desktop/macos/Desktop/Sources/MemoryExportService.swift`
- `desktop/macos/Desktop/Sources/MemoryBankConnector.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/MemoryStorage.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/MemoryModels.swift`
- `web/app/src/components/memories/**`
- `web/app/src/lib/memoryExport.ts`
- `web/frontend/src/components/memories/**`

## PR rule

Name `INV-MEM-1` in the PR body if you touch the path globs above.

## Canonical docs (do not duplicate)

- [`docs/epics/memory_normative_architecture.md`](../../epics/memory_normative_architecture.md)
- [`docs/memory/domain_model.md`](../../memory/domain_model.md)
