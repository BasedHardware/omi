# Memory Continuity Gauntlet Gates

Moved out of `backend/AGENTS.md` (size ratchet:
`.github/scripts/check_agents_md_lean.py`). Read this before claiming any
canonical-memory rollout gate is satisfied.

Do not confuse these gates — a green live gauntlet does **not** prove hermetic
pipeline invariants, and hermetic tests do **not** prove deployed-backend continuity.

| Gate | What it covers | What it does **not** cover |
| --- | --- | --- |
| **Hermetic pipeline E2E** (`testing/e2e/test_canonical_memory_pipeline.py`) | capture→consolidate→promote→read, archive excluded from default reads, surface default-access matrix, projection fail-closed without legacy bleed | Deployed revision identity, prod IAM/index deltas, live LLM consolidation |
| **Gauntlet `--self-check`** | Required files, `canonical_memory_pipeline` workflow registration, suite/nonce wiring in `memory-continuity-gauntlet.py` | Any memory write or HTTP probe |
| **Live gauntlet** (`memory-continuity-gauntlet.sh` with `ADMIN_KEY` + reachable backend) | Structural `/v3/memories` probes per suite on a running backend | Full Gate 2 synthetic matrix or Gate 3 prod activation |
| **Gate 2 dev-cloud proof** (`v3_dev_cloud_proof.py` + deployed branch revision) | Multi-user synthetic matrix, indexes, IAM, auth, rollback on dev-cloud | Local hermetic fakes; not production activation |
| **Gate 3 production proof** (`docs/rollout/memory-v3-proof-order.md`) | Prod-specific deltas after Gate 2 GO + independent review | Substitute for hermetic pipeline E2E or gauntlet self-check |

CI runs `python3 backend/scripts/memory-continuity-gauntlet.py --self-check` only.
Live suites record `NOT_RUN` when credentials/backend are unavailable — never fake `GO`.
