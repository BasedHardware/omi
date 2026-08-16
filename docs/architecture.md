# How this tree fits together

This is a description of what the tree does today. It is not a design
proposal. Every non-obvious claim names the file it was read from.

Related, already written, and not restated here:

- Memory formation (local producer path, `source_trust` travel, HTTP write
  door): [`docs/memory-formation.md`](memory-formation.md)
- Chat provenance (three witnesses that must agree):
  [`docs/chat-provenance.md`](chat-provenance.md)
- How to run a lane, and what a lane is entitled to claim:
  [`docs/verification.md`](verification.md)
- Boot, seed, reset, stop: [`docs/running-locally.md`](running-locally.md)
- UI fixture harness (backend-free): [`docs/ui-harness.md`](ui-harness.md)
- Local JSONL inspection log: [`docs/telemetry.md`](telemetry.md)
- Network-fence proposal (not built): [`docs/network-fence-proposal.md`](network-fence-proposal.md)

## Shape

Two deployments share `core/` (contracts, orderings, admission). They do not
share a process, a store, or an identity seam.

**On David's machine (the headed app):** a Bun HTTP service,
`apps/service/bin/dev-server.ts`, bound loopback-only, with one SQLite file
as QA fixture storage. The comment at `dev-server.ts:61-63` states that
SQLite here is never production authority. The same factory tests use,
`createLocalDevService` in `apps/service/app-facing.ts:484-498`, is what the
dev server serves. A macOS WKWebView shell loads the surfaces bundle against
that origin. Chat tokens come from a **separate loopback process** (canned
test gateway or opt-in real-model proxy), not from a model client linked
into the service.

**Not on David's machine (the hosted path):**
`drivers/postgres/firebase-authorized-memory-service-process.ts` wraps
`createPostgresFirebaseAuthorizedMemoryServiceApp`
(`firebase-authorized-memory-service-app.ts:31-65`). That composition
registers `/v1/memories` and an MCP handler. It does not register
conversations, tasks, chat, listen, or screen. Identity is a Firebase ID
token (`apps/service/auth/firebase-identity.ts`), not the local dev-token
seam. Storage is PostgreSQL. `bun run prod-local` (`scripts/prod-local.ts`)
is this process on loopback against a managed local Postgres; it is still
the hosted kernel, not the SQLite QA server.

A misdiagnosis this program has already paid for is treating a green local
SQLite stack as evidence about the hosted Postgres/Firebase path, or the
reverse. They share `core/`. They do not share a listener, a database, or a
principal.

`core/` is imported by both. `drivers/sqlite/` is the local/QA adapter.
`drivers/postgres/` is the hosted adapter. `harness/` is offline evaluation
and is forbidden on both production closures (see Rule 18 below).

## Two sanctioned network destinations

The service is allowed to leave the machine for **Firebase Authentication**
and **the chat model provider**. Nothing else is a sanctioned leak.

The in-tree enforcement of the **import** half is Rule 18, `bun run lint:closure`,
implemented by `scripts/lint-import-closure.ts` and traced by
`scripts/trace-value-imports.ts`. It is a dependency/import-closure fence,
not a network observer. The host-level follow-up is
[`docs/network-fence-proposal.md`](network-fence-proposal.md).

What the fence **actually traces**: the transitive **value-import** closure
of listed TypeScript entrypoints. Type-only imports are excluded
(`trace-value-imports.ts:19-21, 46-51`) because they erase at runtime.
`--forbid` is a path-substring match against that closure
(`trace-value-imports.ts:109-116`). The tracer does not inspect `fetch`
URLs, environment values, or which host a running process contacted.

Two groups, deliberately different lists (`lint-import-closure.ts:42-66`):

| Group | Entrypoints | Forbidden substrings |
|---|---|---|
| CLOUD | `drivers/postgres/firebase-authorized-memory-service-process.ts`, `drivers/postgres/firebase-authorized-memory-service-app.ts`, `apps/mcp/bun-http.ts` | `apps/qa`, `drivers/sqlite`, `drivers/model/glm`, `integration/local-test-gateway`, `harness/`, `spikes/`, `migration/` |
| LOCAL | `apps/service/bin/dev-server.ts` | `drivers/model/codex`, `drivers/model/glm`, `harness/`, `spikes/`, `migration/` |

The local entrypoint is allowed to link SQLite and the QA seeder; the hosted
entrypoints are not. The local entrypoint is forbidden from linking a Codex
or GLM model client, or anything under `harness/` (which carries its own
provider profile). Chat on the local path reaches a model only by HTTP to a
loopback gateway configured at boot (`dev-server.ts:279-304`,
`OMI_LLM_GATEWAY_URL`). That gateway process is not one of the Rule 18
entrypoints.

Firebase identity is composed on the hosted memory path
(`firebase-authorized-memory-read-runtime.ts:15`). The local QA binary does
not import it; it issues a committed loopback bearer
(`dev-server.ts:70-76`).

The comment at `lint-import-closure.ts` names this as an import-closure
fence and points at [`docs/network-fence-proposal.md`](network-fence-proposal.md)
for a host-level follow-up. A `fetch` to an unsanctioned host from a module
that is already on the closure still does not fail Rule 18. The CLOUD
forbid-list does not include `drivers/model/codex`; the LOCAL list does.
Entrypoint and forbid-list edits are David-only
(`trace-value-imports.ts:28`).

## Domains, and where each one's data comes from now

The producer-evidence inventory is eight domains
(`apps/service/observability/producer-evidence.ts:7-17`): memories, tasks,
conversations, folders, listen, chat, settings, screen. Home is a surface
that reads memories and conversations (`home-sources.ts`); it is not a
backend domain. `stm-notes` is a write door into memory formation, not a
row in that inventory — see [`docs/memory-formation.md`](memory-formation.md).

On the **local SQLite service** (`dev-server.ts` injects
`createSqliteLocalServiceStores` at `dev-server.ts:273`; the store set is
assembled in `drivers/sqlite/service-stores/index.ts:47-80`):

| Domain | Data comes from |
|---|---|
| memories | Durable QA snapshot in the same SQLite file (`apps/service/qa/seed.ts` `seedQaSnapshot`), plus formation from user notes and listen finalization. Read through `composition/memory-read.ts`. The hosted Postgres reader is a different composition on the same `/v1/memories` path; it is not this binary. |
| tasks | `SqliteTasksStore`. Reads `GET /v1/tasks`; writes `POST /v1/tasks/ops`. Account epoch rides on the tasks read (`routes/tasks-read.ts:184-194`). |
| conversations | `SqliteConversationsStore`, seeded at `app-facing.ts:582-584`. Listen finalization can upsert a conversation. |
| folders | `SqliteFoldersStore`, seeded at `app-facing.ts:582`. |
| listen | `SqliteListenStore`. Default transcription is the scripted adapter (`createLocalDevService` at `app-facing.ts:493`). On-device MLX Whisper is opt-in in `dev-server.ts` only (`dev-server.ts:306-315`); production entrypoints do not import it. |
| chat | SQLite message, attachment, admission, and generation-event stores. Generation is gateway-required (`app-facing.ts:496`); without gateway config the source fails closed rather than emitting a fake answer. |
| settings | `SqliteSettingsProjectionStore` (identity and entitlement). |
| screen | `SqliteScreenStore`. Capture pixels arrive from the native host channel, not from this HTTP service inventing frames. |

Tests that omit `stores` get in-memory defaults (`app-facing.ts:550`). The
headed path always passes the SQLite set.

On the **hosted Postgres/Firebase process**, only memories (and MCP) are
wired (`memory-service-app.ts:18-25`). Conversations, tasks, chat, listen,
settings, and screen have no composition on that process in this tree.

## Generation, after retirement

Two different words, both in this tree. Do not collapse them.

**Account generation** (`legacy` / `migrating` / `new` /
`rolled_back_stranded`) is control-plane state. Application admission
denies every value except activated `new`
(`core/control/application-admission.ts:34-51`). The local headed app does
not walk that cutover through `/v1/qa/control`; `bin/dev-server.ts` calls
`ensureLocalOwnerWriteReady` after `createLocalDevService` and again from
the process-registered `afterReset` hook on `/v1/qa/reset`. That is still
process-owned, never factory-owned.

**Backend generation** is the client knob: `legacy` (old wire, through
`packages/adapters-legacy`) versus `platform` (contracts-native wire,
through `packages/adapters-platform`). The selector is
`frontend/packages/domain/src/generation-selection.ts`. An omitted or
null host config is legacy on every domain
(`generation-selection.ts:62-67, 115`). A malformed request is rejected
and reported, never silently downgraded (`generation-selection.ts:20-24`).

Availability today (`generation-selection.ts:47-60`): memories,
conversations, folders, and tasks each offer both `legacy` and `platform`.
Listen, chat, settings, and screen are not in that table; they are not
selected this way.

David's 2026-08-16 rulings that have already landed:

- Tasks park lifted: `tasks` is ratified on platform
  (`generation-selection.ts:56-59`).
- In-place memory editing retired: the platform Memories surface adds a
  fact through the correction composer; it does not patch a synthesized
  proposition (`home-sources.ts:19-22`, and the rendered-absence test in
  `frontend/packages/surfaces/test/memories-platform.test.mjs`).
- Live launchers pin `generation=platform`
  (`frontend/shells/macos/scripts/dev-run-macos.sh:160-167`;
  `frontend/shells/ios/scripts/dev-run-ios.sh` does the same). L3 no longer
  carries a `--generation` split
  (`integration/single-service-structure.test.mjs:38-40`).

`packages/adapters-legacy` is still in the tree. A sibling lane is deleting
it. Until that lands, omitting `generation=` still selects legacy
everywhere, and `--generation legacy` is still a reachable launcher arm.

Surfaces must not know which generation they are on; `ProductionStores`
ports hide it (`generation-selection.ts:9-10`). The shell knows, and says
so without a recompile.

## `source_trust`, and the user's own words

`source_trust` is a required field on evidence and event records. Local
formation stamps it and does not later drop a record because of it. The
travel path is documented in [`docs/memory-formation.md`](memory-formation.md).
The stamps in this tree:

- User notes: `source_trust: "user_asserted"`
  (`apps/service/stm/stm-note-ingestion.ts:150`).
- Listen: `source_trust: "listen-finalized"`
  (`apps/service/listen/formation-ingestion.ts:412`).
- QA seed: `` `${family}-seed` `` (`apps/service/qa/seed.ts:259, 274`).

A user's own words are never filtered out of promotion.
`drivers/sqlite/dream.ts:22-26` defines `TRUSTED_SOURCE_TRUST` as
`user_asserted` and `imported_unverified`. `user_asserted` is fully trusted
for promotion; that set is not a lock field and not an overwrite. It lets a
user-asserted note enter the graph without a `subject:owner` label
(`dream.ts:59-61`). The HTTP note door is never quality-gated
([`docs/memory-formation.md`](memory-formation.md)).

The only quality gate is `core/extract/quality.ts`. It is distributional.
The file header (`quality.ts:1-12`) says why: every claim in a collapsed
extractor run was individually well-formed, so structural validation passed
on output that carried almost no information. The checks look at the
**population** of claims, not at any one claim. Thresholds were measured
against that run (`quality.ts:14-24`):

- `max_relation_share` 0.15, once there are at least 20 claims
- `max_sole_argument_coverage` 0.6 (one argument whose surface is most of
  the cited excerpt)

`checkRelationDistribution` reports; it does not throw (`quality.ts:35-38`).
`core/extract/grounded.ts:474-476` records `sole_argument_covers_evidence`
as a finding and still retains the claim. Findings are appended to
`quality_findings` on the way out (`grounded.ts:516`). They are not a drop
rule. The scripted local extractor can emit that finding; formation still
keeps the user's excerpt.

## What is not true

These would otherwise be assumed.

**iOS control clicks exist, and they are not L3.** L3's first step drives both
shells through `integration/dev-stack.sh --assert` and joins producer and
consumer evidence. The second L3 step, and all of L4, click real controls
inside the **macOS** WKWebView (`integration/control-acceptance/run.mjs`,
`integration/lanes.mjs` L3/L4). iOS click-through is the same runner with
`--ios`: same `driver.js`, same `verdict.mjs`, same outcome tokens, injected
through the Flutter host at the frozen `omi-ui://local` origin
(`frontend/shells/ios/scripts/dev-run-ios.sh`). That origin is not the macOS
5290/15290 lease. `--ios` is not a lane gate; a green L3 still does not
entitle an iOS control claim.

**The real chat-provider path is newly present, not the default proof.**
Default Chat is the canned loopback gateway. The opt-in real-model proxy is
`integration/local-model-gateway.mjs`, selected with `OMI_CHAT_MODEL=real`.
`tier: "real-provider"` is minted only from that gateway's `/ready`
declaring `real_model_proxy: true` (`generation-source.ts:213-216`).
Reachability is not provenance. How to read the three witnesses is
[`docs/chat-provenance.md`](chat-provenance.md). A sibling lane is proving
the real provider against the headed app; until that is the lane you ran,
do not quote a canned L3 as a real-model result.

**Performance is unmeasured.** This repo must not contain benchmark corpora
(`AGENTS.md`). There is no latency, throughput, or memory budget enforced
by a lane. A timing note in a hidden-versus-absent test is a side-channel
observation, not a product SLO.

## Landing under this tree (not done here)

Sibling lanes are deleting `adapters-legacy` and proving the real chat
provider. When those land, the generation availability table, the launcher
`--generation legacy` arm, and the Chat default in
[`docs/verification.md`](verification.md) are the lines that move. Re-read
those files; do not take this paragraph as the new state.
