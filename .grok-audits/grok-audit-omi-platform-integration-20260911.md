# Audit: omi-platform-integration

**Date:** 2026-09-11  
**Checkout:** `/Users/undivisible/projects/omi-platform-integration`  
**HEAD:** `e4d85d7b` (`codex/track3-backend-integration`, 2026-08-11)  
**Remote:** `https://github.com/Git-on-my-level/omi-platform.git`  
**Lag:** local is **0 ahead / 1848 behind** `origin/codex/track3-backend-integration`  
**Mode:** read-only recon. No push, force-push, merge, deploy, delete, or `make sync`/`make up`. Tests were not executed.

**CS: 8.** Architecture, auth, HTTP/MCP/WS, lint fences, and git metadata were read in source. Residual uncertainty: the 1848-commit lag means origin may already have fixed some items; GitHub branch protection is not visible from this clone; exact `bun test` case count was not re-run (`Agents.md` still says 265).

---

## 1. Overview

This repository is the **TypeScript/Bun rewrite of omi’s memory kernel** plus a **loopback app-facing HTTP service** for macOS/iOS dogfood. Package name: `omi-placement-platform`. Decisions are **not** made here.

| Layer | Role |
|---|---|
| `core/` | Pure contracts: ingest, ledger, STM, resolve, consolidate/dream, retrieve, grants, write-fence, account-control |
| `drivers/` | SQLite adapters + model ports (GLM, Codex, fake, verdict cache) |
| `harness/` | Offline Stage A pipeline (corpus → extract → STM → dream → graph/recall) |
| `apps/service/` | Canonical Hono REST/WS service, port **4851**, `127.0.0.1` only |
| `apps/mcp/` | Stateless MCP 2026-07-28 JSON-RPC (`read_synthesized_memory`) |
| `apps/qa/` | QA MCP server, port **4801**, shares the memory-read composition |
| `integration/` | Live-socket adversarial tests (hidden-vs-absent, cross-door identity, epoch fence) |
| `contract-tests/` | Vendored `@omi-core/ratified-contracts` 0.8.0 conformance |
| `scripts/` | Import-graph security lint, lockfile QA, network publication verify |
| `spikes/` | Unapplied patches (ADR-010 auth context, MCP reauthorization) |
| `vendor/` | Locked contract tarball + listen protocol schema |

**Not in this repo (looked, absent):** Firestore rules, Firebase Admin, OAuth token storage, BYOK key vaults, production Postgres, GitHub Actions, Docker, desktop IPC, deep links, `Makefile`, root `README`, `LICENSE`, `.github/`.

Sibling product tree `../omi/firestore.rules` exists on disk. **This audit does not cover it.** Firestore/OAuth/BYOK live in the legacy product, not this rewrite.

### What actually runs

Two stacks share types and SQLite. They are **not** one ingest→serve process.

1. **Offline pipeline** (`harness/run-pipeline.ts`): synthetic corpus → ingest → grounded extract → STM → dream placement. Live GLM/Codex only with `--model glm|codex` and env keys.
2. **App-facing service** (`apps/service/bin/dev-server.ts` → `createLocalDevService`): seeded QA memories, conversations, tasks, chat (scripted generator, **no memory consultation**), listen WS (scripted transcription), settings, write fence. Dev HMAC bearer. Loopback only.

Memories served on `/v1/memories` are a **QA graph snapshot**, not live dream output.

### Auth in one paragraph

There is **no production identity provider**. Dev tokens are HMAC (`dev1.<key_id>.<payload>.<sig>`), signed from `sha256(OMI_DEV_TOKEN_SECRET || "omi-local-dev-token-not-a-secret-v1")`. Issue and verify both use the **frozen fixture clock** `2026-08-07T12:00:00.000Z`, so the 24h TTL never elapses. Verified principals are **mapped onto `credential_kind: "mcp_api_key"` and grant consumer `"mcp"`** because inventing a new authority class is out of bounds (David). OAuth and `developer_api_key` are **typed and then denied** as `unsupported_credential_kind`.

### Threat model used here

Treat this tree as a **loopback QA fixture with production-shaped routes**. Findings that are fatal **if composed behind real credentials or bound off loopback** are called out as P0 *composition* risks, even though no production server exists in-tree today. A LAN-reachable default-token service would be an incident.

---

## 2. Architecture (depth)

```
sibling trackers (ADRs, domain language)     BasedHardware/omi ratified-contracts 0.8.0
            │                                              │
            └──────────── this repo implements ────────────┘
                              │
     core (pure)  ←lint fence→  drivers (sqlite, glm, codex)
                              │
              apps/service/composition/memory-read.ts   ◄── Rule 16 (one composition)
                    ┌─────────┴─────────┐
              REST /v1/memories     MCP read_synthesized_memory
                    └─────────┬─────────┘
                      127.0.0.1:4851 / :4801
```

**Hexagonal split is real.** `scripts/lint-import-graph.ts` forbids `core/` importing `drivers/`. Model I/O lives only in drivers/harness.

**Security fences that already shipped (and already failed once):**

- **Storage-provenance fence:** wire bytes must not derive from loader `coherent_snapshot_digest`, `ledger_head`, or other storage-scoped counts. A 2026-08-08 bug published hidden-row existence via cursor/frontier digests (measured: `3ad6626b…` vs `1441b306…`, ledger seq 6 vs 5). Escape hatch is `// storage-provenance-ok(<reason>)`.
- **Rule 16 (port registry, provisional, opt-in):** one composition per registered port. `ApplicationReadPorts` and `TasksReadPorts` are registered. New ports are unprotected until a row is added.
- **Rule 17 (wire-path fence):** a file that both stands up a server *and* names `/v1/memories`, `/v1/tasks/ops`, or `/v1/tasks` must import the registered route module. This exists because `integration/server/serve.ts` once served raw fixture row ids as public item ids while Rule 16 stayed green (it composed no registered port).
- **QA-control containment test:** `registerQaControlRoutes` may be imported only from `apps/service/app-facing.ts`. Bypassable via dynamic `import()`.

**D21 sharing is deferred** (`NOTES.md`). Owner identity is the whole-graph grant (`core/retrieve/grant.ts`). Conversation `visibility: public|private|shared` is a **legacy wire field**, not a sharing implementation.

**Known-open residuals (named in NOTES, not TODOs):** unrecognized-label joins for non-owners; novel policy strings fail-closed; reader-relative liveness through tree/dogfood; full two-reader noninterference fixtures.

---

## 3. Top risks

Severity is for **this checkout**. “P0 if deployed” means: do not compose this binary as production; the defect is already the intended QA shape.

### P0 — composition / exposure (fatal if this leaves loopback)

#### P0-1. Public HMAC material is the only credential; clock is frozen

**Confirmed.**  
`apps/service/bin/dev-server.ts:44,120` · `apps/service/app-facing.ts:538–551` · `apps/service/auth/dev-token.ts`

- Default label `omi-local-dev-token-not-a-secret-v1` is committed on purpose.
- Token is printed to stdout and written into `OMI_DEV_READY_RECORD` (mode `0o600`) including `devToken`.
- README embeds a working example token.
- Verify uses the same fixture epoch as issue → **TTL never expires**.

**Exploit sketch:** if the listener is reachable, `GET /v1/qa/status` (no auth) returns `owner_account_id`; mint `dev1.dev-local.<canonical-payload>.<hmac>` for that uid; full REST + Listen WS as that owner. Omitting `hostname` in `Bun.serve` binds `0.0.0.0` (documented past bug; `loopback.ts:21–23`).

**Today:** bind is `127.0.0.1` + `assert-loopback` LAN probe. Other **local processes** can still use the documented token.

#### P0-2. QA control plane mints account-epoch state the fence is built to deny

**Confirmed (footgun, documented in-module).**  
`apps/service/routes/qa-control.ts:35–68,157–185`

`observe` / `activate` let the authenticated principal walk **their own** account `legacy → migrating → new` and activate an epoch. Behind a real credential that is self-service fence defeat: the fence answers honestly about attacker-written control state.

Containment is “only `app-facing.ts` composes it” + a source-tree test. **No production server exists in this repo today.** The module header says that will stop being true.

#### P0-3. Checkout is 1848 commits behind the tracked remote

**Confirmed.** Local HEAD 2026-08-11; origin `codex/track3-backend-integration` is 1848 commits ahead. Auditing or shipping **this** tree as current is an integrity risk independent of code bugs. Do not treat this report as covering origin HEAD.

---

### P1 — real defects / oracles / stubs that survive review

#### P1-1. Authorization applied after load: hidden vs absent is timing-distinct

**Confirmed, measured, documented as unfixed.**  
`apps/service/README.md:295` · `apps/service/routes/hidden-vs-absent.test.ts`

Byte-identical pagination (status, headers, ids, cursors) is tested. **Clock is not.** Hidden rows are loaded and policy-classified then discarded. Measured 8 visible vs 8+8 hidden: median 8.07 ms vs 10.46 ms (~1.3×), non-overlapping p10/p90. Storage predicate in the query is still owed.

#### P1-2. Integration harness `/qa/*` mutates the corpus with no auth and ignores method

**Confirmed.**  
`integration/server/serve.ts:129–175`

`void request` — GET `/qa/reset`, `/qa/grow`, `/qa/absent` reseed/wipe. Loopback-only child process, but a local page can CSRF it (`<img src=http://127.0.0.1:…/qa/reset>`). Credentials `omi-integration-qa-key-v1` / `-v2` / `-noscope` are in-repo (`integration/server/compose.ts`).

#### P1-3. MCP pre-emission reauthorization is stubbed open on the live integration door

**Confirmed.**  
`apps/mcp/protocol.ts:316–318` (protocol calls the fence)  
`apps/qa/mcp-ports.ts:162–167` (QA implements it)  
`integration/server/compose.ts:375–377` (`reauthorizeBeforeEmission() { return Promise.resolve(true) }`)  
`spikes/mcp-final-reauthorization/` (incomplete draft)

The protocol has a real last-mile fence. The **live adversarial server** never refuses. A grant revoked after page build would still emit. `apps/qa` proves the fence; `integration/` does not.

#### P1-4. Canonical redaction is an exact-key denylist

**Confirmed.**  
`core/ledger/index.ts` (`api_key`, `authorization`, `raw`, `raw_text`, `secret`, `token`)

Misses `apiKey`, `password`, `private_key`, `refresh_token`, `access_token`. Digests and logs can retain those values. Graph payloads are otherwise assumed already redacted (`NOTES.md`).

#### P1-5. Tasks write path has pinned, unruled defects across epoch boundaries

**Confirmed, tests named as defects not specs.**  
`apps/service/routes/tasks-ops-known-defect.test.ts`

Crash-replay across an epoch advance can be reported as a **permanent failure for an edit that applied**. B5 GC disagrees across the same boundary. File cites `data/run-2026-08-09/blocked/OPS-b1-idempotency-and-b5-gc-disagree-across-an-epoch-boundary.md` (machine-local; not in git).

#### P1-6. Unauthenticated `/v1/qa/status` leaks seed identity

**Confirmed.**  
`apps/service/routes/qa.ts:48–63` · `app-facing.ts` seed identity includes `owner_account_id`

Deliberate for demo-detection. Feeds P0-1 if the door is reachable. `/v1/qa/control/stats` is also unauthenticated (counts only). `/health` and `/ready` unauthenticated (expected).

#### P1-7. Account lifecycle fail-open

**Confirmed.**  
`apps/service/auth/account-lifecycle.ts:5–6,35–36`

Missing row → `active`. Correct for a seeder with no production source. Combined with a minted uid (P0-1) the principal is live; stores are still owner-keyed so you get an empty account unless the uid matches a seeded owner.

#### P1-8. No CI in this repository

**Confirmed.** No `.github/`, no Makefile, no Dependabot, no CODEOWNERS. Quality gates (`bun test`, import-graph lint) exist only if someone runs them. Combined with P0-3, regressions can land on origin with no local signal.

#### P1-9. Prompt-injection surface on extract/dream (harness, not HTTP chat)

**Confirmed surface; exploit speculative against the live model.**  
`core/extract/grounded.ts:12–25,65–69` · `harness/injection.fixture.json` · `drivers/model/glm.ts:731–735`

Transcripts are treated as untrusted; a content-derived delimiter and an invariant prefix try to fence “obey” vs “analyse”. Live GLM still sends speech to `OMI_BENCH_OPENAI_BASE_URL` (default `https://api.z.ai/api/paas/v4`) with `GLM_API_KEY` / `ZAI_API_KEY` / `OMI_BENCH_OPENAI_API_KEY`. Repair hints append prior error text into the next prompt. HTTP Chat generation is a **scripted local adapter** and does not call GLM.

#### P1-10. Rule 16/17 are opt-in and provisional

**Confirmed.** New HTTP doors or port types are unprotected until someone adds a registry row. That is how the previous identity-split and raw-id leaks shipped green. Residual: two port constructions on one physical line share one hatch key (named 2026-08-09).

---

### P2 — hygiene, stubs, residual oracles

| ID | Finding | Evidence |
|---|---|---|
| P2-1 | MCP Origin allow-list skipped when `Origin` is absent | `apps/mcp/protocol.ts:180–185`. Native clients skip Origin. Browser POSTs send it. CSRF still needs a bearer. |
| P2-2 | Listen WS has no Origin check; credential recheck leased ≤1s | `apps/service/routes/listen.ts:247–254,29`. Auth is `Authorization` header (browsers cannot set that on `WebSocket()`), which blocks classic CSWSH. Native/local clients can. |
| P2-3 | Codex `spawn(OMI_CODEX_BIN)` + GLM base URL from env | `drivers/model/codex.ts:43–54` (`-s read-only --ephemeral`); `glm.ts:713–735`. SSRF/exec only if the operator env is attacker-controlled. Not on the HTTP door. |
| P2-4 | `OMI_QA_DB` / `OMI_DEV_READY_RECORD` unsanitized paths | `dev-server.ts:101–136,187–197`. Operator-only. Ready record contains the live token. |
| P2-5 | Integration rate-limit always allows; authorize is scope-only | `integration/server/compose.ts:326–338` |
| P2-6 | Settings: missing `Authorization` → 200 signed-out; bad bearer → 401 | `apps/service/routes/settings.ts:86–99`. Intentional. |
| P2-7 | `verify-publication.ts` interpolates lockfile `repository` into `git ls-remote https://github.com/${repository}.git` | argv, not shell. Not in `bun test`. |
| P2-8 | No root `tsconfig.json`; only `tsconfig.contracts.json` covers `contract-tests/` + `qa-contracts.ts` | Apps/core/drivers are Bun-run, not `tsc --noEmit` gated. |
| P2-9 | `package.json` `"test:node": "bun test"` is a lie | Node is not exercised. |
| P2-10 | Caret deps: `@sinclair/typebox ^0.34.41`, `ajv ^8.17.1`, `fast-check ^3.23.2` | Lockfile pins today; fresh resolve can drift. `hono` is exact `4.12.26`. |
| P2-11 | `.gitignore` omits `.env`, `.env.*`, `*.sqlite`, `*.db` | `/data/` is ignored (eval corpora). No committed `.env` found. |
| P2-12 | `Agents.md` “265 tests” is stale | 142 `*.test.ts` files; case count is higher than 265 if origin grew, unknown locally without a run. |
| P2-13 | `core/consolidate/state-machine.ts` (`ownsLease`) is unreferenced | T7 notes: no B3 lease/outbox/concurrency. Dead contract, not a runtime bug. |
| P2-14 | Dev REST pretends to be MCP credentials | `dev-token.ts:323–374`. Correct under current rulings; a production mapper that copies this is an authority-class invention. |
| P2-15 | Conversation `visibility=public` does not share | Field mutation only. D21 still open. |
| P2-16 | IPv6 `::1` is unbound | Only `127.0.0.1`. Clients using `localhost` → `::1` fail (reliability, not exposure). |
| P2-17 | ~700 `domain-pending(...)` sites, ~24 IDs | Mechanical rename debt. Markers present (merge rule satisfied). |

---

## 4. What is actually solid

Do not “fix” these into weaker shapes.

- **Tenant from bearer uid only.** Body/query cannot select an account (`tasks-read-account-epoch.test.ts`, write-fence `accountId` from principal, ADR-012 cited in `write-fence-guard.ts`).
- **Fixed 401/403 bodies.** No grant reason, stack, or owner id in error JSON. Route-hardening tests ban leak substrings.
- **Hidden-vs-absent byte identity** on the recall wire (timing excepted). Integration transport-traps run against the **registered** composition, not a lookalike.
- **Dev-token parser:** exact JSON keys, canonical HMAC, `timingSafeEqual`, dummy HMAC on unknown key id, reject non-canonical base64url.
- **Loopback is asserted, not assumed.** `hostname: 127.0.0.1`, lsof parse, LAN `/health` probe. Past `0.0.0.0` ship is why this exists.
- **No CORS headers.** Browser JS from another origin cannot read authenticated responses.
- **SQL:** values `?`-bound; interpolated table names from frozen enums (`drivers/sqlite/index.ts` witness tables, `qa/seed.ts`).
- **Chat attachments:** one multipart `file`, basename-only, magic-byte MIME, 50 MiB / 4-per-message, declared MIME must match sniff.
- **Chat SSE revalidates** the presented token during the stream (`chat-messages.ts:636–637`). Generation cancel is owner-scoped.
- **MCP protocol:** origin check when present, header multiplicity fail-closed, 1 MB page cap, tool-unavailable is identical for hidden vs unknown names, pre-emission reauth hook (implemented in QA, stubbed in integration — P1-3).
- **Cross-door identity** collapsed to one `ApplicationReadPorts` composition after REST vs MCP minted different public ids for the same memory.
- **Small dependency surface.** Hono exact-pinned, contracts vendored tarball with sha256/sha512 lock. No `postinstall`. No `eval` / `new Function` / `vm`.
- **No skipped tests, no `.only`, no FIXME/TODO/HACK.** Defects that must not be “fixed at night” are named `known-defect`.
- **Eval corpora stay out.** Import-graph bans `omi-real-djz-dev-v1`, `holdout-v1`, `benchmark`, `corpora/` path shapes. `/data/` gitignored. Fixtures are `source_trust: "synthetic"`.

---

## 5. Looked, not found

| Hunt | Result in this repo |
|---|---|
| Firestore / Firebase rules / Admin SDK / service accounts / `GoogleService-Info` | Absent |
| OAuth implementation / refresh tokens / BYOK key storage | Types only; `oauth` and `developer_api_key` deny |
| GitHub Actions, `pull_request_target`, unpinned actions, fork secrets | No `.github/` |
| Committed `.env`, `sk-`, `AIza`, `BEGIN PRIVATE KEY` | None |
| `eval` / `new Function` / `child_process.exec` of user input | None (Codex spawn is harness-only, flags sandboxed) |
| Open redirect / user-controlled `fetch` on HTTP door | None |
| Token in Listen query string | Bearer header only |
| Path traversal on attachments | Basename + sniff |
| Desktop IPC / deep links / Flutter bridges | None (loopback HTTP is the bridge) |
| Dockerfile publishing `0.0.0.0` | None |
| Real PII in fixtures | `@example.invalid`, synthetic phrases |
| `test.skip` / `describe.only` | None |
| Benchmark/eval data in git | None |

NUL bytes in `apps/qa/cursor-bindings.test.ts` and `contract-tests/write-ops-adversarial.test.ts` are **intentional adversarial strings** (`${valid}\0`, `/v1/tasks\0/ops`), not broken files.

---

## 6. CI / hygiene / dead code

### CI

Nothing. `bun test` is the gate, and it includes import-graph lint as a test. `scripts/qa-contracts.ts` is hermetic lockfile+tsc for contracts. `scripts/verify-publication.ts` hits GitHub `ls-remote` and **must not** join `bun test` (documented).

`make sync` / `make up` are **workspace-root** rules (`Agents.md`). There is no Makefile in this repo; they were not run.

### Dead / orphaned

| Item | Notes |
|---|---|
| `core/consolidate/state-machine.ts` | `ownsLease` never imported. T7 explicitly does not implement B3 lease/outbox. |
| `spikes/*` | Disposable patches; not runtime. Blocked on unpublished ADR-010. |
| `docs/wire-proposals/*` | Not contracts. |
| Dual store trees `apps/service/stores/` vs `drivers/sqlite/service-stores/` | Layered ports, not dead. |
| `createServiceApp` (`apps/service/app.ts`) vs `createLocalDevService` | Two doors on purpose: MCP-only shell vs full app-facing service. |

### Inventory (this tree)

- ~373 source-ish files (ts/json/md, excluding `node_modules`)
- 340 `*.ts`, 142 `*.test.ts`, 379 git-tracked files
- ~700 `domain-pending` occurrences, ~24 unique IDs (plus example placeholders in `Agents.md`)
- Last local commit: 2026-08-11

---

## 7. Easy wins

Ordered by leverage. None require a product decision.

1. **Add CI** on `pull_request` (not `_target`): `bun install --frozen-lockfile` && `bun test`. Pin actions by SHA. Optional separate job for `verify-publication.ts` on lockfile changes only.
2. **Root `tsconfig.json` + `"typecheck": "tsc --noEmit"`** covering `apps/`, `core/`, `drivers/`, `harness/`, `integration/`.
3. **`.gitignore`:** `.env`, `.env.*`, `*.sqlite`, `*.db`.
4. **Pin remaining `^` deps** (typebox, ajv, fast-check) to exact versions matching `bun.lock`.
5. **Fix `"test:node"`** or delete it.
6. **Refresh `Agents.md` test count** after a real `bun test` run.
7. **Fail closed if `Bun.serve` is constructed without `hostname`** (static lint or runtime assert beyond the one binary).
8. **Implement `reauthorizeBeforeEmission` in `integration/server/compose.ts`** the same way `apps/qa/mcp-ports.ts` does, or delete the live MCP door from that harness.
9. **Auth the integration `/qa/*` control plane** (or bind it to a second loopback port that tests alone know).
10. **Widen redaction keys** (or switch to an allowlist for hashed payloads).
11. **Drop or wire `core/consolidate/state-machine.ts`** so T7 debt is visible as a missing driver, not a dead export.
12. **Root LICENSE + README pointer** to `apps/service/README.md` (the only operator doc).

---

## 8. Suggested follow-ups (need a human / David)

These are not “easy” because they invent authority, delete data, or reopen open specs.

1. **Do not compose `createLocalDevService` / `registerQaControlRoutes` behind production credentials.** When a production server lands, it needs a different app factory with no `/v1/qa/*` and no default HMAC. The containment test is a ratchet, not a capability restriction.
2. **Publish or replace ADR-010**, then apply `spikes/authorized-context/` **in order** (0001 then 0002 expiry-after-grant-lookup). Integrating now would choose an open authority model.
3. **Finish MCP final reauthorization** after that same ruling (`spikes/mcp-final-reauthorization/`).
4. **Push authorization into the SQLite predicate** so hidden-vs-absent is timing-identical (P1-1). HTTP cannot fix this.
5. **Rule the tasks-ops epoch defects** (P1-5) or invert the known-defect file. Do not “clean up” the assertions while the escalation is open.
6. **D21 sharing** (reader≠owner). Conversation `public`/`shared` is a trap until this exists.
7. **Production credential kinds** (`oauth`, `developer_api_key`) are types that currently deny. Implementing them is a new authority class.
8. **Postgres adapter, production Chat model, production Listen STT** — documented as owed; local adapters are scripted.
9. **Rebase/ff this checkout** onto origin before any implementation work. This audit is of an August 11 snapshot, not of GitHub HEAD.
10. **If Firestore/OAuth/BYOK of the shipping product is in scope**, audit `../omi/` (legacy `firestore.rules`, plugins OAuth, Flutter app) as a **separate** report. Mixing the two trees will produce false confidence.

---

## 9. Method

Read: `Agents.md`, `NOTES.md`, `package.json`, `contracts.lock.json`, `apps/service/README.md`, auth (`dev-token`, session, lifecycle), loopback bind, QA/control routes, MCP protocol + QA ports, Listen WS, chat attachments/generation, write-fence, grant/authorization-boundary, import-graph lint, integration serve/compose, model GLM/Codex, spikes, git log/status/remote.

Grep: secrets, OAuth, Firestore, eval/exec, CORS, Origin, domain-pending, TODO/FIXME, skip/only, `process.env`.

Did **not:** run `bun test`, `make sync`, mutate git, hit GitHub APIs, audit `../omi` Firestore rules, or treat origin’s 1848 newer commits as present.

---

## 10. Bottom line

This is a **unusually well-fenced QA backend**: tenant binding, failure oracles, loopback bind, storage-provenance, and one-composition-per-port are real, and several of them exist because earlier waves shipped green-and-wrong.

The residual risk is not a missing HMAC compare. It is **shipping the fixture**: default HMAC, frozen clock, self-service epoch control, unauthenticated QA status, integration reauth stub, and **no CI**, on a checkout **1848 commits behind** the branch it tracks.

**Do not deploy this composition. Do not omit `hostname`. Do not register `qa-control` on a production app.**
