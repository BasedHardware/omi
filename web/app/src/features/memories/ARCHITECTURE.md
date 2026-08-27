# memories

Destination `/memories`. Product tiers: **INV-MEM-1** (`short_term`, `long_term`, `archive`).

- `api.ts` — memory CRUD and knowledge graph
- `memoryCategory.ts` / `memoryExport.ts` — pure helpers
- `insights.worker.ts` — off-main-thread insights
- `ui/` — list, filters, graph, dashboard
- `useMemories.ts` — signal store; category filter, IndexedDB hydrate, and chunked bulk delete are unchanged (**INV-MEM-1**)
- `useKnowledgeGraph.ts` / `useInsightsDashboard.ts` — signal stores; graph colors stay in the hook file (INV-UI-1 ratchet)
