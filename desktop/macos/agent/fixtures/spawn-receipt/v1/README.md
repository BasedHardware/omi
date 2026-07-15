# Spawn receipt fixtures (schema v1)

Cross-language contract for realtime `spawn_agent` results:

- **Producer:** `desktop/macos/agent/src/runtime/agent-spawn-journal.ts` → `compactRealtimeSpawnToolResult`
- **Consumer:** Swift `RealtimeSpawnJournalReceipt.parse` (currently in `RealtimeHubController.swift`)

## Rules

- `v1/` fixtures are immutable. Never edit a checked-in v1 JSON file to “fix” a test; add a new fixture or open a v2 directory.
- Adding schema `2` means creating `../v2/` with its own valid + malformed set; keep v1 until the producer stops emitting it.
- Tests compare **decoded semantic values**, not byte-identical JSON (key order / whitespace are not protocol).

## Files

| File | Expectation |
|------|-------------|
| `valid-running.json` | Swift parse accepts; Node emitter must match semantically for the same descriptor |
| `malformed-*.json` | Swift parse returns `nil` without crashing |
