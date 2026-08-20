# Memory ingestion architecture

This package is an isolated benchmark and evaluation surface for memory extraction. It is not the production memory persistence path.

## Flow

1. `cli.py` and `adapters/offline_input.py` load and write JSON or JSONL pipeline fixtures.
2. `CoreMemoryPipeline` in `pipeline.py` validates input, calls a `MemoryModelClient`, normalizes frames, applies redaction and evidence rules, and compiles bounded mutation plans.
3. `stages/verify_output.py` applies grounding, confidence, duplication, and active-create checks before output is accepted.
4. `adapters/production_like_model.py` provides the production-shaped model client used by offline evaluation; the default stub remains deterministic for hermetic tests.
5. `rollout.py` contains graph migration, legacy projection, parity-diff, and benchmark comparison helpers.

## Boundaries

- The package returns typed pipeline and mutation artifacts; it does not write production memory state.
- `redaction.py` must run before diagnostic payloads or model traces leave the pipeline.
- Stable IDs and fingerprints come from `ids.py`; callers must not invent parallel identity schemes.
- Changes to mutation semantics require pipeline regression coverage and parity evidence for the legacy projection.
