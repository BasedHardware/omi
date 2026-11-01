# Local inference architecture

`LocalInference/` owns on-device generation and embeddings. Local engines never
open a cloud LLM client. Capture and OCR remain independent of vector generation.

## Screen vector entitlement and routing

`ScreenEmbeddingPolicy` synchronously peeks `ScreenCloudEntitlementService`'s
owner-session-bound server subscription cache. The five-minute TTL bounds stale
paid grants. Missing/expired/revoked authority denies cloud spend and coalesces a
background refresh (15-second deadline, 30-second failure retry floor); capture
never awaits it. Launch/sign-in/checkout's existing `FloatingBarUsageLimiter`
fetch also seeds it. Fresh Free/Plus replies beat persisted paid UI hints.
Owner transitions invalidate receipts, including same-user reauthentication;
late subscription replies cannot repopulate a replacement session's cache.
Free, Plus, mobile-only Unlimited-v2, missing and unknown plans never authorize
Gemini embeddings. Active Pro (`operator`), Architect (including legacy `pro`),
and Neo (`unlimited`) before its server-reported desktop grandfather deadline
retain Gemini upload plus local desktop retrieval. BYOK does not grant cloud
screen-vector storage.

TODO(#21488 follow-up): replace the temporary plan derivation with the server's
`cloud_screen_vectors` capability when the subscription wire supplies it. Main
currently exposes no such capability. Plan identity alone must never imply that
Plus has Pro-only screen context.

Local embeddings default **on in Stable, Beta and dev** (David, 2026-10-18).
`LocalEmbeddingRuntime.makeDefault()` registers Apple `NLContextualEmbedding`
(`apple_nlce`, macOS 14+). A bounded synthetic probe verifies assets, vectors and
latency before selection. Probes are cached for 60 seconds by model, thermal state
and kill switches. Missing assets or a failed/slow engine use FTS-only without
calling Gemini for plans lacking cloud vectors. A query failure after selection
also remains FTS-only. Rewind UI and chat use `ScreenHistorySearchRoute`.

Capture schedules local indexing after OCR without awaiting it. The Gemini queue,
flush, every backfill batch, and the final single/batch HTTP dispatch recheck
entitlement. A downgrade drops queued cloud projection work; OCR remains intact
and local backfill can recover vectors. Backfill is AC-bounded. Local vectors live
only in `local_embeddings`, keyed by source kind, source id and model id; they
are never uploaded as Gemini vectors. Hybrid search fuses FTS and cosine via RRF.

Every outbound single/batch embedding requires an explicit runtime owner
snapshot. OCR pins it when queued, backfill/search before reads, and task
backfill before loading rows. Authority is checked after auth and immediately
before HTTP; owner transition or missing authorization cannot use the next
account's token, regardless of a cached paid plan. Local writes retain owner
mutation commit leases.

Both sync paths deliver vectorless OCR and retain durable optional-projection
receipts. Legacy cursor delivery waits for completed five-minute buckets and
skips empty captures; pending text advances its cursor independently of vectors.
A `textSynced` row with a later Gemini vector is selected independently of that
cursor, and becomes `fullySynced` only after vector delivery succeeds. Free/Plus
strip stored cloud vectors while keeping text-first state for a later upgrade;
they do not repeatedly upload those rows. Failed/revoked pushes never acknowledge
rows. Sync headers and acknowledgement commits bind the captured owner. The
legacy cursor has owner-keyed persistence and monotonic saves under a session
mutation lease. A missing owner key starts at zero; the unowned historical cursor
is never adopted or claimed. Legacy pending rows may be re-delivered once in
100-row batches rather than risk skipping another owner's history.
Cloud screen rows remain readable by time/app even without vectors.

Cloud embedding recovery is coalesced in `OCREmbeddingService` for both startup
callers and every sync tick. Missing/expired grants, battery power, transport
errors and interrupted runs retain a 60-second retry floor. Completion schedules
a five-minute missing-vector probe so rows captured during a later unknown grant
can recover, including Stable's legacy path with an old completed marker. The
legacy rearm uses the existing missing-embedding index and an existence query;
lossless retains its completed-bucket winner rearm. Progress commits after each
batch. Attempted documents, including failed batches, share one process-launch
budget (500 lossless / 5000 legacy); retries and owner resets cannot replenish
it. Batch calls are at most 100 documents and stop on battery or revoked authority.
No per-frame polling or recovery telemetry is added.

## Kill switches and capability signal

- `OMI_LOCAL_EMBEDDINGS=0` (also `false`/`off`) or UserDefaults
  `localEmbeddingsEnabled=false`: disable local vectors. Entitled plans use legacy
  Gemini search; other plans keep FTS. Explicit environment wins over defaults.
- `OMI_DISABLE_LOCAL_EMBEDDINGS=1` or `disableLocalEmbeddings=true`: hard kill local
  vectors and omit `X-Omi-Local-Embeddings`. **This deliberately does not restore
  Gemini for unentitled plans**, unlike the closed, unmerged #13473 design.
- `OMI_FORCE_LOCAL_EMBEDDING_ENGINE=<id>` or `forceLocalEmbeddingEngine`: unknown
  engine ids fail closed to FTS.
- Every Gemini proxy request, including generation/streaming clients, sends
  `X-Omi-Local-Embeddings: 1` through `applyGeminiProxyHeaders` unless hard-killed.
  The signal declares client capability, not a successful model probe or spend
  authorization. Local opt-out still sends it so it cannot bypass server policy.

The existing remote `free-tier-kill-switch-v1` stops local vectors and summary
attachment on a definitive boolean true. `LocalCapabilityRemoteKill` reads only
the SDK cache, without fetching or emitting exposure events. Missing/unknown
values leave defaults on. The normal SDK refresh owns delivery latency; in-flight
local model calls may finish. This never grants absent cloud-vector entitlement.
No new PostHog row or production remote configuration is created here. The backend
follow-up must add macOS to this existing row's registry surfaces (the current
registry lists backend only) and retain `FREE_TIER_EMERGENCY_STOP` server-side.

Route and local embedding fallback telemetry stores only bounded decisions and
emits on changes. There is no per-frame event or hourly heartbeat, content, path,
query, or unknown raw plan identity.

## Conversation summaries and funding

`FreeTierLocalProcessingFlag` defaults on in every channel. Explicit
`OMI_FREE_TIER_LOCAL_PROCESSING=0` or `freeTierLocalProcessing=false` stops local
projection attachment. `OMI_DISABLE_LOCAL_INFERENCE=1` / `disableLocalInference`
stops generation; the existing deterministic minimum remains available. AFM is
selected only when its availability probe succeeds (macOS 26+, Apple Intelligence
ready). macOS 14 and unavailable AFM retain the existing loopback-engine then
deterministic-minimum fallback; no cloud fallback is introduced.

`LocalProjectionFinalization.fundingUnavailable` consumes the subscription's
`transcription_allowance`: `managed` keeps uploads unchanged. `on_device` with
zero remaining seconds and `usage_budget_exhausted` proves a ladder shared cap.
Legacy `plan_allowance_exhausted` / `subscription_inactive` attach only for basic;
a paid user's legacy STT cap does not prove summary funding is exhausted. Unknown
reasons, `allowance_unavailable`, `usage_invalid`, malformed or blocked allowance
do not classify a funded user as unfunded. Without this
field, only identified basic without BYOK takes the current-main legacy local
processing path. BYOK leaves processing server-owned.

TODO(#21488 follow-up): after #21488 and the backend fold, consume a dedicated
funded-processing capability if introduced. #21488 projects the ladder shared
funding answer through `transcription_allowance` with `usage_budget_exhausted`.
Its legacy shared-cap path reuses `plan_allowance_exhausted`, which is ambiguous
with current main's STT-only snapshot: paid legacy overflow needs a dedicated
funding signal in the follow-up. Current main's transcription exhaustion alone
does not enforce a shared cloud-processing cap on the server.

Upload reuses the existing schema-v1 `client_processing` projection and transcript
hash contract (`backend/models/client_processing.py`, read-only inspection).
Projections remain display-only, never canonical `structured`, task/memory/vector
input. Stored retry bytes and thermal stored-only behavior are unchanged. Backend
policy chooses whether to display a projection; this client change neither changes
backend admission nor guarantees it is active in production.

## Rollout and measurement gates

Parent PR must remain draft: Beta first, inspect local/hybrid/FTS routes, vectorless
sync, and funded-versus-local upload behavior; then explicitly promote Stable.
Backend dependency: #21488 (open at implementation) followed by the entitlement
and capability fold of `BASIC_PLAN_GATE_PROXY_EMBED_ENABLED`,
`BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED`, and `FREE_TIER_LOCAL_PROCESSING`.
No deployment, remote flag, production channel or account was changed here.

The default-on ruling supersedes #13456's default-off implementation, but does
**not** supply its measurement evidence: current real-Rewind-DB retrieval/latency
and an actual eight-hour energy measurement remain production acceptance gates.
#13473's historical one-Beta-DB results are not current measurements. Hermetic
fixtures and synthetic hash benchmarks establish correctness only, never model
quality or energy. Do not read customer databases to fill this evidence gap.
