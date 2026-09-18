# Memory ingestion — package map

Benchmark and eval extraction surface, not product runtime. Product extraction
and persistence live in `utils/llm/memories.py`, `utils/llm/working_observations.py`,
and `utils/memory/`. This package must not own HTTP routes, Firestore writes, or
request-scoped BYOK credentials.

The only inbound edge from outside this subtree is
`migrations/007_genesis_ledger_backfill.py`, which imports rollout helpers for
offline genesis-ledger backfill.

## Module map

- `__init__.py` — public exports (`CoreMemoryPipeline`, config, I/O models). Must not import routers or database.
- `config.py` — default `MemoryPipelineConfig`. Must not construct clients or I/O.
- `models.py` — pydantic pipeline I/O (`MemoryPipelineInput`/`Output`, frames, mutations). Must not call LLMs or persist.
- `ids.py` — `stable_hash` / `stable_hmac` / `StableIdFactory` / `edit_distance`. Pure; must not I/O.
- `pipeline.py` — `CoreMemoryPipeline.run` plus stub/protocol model clients. Orchestrates stages; must not talk to production memory stores.
- `redaction.py` — `redact_text` / `redact_payload` secret scrubbing. Must not log raw secrets.
- `source_routing.py` — passthrough `route_source` provenance (`SOURCE_ROUTER_VERSION`). Must not change effective source type yet.
- `cli.py` — `memory-ingestion run` offline CLI. Must not start the FastAPI app.
- `rollout.py` — graph/legacy write-read flags, genesis-ledger backfill helpers. Must not flip production `MEMORY_MODE`.
- `rollout_cli.py` — `memory-rollout` benchmark/parity CLI. Must not write Firestore.
- `export_runner.py` — offline export-dataset replay into the pipeline. Must not be imported by request handlers.
- `stages/__init__.py` — stages package marker.
- `stages/verify_output.py` — grounding/confidence lints on `MemoryPipelineOutput`. Must not mutate pipeline input.
- `adapters/__init__.py` — adapters package marker.
- `adapters/offline_input.py` — JSON/JSONL pipeline I/O. Must not call production APIs.
- `adapters/production_like_model.py` — `ProductionLikeMemoryModelClient` for benchmark runs. Must not persist extracted memories.
- `adapters/typed_extraction_prompt.py` — typed-predicate extraction prompt. Must not add extra model calls.
