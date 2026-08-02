# Handoff

Two things in here:

1. **Part A — every CRITICAL from the security audit**, fixed and unfixed, with what still needs a human.
2. **Part B — the Rewind → memory-graph-only sync task**, specified against real code.

Branches:
- `security/transport-and-secrets-hardening` — 4 audit rounds, ~80 fixes, pushed and green. Reports: `SECURITY-AUDIT.md`, `AUDIT-WORK-SUMMARY.md`.
- `arch/local-first-agent` — migration plan only, no code. `docs/architecture/local-first-agent-migration.md`.

Every `file:line` below was read from the tree, not recalled. Where something is a judgement call or unverified, it says so.

---

# PART A — ALL CRITICALS

## A1. Fixed on the security branch

| # | Finding | Where |
|---|---|---|
| 1 | `update_app`/`update_persona` authorized on the path id but **wrote the id from the request body** — any app owner could rewrite any other developer's app: reassign ownership, repoint the webhook receiving installing users' transcripts, repoint the Stripe payment link. | `backend/routers/apps.py` |
| 2 | Chat image thumbnails were `make_public()`'d at a **guessable** URL (`<bucket>/<uid>/<snake_cased_filename>`). uids leak via PostHog `distinct_id` and Sentry. | `backend/utils/other/storage.py` |
| 3 | **Account deletion never purged voiceprints or conversation audio.** Firestore wiped, API reported success, raw audio stayed in GCS with the index to find it gone. GDPR Art. 17. | `backend/services/users/account_deletion.py` |
| 4 | `TaskAgentManager` built a `zsh -c` string containing `$(cat promptFile)`, which tmux re-parsed with a **second shell** — LLM-extracted task text executed. | `TaskAgentManager.swift` |
| 5 | Server-supplied task ids interpolated into `osascript` + four `zsh -c` strings, **replayed from SQLite every launch** with no revalidation → persistent execution. | `TaskAgentManager.swift` |
| 6 | A **live, non-expiring Notion access token** printed to stdout on every integration setup. **Rotate every token that passed through this.** | `plugins/oauth/conversation_created.py` |
| 7 | **One-line binding error made the Gemini daily cap unreachable.** `check_rate_limit` returns `(allowed, remaining, retry_after)`; code bound `_, current, _` then tested `current > 1500`. `current` was `remaining` — starts at 1499, counts *down*. Real ceiling was the burst limit: **43,200 req/day/account** on Omi's key. Same inversion ran the cost downgrade backwards. | `backend/routers/desktop_proxy.py` |
| 8 | `/v1/omni/relay` — realtime LLM websocket on the platform OpenAI key, no quota/rate policy/connection cap/session timer/usage recording. ~$4–6/hr/socket, unbounded sockets. | `backend/routers/omni_relay.py` |
| 9 | `/v2/realtime/session` minted OpenAI realtime secrets **with no expiry**, usable directly against OpenAI — spend invisible until the invoice. | `backend/routers/desktop_realtime.py` |
| 10 | **Quadratic regexes blocked the event loop.** Three unanchored lazy `DOTALL` patterns, sequential, synchronous, inside `async def`. 7.4s at 140 KB against a 512 KB cap. Trigger: one chat message with a URL — the prompt *instructs* the model to fetch any URL. Now 0.18s. | `backend/utils/retrieval/tools/web_tools.py` |
| 11 | Limitless ZIP import: no decompressed-size cap. 100 MB → ~103 GB, in-process in the API container. | `backend/utils/imports/limitless.py` |
| 12 | Agent-VM upload's decompressed cap **equalled** its compressed cap → ~1000:1 amplification. | `backend/agent_vm/main.py` |
| 13 | MCP batch endpoint charged **one** rate-limit token for an unbounded array — ~100,000× bypass. | `backend/routers/mcp_sse.py` |
| 14 | **agent-proxy stored "enhanced protection" chat in plaintext** and relabelled the record `'standard'` so nothing downstream could tell. The prod chart never injected `ENCRYPTION_SECRET` — **this was the shipped config.** A fork of `utils/encryption.py` with its fail-closed guard inverted. | `backend/agent-proxy/main.py` |
| 15 | **`personas /api/store-facts` was unauthenticated** and took `uid` from the body, writing memories into any account with the server's privileged key. Unauthenticated persistent prompt injection at scale. | `web/personas-open-source/` |
| 16 | **`Logger.swift` was a local write primitive.** Production log at `/tmp/omi.log`; the permission helper correctly returned `false` when it couldn't remove an attacker-owned file in sticky `/tmp`, **but the caller never checked**, then used symlink-following `fileExists` + `FileHandle`. Another local account could read the whole log, or make Omi append to `~/.zshenv` as the victim. | `desktop/macos/.../Logger.swift` |
| 17 | **Agent VM ran Claude with `bypassPermissions` + full `Bash`, as root**, over the user's screen-OCR DB. Indirect prompt injection was a root shell. | `backend/agent_vm/main.py` |
| 18 | `fill_cloud_connector_form` could attach the user's signed-in Claude/ChatGPT account to a **model-chosen MCP server**, no confirmation. | `CloudConnectorFormAutomation.swift` |
| 19 | Firmware: `speak()` wrote `2 × len` bytes per BLE write into a 10,000-byte slab with **no write-pointer bound** → ~150 KB attacker-chosen overwrite. | `omi/firmware/*/speaker.c` |
| 20 | Firmware: path traversal in v2 sync upload wrote into **another tenant's** staging directory. | `backend/utils/sync/pipeline.py` |

## A2. NOT fixed — needs a human decision

These are the ones to action first.

### 1. The wearable is an unauthenticated open microphone — **most serious finding in the audit**
`omi/firmware/omi/src/lib/core/transport.c:144`. The BLE audio characteristic had no encryption requirement and `bt_conn_set_security()` was never called anywhere in the firmware. Anyone in range connects with **no pairing**, writes `0x0001` to the audio CCCD, and receives the live microphone. Storage service equally open — list, download, wipe recordings. omiGlass is worse: unauthenticated BLE writes set the WiFi credentials *and* the OTA URL.

**Status:** a fix IS on the security branch behind `CONFIG_OMI_REQUIRE_BLE_ENCRYPTION` (default `y`) — but **it was never compiled** (no NCS toolchain available) and **never exercised against hardware**. It is a breaking change: every device in the field will prompt to pair once. Android also needs `needsBond` extended (`device_connection.dart:112`) or it fails silently.

**Blocker before shipping:** `CONFIG_BT_MAX_PAIRED=1` means the device marries the first phone that pairs, permanently, and there is **no bond-clear path in the firmware** (`bt_unpair` — zero hits). Add a long-press unpair or a user replacing their phone has a brick.

### 2. Firmware signing key is committed
`omi/firmware/bootloader/mcuboot/root-rsa-2048.pem`. CI's own README says it is the key releases are signed with. Anyone with the repo can produce a valid DFU image. Rotation needs a staged bootloader update signed with the *old* key, because the public half is burned into shipped bootloaders.

### 3. Agent-VM traffic is cleartext HTTP
Full `omi.db`, Firebase ID token, and a long-lived bearer (**in the query string**) over `http://` to a public GCE IP. `NSAllowsArbitraryLoads` app-wide. Also: `/health` is unauthenticated and its response is *trusted* — forging `{"databaseReady": false}` triggers a full DB re-upload. No firewall rule for tag `omi-agent-vm` exists in any IaC; **verify in GCP whether 8080 is `0.0.0.0/0`.** No client-only fix exists.

### 4. One org-wide Anthropic key on every user's internet-facing VM
`backend/agent_vm/startup.sh:6`. Compromising *one* user's VM yields production model billing credentials. Revocation is all-or-nothing.

### 5. ACP permission requests auto-approve
`desktop/macos/agent/src/runtime/desktop-tool-policy.ts:304` selects `allow_always` unconditionally — no confirmation gate anywhere. Grants `Read`/`Write`/`Edit`/`Bash` on any absolute path in an unsandboxed process with Full Disk Access. Documented as intentional, so it's a product call.

### 6. `fetch_url_tool` is a mandated exfiltration channel
`backend/utils/retrieval/agentic.py:871` — the prompt says the model **MUST** fetch any URL it sees, including URLs arriving inside untrusted tool results, while `get_memories_tool` output sits in the same context. Partially fixed (scoped to current-turn user URLs); verify the scoping holds.

### Rotate now
Notion tokens (printed to stdout), the Hive API key (printed on every REST call), and `OPENAI_API_KEY` + `GOOGLE_CLIENT_SECRET` if any published mobile build carried them (CI injects both, contradicting `app/config/client_env_policy.yaml`).

### Deploy ordering — will break things if ignored
1. `AGENT_VM_ENABLED=true` must be set before deploy or agent VMs go dark.
2. `ENCRYPTION_SECRET` must exist in `prod-omi-backend-secrets` — agent-proxy now **raises at import** rather than silently writing plaintext.
3. `ADMIN_KEY` must be non-empty or all admin routes 403.
4. `ADMIN_KEY_AUTH_ENABLED=false` **disables a live impersonation mechanism in prod** — needs sign-off.
5. `shieldedInstanceConfig` requires a UEFI-enabled source image or `instances.insert` fails outright.
6. The VM name change orphans currently-provisioned VMs; no migration written.

### Not converged
Round 4 still produced new CRITICALs, so **a round 5 is warranted.** Each round has also found bugs introduced by the previous round's fixes — the self-review pass over our own diff has been the highest-value agent every time. Run it.

---

# PART B — REWIND: SYNC THE MEMORY GRAPH, NOT IMAGES

## B1. The ask

> Rewind keeps capturing locally. The **only** thing that syncs to the cloud is the derived **memory graph** — never images, never raw OCR. **No web recall/timeline UI** — heavy for no benefit.

## B2. Read this before planning — it changes the shape of the job

**1. omi-v4 gives you a sync protocol but ZERO reference for the actual hard part.**
v4 never derives anything from Rewind. `CaptureSource::Screen` is defined in the signal enum but **never constructed outside tests**, and the extraction gate at `runtime.rs:3776-3778` explicitly admits only `OmiDevice | Chat`. v4's Rewind is newline-delimited JSON + loose JPEGs (`rewind/store.rs:1-9`) with local substring search, and `grep -rin rewind worker-rs/src` returns **no matches**.
→ **The screen→graph extractor is net-new work with no reference implementation.** Do not scope this as "port v4 Rewind."

**2. The two graph models are different shapes.**
- v4/zkr: **claim/evidence triples** — `claims(subject, predicate, value, valid_from, valid_until, …)` + `evidence(quote, source_id)` (`zkr` schema `schema.rs:65-76`). No entities table, no edges table.
- omi: **entity nodes + edges** — `knowledge_nodes`/`knowledge_edges` (`backend/database/knowledge_graph.py:15-16`), and desktop `local_kg_nodes`/`local_kg_edges` (`RewindDatabase.swift:2456,2467`).

Porting v4's *protocol* does not port its *model*. **Pick one and say so in the PR.** Recommendation: keep omi's node/edge model — it already has a live server, routes, and two clients (below). Unresolved either way.

**3. `zkr` is a published crates.io crate (`zkr = "0.4.0"`), not repo source.** Any model change means forking or an upstream release.

**4. The web recall UI does not exist. There is nothing to remove.**
Every `web/app/src/app/**/page.tsx` route enumerated — no rewind/timeline/screenshot route, and `grep rewind web/` returns **zero hits**. The recall UI is macOS-only (`Rewind/UI/*.swift`). So "no web recall" costs nothing — just don't add it.

**5. The graph surface you want already has a web client.**
`web/app/src/components/memories/KnowledgeGraph.tsx`, rendered from `MemoriesPage.tsx:657`, backed by `GET /v1/knowledge-graph` (`backend/routers/knowledge_graph.py:90`). Flutter too: `app/lib/pages/memories/widgets/memory_graph_page.dart`. **You are feeding an existing surface, not building one.**

**6. Server-side graph already exists and is live.** `knowledge_nodes` / `knowledge_edges` / `memory_graph_assertions` under `users/{uid}/` (`backend/database/knowledge_graph.py:15-17`), caps 500 nodes / 1000 edges / 500 assertions (`:23-25`), with GET/rebuild/DELETE routes. Written today only by the **legacy** conversation pipeline (`process_conversation.py:1255-1262`). `canonical_kg_promotion.py:104` is **dead** — no production caller.

**7. Desktop `local_kg_nodes` is populated only by an onboarding LLM chat tool** (`ChatToolExecutor.swift:2627` via `save_knowledge_graph`), never from Rewind or OCR. `sourceFileIds` is dead — always written `nil` (`:2593`). No indexes on either table (`RewindDatabase.swift:2455-2476`).

## B3. What leaves the device today — TWO paths, both must be closed

**Path 1 — agent-VM sync.** `AgentSyncService.swift:130-152`. 9 tables. `screenshots` is `appendOnly` with **`ocrDataJson` as the only exclusion** — so `ocrText`, `imagePath`, and the **12 KB `embedding` blob** all ship, base64-encoded (`:541-543`), every 3 seconds, to `http://<vmIP>:8080/sync`.

**Path 2 — cloud screen-activity sync.** `ScreenActivitySyncService.swift` → `POST /v1/screen-activity/sync` (`backend/routers/desktop_screen_crisp.py:112`) → Firestore `users/{uid}/screen_activity` with **verbatim `ocrText` truncated to 1000 chars** (`backend/database/screen_activity.py:44`), plus Pinecone ns3 vectors. macOS-only writer; Flutter never calls it.

⚠️ **Easy to miss:** `_parity_screen_rows` (`desktop_screen_crisp.py:56-66`) retains **`ocr_text` up to 8192 chars** — 8× the Firestore truncation — plus app name and window title, persisted by `SurfaceParityCapture` (`:121-130`). Its docstring at `:57` claims it never retains that. **Remove it.**

⚠️ **Unresolved product question:** screenshots **already** leave the machine as base64 to third-party LLMs — `RealtimeHubSession.swift:806,905` sends JPEGs straight to `wss://api.openai.com/v1/realtime` and a Gemini WS, **bypassing the Omi backend entirely**; `InsightAssistant.swift:813` and `TaskAssistant.swift:1089` go via the Omi Gemini proxy (forwarded, not persisted). Does "never images" cover inference-time transmission, or only storage? **Answer this before starting** — it changes whether this is a sync change or a capture-architecture change.

## B4. The work

**1. Screen → graph extractor (the real work, net-new).**
Input: `screenshots.ocrText` + `appName` + `windowTitle` (all already local). Output: nodes and edges into `local_kg_nodes` / `local_kg_edges`. Runs on-device. v4's on-device extractor (`extraction.rs:8-19`, Apple Foundation Models via `local_ai.rs:21-44`) is the closest shape to copy, but it emits claim triples from *transcripts*, not entities from screens.
Decide: on-device model (private, macOS-only — v4 returns `None` off macOS+aarch64, `local_ai.rs:39-43`) vs. the existing Gemini proxy (works everywhere, but OCR text then transits the backend, which partly defeats the point).

**2. Sync only the graph.** New `TableSpec`s for `local_kg_nodes` / `local_kg_edges`; **remove `screenshots` and `observations` from `tableSpecs` entirely.** Note `AgentSyncService` has **no allow-list** — `excludedColumns` is the only deny mechanism, so adding a column to a synced table silently ships it. Consider inverting to an allow-list while you are here.

**3. Point it at the existing server graph.** `POST`/merge into `knowledge_nodes`/`knowledge_edges` via the existing `/v1/knowledge-graph` surface rather than inventing a second store. Respect the 500/1000 caps (`knowledge_graph.py:23-24`) — decide eviction before you hit them.

**4. Delete path 2 outright.** Remove `ScreenActivitySyncService.swift`, `/v1/screen-activity/sync`, `screen_activity` Firestore writes, Pinecone ns3 upserts, **and** the `SurfaceParityCapture` OCR retention. Then check the read side: `GET /v1/mcp/screen-activity` (`backend/routers/mcp.py:784`), the MCP SSE `get_screen_activity` tool (`mcp_sse.py:646`), and the `screen_activity.read` OAuth scope (`mcp_oauth.py:32`) all become dead — remove or repoint them at the graph.

**5. Do not build web recall.** Nothing exists; keep it that way. One dead generated symbol remains — `McpScreenActivityRow` (`web/app/src/lib/omiApi.generated.ts:2121`), unused by hand-written code; regenerate rather than hand-edit.

**6. Backwards compatibility.** Existing `screen_activity` docs and ns3 vectors need a decision: migrate to graph, or delete as part of the cutover. Deleting is defensible (it is derived data) but it is **user-visible** if anything reads it — check the MCP consumers above first.

## B5. Sync protocol, if you copy v4's

Worth copying — it is genuinely better than the current 3-second full-table poll. `POST /v1/memory/zkr-sync`, 30 s (`memory_sync.dart:123`), and critically **an idle tick costs zero network** (`:185` breaks before upload when there are no commits). Cursor `(requestCommit, requestEventIndex, appliedCommit, highWaterMark)` (`:13-18`), acks per commit as `staged`/`applied`/`replayed` (`:224-228`), cursor advances only on `applied`/`replayed` (`:229-238`).

Two flaws to fix rather than copy:
- The worker **ignores** `database_schema_version` and `high_water_mark` (`wasm_glue.rs:772-783`) despite the client sending them. If version negotiation matters, add it.
- The commit loop (`wasm_glue.rs:794-914`) is **not wrapped in an outer transaction**, so a mid-loop 409 leaves earlier commits committed.

Also note omi's current sync advances its cursor on **HTTP 200 alone** without checking the returned `applied` count — fixed on the security branch; don't reintroduce it.

## B6. Definition of done

- Screenshots, `ocrText`, `ocrDataJson`, and screen embeddings appear in **no** outbound request from either path. Verify by proxy capture, not by reading code.
- `screen_activity` Firestore collection and Pinecone ns3 receive no new writes.
- `SurfaceParityCapture` retains no OCR.
- The existing web/Flutter graph UI renders graph data derived from screen activity.
- No web recall route exists.
- Rewind still captures, searches, and replays locally with no regression.
- A test asserts the sync payload contains no OCR/image field — this is exactly the class of guard that would have caught path 2.

## B7. Unresolved — answer before coding

1. Does "never images" include inference-time transmission to third-party LLMs (§B3)?
2. Claim/evidence triples or entity/edge nodes (§B2.2)?
3. On-device extraction (macOS-only) or proxied (everywhere, but OCR transits the backend)?
4. Migrate or delete existing `screen_activity` data?
5. Is "query screen history from a non-desktop surface" a shipped promise? This also gates `docs/architecture/local-first-agent-migration.md`.
