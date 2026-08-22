# Ground truth: the Context Director port (buckets, engine, TCRS)

Windows port of macOS's context-bucket proactivity system. Every behavioral
rule was extracted from the Swift sources before any TypeScript was written:
`ContextBucketStore/Schema/Rollup`, `ContextProactivityEngine`,
`ContextDeliveryAuthority`, `ContextDirectorRetrieval`, `ContextVisitCoordinator`,
`ContextDestinationKey`, `ContextTitleNormalizer`, `ContextWorkstreamPooling/Reconciler`,
`ContextSubjectBindingService`, `CandidateSink`, `ProactiveLaneClient`,
`TaskContextualResurfacingService`, `NotificationSettingsSyncCoordinator`, and the
backend facades (`backend/desktop_backend.py` + `routers/desktop_proactivity.py`,
`routers/task_recommendations.py`, `routers/tools.py`, `routers/candidates.py`,
`routers/users.py`). Module-by-module mapping: `src/main/assistants/director/ARCHITECTURE.md`.

## Contract facts the port depends on

Bucket substrate (ported exactly):
- Identity: `sha256:<hex>` over `app::normalizedTitle` (mac-exact normalizer rules,
  in order: braille strip, progress glyphs, clock/dimension regexes, leading unread
  badges for messaging+browsers, trailing counts for messaging only, shell suffixes
  for terminals, whitespace collapse); blank titles get `ephemeral:<uuid>` and never
  share identity. Durable url/file handles override the title hash as the binding key.
- A brand-new context earns its bucket on the SECOND completed visit within 7 days;
  a pre-existing binding skips the gate. Visits qualify at >= 1s dwell; freshness for
  evaluation = active, or completed within 60s; discarded/interrupted never.
- Extraction (one per qualified departure, `proactive_extraction` lane, 1200 tokens,
  strict schema, quota-silent): narrative cap 2400; facts capped 20/500/1000 with the
  evidence-ref allowlist {visit:<id>, screenshot:<frameId>}, bookkeeping-identifier
  regex + evidence-containment filter; duplicate statements become `superseded`;
  `validated` requires an identifier AND evidence text AND refs; worthiness zeroed
  unless validated. Every extraction publishes a bucket version: compaction when >5
  uncompacted entries (all but the newest 5 append as `- entry:<id> <narrative>`
  lines), frozen segment front-trimmed to 16,000 bytes, constant header
  `Persistent work context.` (a prompt-cache prefix — never re-encoded).
- Browser destination routing: the model proposes `<domain>/<section>` once per novel
  browser title; the deterministic sanitizer (exact browser-name set, forbidden and
  messenger labels, the 4-char-substring vs whole-token grounding rule) decides; the
  binder merges future visits into the owning `dest:` bucket (crediting its
  freshness) and never overwrites explicit or previously derived bindings.
- GC: expired deliveries/candidates/facts; buckets idle 30 days (active-visit
  protected); keep the newest 250; abandoned delivery rows (15 min) become
  silence/failed. Cadence: startup + every 24h through the visit coordinator.

Director engine (ported exactly):
- Two triggers only: context entry (2s settle sleep, then the mac step order:
  settle mark -> free gate -> freshness -> snapshot -> eligibility(worthiness>0 &&
  facts nonempty) -> frame sample -> freshness re-read -> frame bound) and departure
  (flag-gated, threshold 0.6 on newly validated worthiness). No timer trigger.
- Transport: POST `{desktopApiBase}/v1/desktop/proactivity/completions` with one
  user message [stable text, volatile text, image_url jpeg], strict `json_schema`
  named `desktop_proactivity`, `cache_key: director:v1`, max 800 tokens, no
  temperature. Client 429 cooldowns per operation, Retry-After clamped [60s, 3600s].
- Prompts byte-for-byte: the untrusted preamble; the director instruction block; the
  optional lookup block; the assembled bucket (header/frozen verbatim/facts <=
  min(8000, remaining)/tail under the 30,000-byte budget); the volatile prompt
  (tasks <=20 with the 48h reference-only horizon, frame metadata, visit count,
  recent-deliveries block <=15 with 320-char summaries); every timestamp rendered
  `yyyy-MM-dd HH:mm zzz` in the user's zone.
- Decision decode clamps 120/600/1200/20x200/200; enum
  suggest|insight|task_candidate|resurface|silence.
- Grounding: non-silence requires >=1 validated own-bucket entry ref AND >=1
  validated fact id (validated against the snapshot's own quoted ids AND live
  validated-unexpired rows); failure rewrites to silence/suppressed. Retrieved refs
  validate only against the per-call allowlist and never substitute.
- One retrieval hop max: admission = flag && priorHops==0 && flattened query in
  [3,200]; three concurrent searches (`/v1/tools/conversations/search` with
  include_transcript false, `/search-chunks`, `/v1/tools/memories/search`), limit 3
  each, independent failure to []; fail-closed item mapping; chunk-wins merge cap 6;
  prompt cap 9; a failed/empty hop keeps the first decision.
- Budget/ledger: reservation per (visitID, bucketVersionID); cooldown anchor =
  max(any deliveredAt, last global proactive presentation, in-flight attemptedAt) vs
  the level ladder {3600/1800/600/180/0}s; trailing-24h count excludes
  suppressed+failed vs base [0,10,20,40,60,100]; rows expire at 30 days; terminal
  rows immutable; provenance JSON with sorted keys.
- task_candidate graduation before presentation: canonical `POST /v1/candidates`
  TaskCreateCandidate per cited fact (source_surface `context_bucket`, evidence ref
  `bucket-fact:<id>` kind local_screen scope device_local version
  `context_bucket.v1`, Idempotency-Key `context-bucket:<factID>`,
  X-Account-Generation from `/v1/candidates/control`), then the local disposition
  flip none -> candidate_pending; failure fails the row with `graduation_reason`.
- Armed-candidate fast path (flag-gated): substitutes a 120-token yes/no gate for
  the director call; Jaccard-0.6 message dedupe vs recent deliveries; grounding
  recheck declines stale candidates; consume only after every gate; restore on drop.

TCRS legacy path (runs when the pipeline flag is OFF — mac's exact inversion):
- Event kinds person|app_window|document|meeting|free_time|dependency|agent with the
  app_window -> `app` signal rename; urgency can_wait|time_sensitive affects only
  the material-hint suffix and interruption eligibility. Subject equality is
  (kind, id) — workstreamID excluded.
- Raw references are trimmed, lowercased, sha256'd in the constructor; the wire
  snapshot carries only canonical subject ids + sorted unique signals (cap 32
  matches / 4 signals); the reference hash itself is never sent.
- Pipeline: per-key accumulator (replace-in-place, cap 16) -> 2s trailing debounce
  -> material hint `ctx:<sha256[:32]>` with a 5-minute success-only dedupe ->
  control gate (workflow_mode read + generation) -> PUT
  `/v1/task-intelligence/context-snapshot` (snapshot_id `ctx-<uuid>`, expiry +5min,
  Idempotency-Key = snapshot id, X-Account-Generation) -> POST
  `/v1/what-matters-now/evaluate` ({device_id, material_hint}) -> projection push.
  Errors log once, no retry; the dedupe memory advances only on full success; owner
  lease re-checked after every await.
- The interruption gate (12 reasons in mac's exact order) ships with the all-off
  safe default (userOptedIn false); no Windows opt-in surface exists yet, so only
  the dashboard lane is wired.
- Device identity: the renderer's `getWindowsDeviceIdHash()` (sha256(install-id)[:8])
  is relayed to main over `director:setDeviceId` so main-side snapshot calls share
  the renderer's device scope — mixed scopes would 403.

Settings sync: GET/PATCH `/v1/users/notification-settings`; local-authoritative
revision journal in appSettings; PATCH pushes the complete local pair; hydrate only
when nothing pending and the revision held across the GET; 1s -> 15min capped
doubling backoff; reconcile on startup once a session is relayed.

## Deliberate deviations (Windows-shaped, called out so they are decisions)

- **Rollout**: mac runs the pipeline on the beta bundle only; Windows has one
  channel, so the pipeline ships dark behind the `contextDirectorEnabled` Settings
  toggle (default OFF) with `OMI_FORCE_CONTEXT_BUCKETS` for dev. TCRS covers the
  flag-off world exactly as on mac.
- **The workstream reconciler is not ported** (the 15-minute tagging/candidate
  writer): mac holds it hard-off in production and beta. The ledger schema, armed
  candidates, pooling rules, and the engine's candidate fast path are all ported
  and tested; the flag surface (`OMI_FORCE_BUCKET_WORKSTREAMS/CANDIDATES`) is
  reserved. Tracked as a follow-up.
- **No durable url/file handle producer yet**: mac scrapes browser URLs via the
  accessibility API; Windows frames carry no URL, so handles are modeled and
  tested but no producer supplies them — destination routing (which needs no URL)
  is the browser-collapse mechanism. `WorkHistoryHandleExtractor` is the follow-up.
- **poolEpoch is constant 1**: better-sqlite3 is one process-lifetime handle and an
  account switch wipes the tables (USER_DATA_TABLES), so mac's pool-generation
  fencing degenerates to the session epoch + wipe.
- **`lastFrameId` has no FK** to rewind_frames (mac: screenshots ON DELETE SET
  NULL): rewind retention owns frame deletion; evidence refs keep the opaque
  `screenshot:<id>` string format.
- **mac's `bundleID` column is `processName`** (the Windows process identity).
- **Presentation**: director decisions deliver through the existing
  `notifyProactive` funnel (budget/snooze/toast), which is synchronous — mac's
  queued-card + system-banner fallback machinery has no Windows analog yet, so
  `onPresented`/`onDropped` resolve at the notify boundary.
- **Paywall + plan multiplier**: no desktop paywall state exists in main;
  `paywalled` is false and the budget multiplier is 1 (both parameters, ready for
  the signals).
- **Telemetry**: mac's PostHog events (decision, gate-rejection stages, extraction
  outcomes, the paraphrase shadow signal) have no main-process analytics transport
  on Windows and are not emitted; the durable `proactive_deliveries` provenance
  rows carry the audit trail.
- **Settings-sync PATCH always carries `enabled`**: mac omits it when the master
  key was never locally written to protect its Balanced-default migration push;
  Windows has no migration push (frequency default stays 0 = Off) and its first
  PATCH only happens on a real user mutation. The Balanced(3) migration itself is
  NOT ported — flipping existing users' notification default is a product call.
- **Legacy UserDefaults import**: no Windows analog ever existed; the
  migration-meta table stays for provenance parity, the import logic does not.
- **TCRS producers**: app_window switches are wired; meeting/agent producers (mac:
  meeting-detector edges, agent-run completions) need main-side sources that do
  not exist yet and are follow-ups; person/document/free_time/dependency are
  probe-only on mac too.
