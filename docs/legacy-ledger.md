# Legacy ledger

Proposed fates only. David ratifies later. This lane deletes nothing.

Each row is one legacy-compatibility touchpoint still present in platform.
The mechanical check is the proof that production kernels do not value-link
the touchpoint; rule 18 (`bun run lint:closure`) covers several of them.
Rule 18 is an import-closure fence. It does not inspect `fetch` URLs or
observe which host a running process contacted; that gap is
[`docs/network-fence-proposal.md`](network-fence-proposal.md).

| Touchpoint | What it is | Why it exists | Proposed fate | Gate before deletion | Mechanical check |
| --- | --- | --- | --- | --- | --- |
| Legacy Firestore memories generation | Account-lifecycle value `account_generation: "legacy"` plus the Firestore `users/{uid}` tree scanned by the P7 cleanup participant (`legacy_generation_data` / `legacy_user_tree`). Application admission denies `account_generation_legacy`. | Pre-cutover accounts still have Firestore-owned memory trees. PostgreSQL is not yet the sole live store for those accounts. | `delete-after-cohort` | David ratifies that the last live `legacy` cohort has migrated or been terminal-deleted; restore/rollback windows have closed; the Firestore participant has run to physical-zero on a qualified production fence. | `bun run lint:closure` on `drivers/postgres/firebase-authorized-memory-service-process.ts` and `firebase-authorized-memory-service-app.ts` (must not value-link Firestore client code or `apps/qa`). Schema static test forbids a `legacy_memories` collection grant. |
| Legacy MCP cursor prefix `mcp1` | HMAC cursor grammar in `apps/mcp/cursor.ts` (`CURSOR_PREFIX = "mcp1"`). Opaque pagination tokens on the MCP door. | Live MCP clients redeem `mcp1.` cursors. Changing the prefix would invalidate every outstanding cursor. | `keep-under-legacy-prefix` | A dual-prefix reader has shipped, a cohort has aged out of `mcp1` TTL (max 86400s), and David ratifies dropping the old encoder. | `apps/mcp/bun-http.ts` is a rule-18 entrypoint and must stay green. Cursor tests assert `mcp1.` encoding; they are the compatibility ratchet, not a production link of QA. |
| Legacy MCP API-key prefix | Dev-token adversarial fixture `mcp1.{keyId}.{payload}.{signature}` (rejected) and live MCP key records' `key_prefix` (`omk_live` in the inert PostgreSQL adapter). The adapter does not mint a new token grammar and does not migrate live Firestore keys. | Shipped MCP keys and QA tokens used a prefix-shaped secret. The PostgreSQL adapter stores a prefix + hash so list/revoke can work without re-minting. | `keep-under-legacy-prefix` | Firestore MCP keys are migrated or revoked; David ratifies a new mint grammar; the inert adapter is replaced by a live mint that still verifies old prefixes during overlap. | Rule 18 on `apps/mcp/bun-http.ts`. `apps/service/stores/mcp-credential-adapter.ts` is composition, not a production entrypoint; it must not appear on the three rule-18 closures. |
| Legacy action-items compatibility | Dated, feature-frozen `/v1/action-items` family in `apps/service/routes/action-items-compat.ts`. Historical authority: `backend/routers/action_items.py`. | Shipped Tasks adapters still call the five frozen invocations. New Tasks work belongs on `/v1/tasks` and `/v1/tasks/ops`. | `delete-after-cohort` | David ratifies the Tasks platform generation and its real-account migration/default flip (the file's own deletion trigger). | `apps/service/routes/action-items-compat.test.ts` is the compatibility ratchet. Production entrypoints in rule 18 must not grow a value-import of this route family unless a production process actually serves it. |
| `apps/qa` | QA seed, deterministic synthesizer, recall-service, cursor bindings, loopback, and model-fake renders (`createQaDeterministicSynthesizer`). | Hermetic proofs for the memory read path and both doors. Previously leaked onto the production import graph via `apps/service/composition/memory-read.ts`. | `dev-only` | No production entrypoint value-imports `apps/qa`. Local/QA composition may keep using `apps/qa/memory-read-bindings` behind the SQLite QA binary only. | Rule 18 forbids substring `apps/qa` on the three production closures. Negative control is `drivers/sqlite/dream.ts` (must exit 1). |
| SQLite drivers | `drivers/sqlite/**` including `dream.ts`, service stores, and the local QA database. | Local/QA binary, hermetic tests, and the offline dream cycle. Not production memory authority. | `dev-only` | PostgreSQL is the only production memory authority; the local binary remains SQLite QA until David says otherwise. Do not delete while `bun test` still needs it. | Rule 18 forbids substring `drivers/sqlite` on the three production closures. `drivers/sqlite/dream.ts` is the negative control (exit 1). |
| Local test gateway | Disclosed hermetic LLM-gateway fake used by Chat gateway tests (`createGatewayChatGenerationSource` with an injected `fetch`). Not a scripted `dev-server` chat source; the registered server uses the real gateway adapter or fails closed. The path `integration/local-test-gateway` is reserved by rule 18 and is not present as a tree in this join. | Gateway integration tests must put their fake provider behind the real gateway request boundary so product code never claims a live model. | `dev-only` | No production entrypoint value-imports `integration/local-test-gateway`. Dev-server Chat remains gateway-required (`createGatewayRequiredChatGenerationSource` when unset). | Rule 18 forbids substring `integration/local-test-gateway`. `apps/service/bin/dev-server-structure.test.ts` asserts the registered server never defaults to a scripted source. |
| `harness/` | Evaluation/pipeline harness workspace package. | Offline evaluation runs. Must not ship in a production image. | `dev-only` | Evaluation corpora stay machine-local and gitignored. Production images are built from the rule-18 closures. | Rule 18 forbids substring `harness/`. |
| `spikes/` | Exploratory patches and tradeoff notes, not product code. | Design history. Must not be linked from production. | `dev-only` | Never imported from `apps/`, `drivers/postgres/`, or `apps/mcp/`. | Rule 18 forbids substring `spikes/`. |
| GLM model driver | `drivers/model/glm.ts`, previously value-imported from predicate-batch consolidation. | Local/QA model client. Must not ride into a production memory-service image. | `dev-only` | Predicate-batch production composition uses a production model port, not GLM. | Rule 18 forbids substring `drivers/model/glm`. Negative control: `drivers/sqlite/dream.ts` currently links it (exit 1). |
| Legacy Chat context strings | `ChatGenerationContextResult` still accepts `readonly string[]`, normalized into a packet with `sourceKind: "legacy"`. | Older adapters and tests passed bare strings. The joined supervisor normalizes them before the provider. | `delete-after-cohort` | Every remaining `ChatGenerationContextSource` returns a packet; the union of tests no longer constructs a string-array context except the dedicated normalizer test. | Packet tests in `apps/service/chat/generation-context.test.ts`. Production closures do not mention this type. |

## Rule 18 command

```text
bun run lint:closure
```

Ratified entrypoints (David-only to change):

- `drivers/postgres/firebase-authorized-memory-service-process.ts`
- `drivers/postgres/firebase-authorized-memory-service-app.ts`
- `apps/mcp/bun-http.ts`

Forbidden substrings: `apps/qa`, `drivers/sqlite`, `drivers/model/glm`,
`integration/local-test-gateway`, `harness/`, `spikes/`.

Negative control (must exit 1): `bun run scripts/trace-value-imports.ts drivers/sqlite/dream.ts` with the same `--forbid` list.
