# Mac→Windows Parity — Sequencing & Effort Plan

> **Rewritten 2026-08-22, afternoon pass.** This file **replaces the 2026-08-22 morning version
> in place** (which itself replaced a 2026-08-20 draft). Two things broke the morning version
> within hours of it being written:
>
> 1. **Its factual basis was stale.** It was built from a 2026-08-20 audit that described a
>    Windows app largely without a proactive-assistant framework, without a shipped agent kernel,
>    without shipped voice-hub/warm-PTT infrastructure, without a shipped Rewind semantic-search
>    stack, and so on. Files `01`–`13` were **completely rewritten** on 2026-08-22 after
>    discovering that almost all of that "absent" framework-level work had actually shipped
>    between **2026-07-11 and 2026-07-29** — three to six weeks *before* the stale audit was
>    written. Sizing this plan's waves as "build the coordinator, then build Focus/Task/Memory on
>    top of it" was building a plan for work that was already done.
> 2. **It never reconciled with the other planning docs already living in this directory.**
>    `PARALLEL-PLAN.md`, `track2-execution-plan.md`, and `TRACK4-PLAN.md` already carry
>    more-detailed, more-current execution plans for large slices of this work (agent runtime,
>    voice/PTT, Rewind+shell, respectively), and `WIRING-AUDIT.md` already tracked and closed a
>    Critical/Major bug list. The morning version re-derived overlapping "build this from
>    scratch" waves instead of scoping around what those docs leave undecided.
>
> This version is built from the **freshly rewritten** `01`–`13` (each independently re-verified
> against current source, with `git log` dates) and explicitly **reconciles** with the four other
> planning docs rather than re-deriving their territory — see "How this reconciles" below. Where
> a wave's execution detail already lives in one of those docs, this file says so and scopes
> itself to what's left, rather than restating it.
>
> **Method.** Every item traces to a specific finding in `01`–`13`, cited inline as `[file#]`.
> Effort is a rough relative size, not a calendar commitment: **XS** (< 1 day), **S** (2–4 days),
> **M** (1–2 weeks), **L** (3–5 weeks), **XL** (multi-month / its own initiative). Sizes assume
> one engineer familiar with the subsystem; parallel workstreams shrink wall-clock time, not
> total effort. No velocity data exists for this codebase — treat sizes as ordering signal, not a
> committed schedule.
>
> **Scope note.** "Windows" means the single Electron codebase that ships both Windows and Linux
> builds — every item lands on both platforms at once.

---

## TL;DR — recommended order

1. **Wave 0 (quick wins)** first — almost every item is "wire a setting/UI onto a capability
   that's already built," days of work, zero architectural risk.
2. **Waves 1–2 (Chat/agent runtime richness, Voice/PTT residual depth)** next, in parallel — both
   are the *remaining* slice of work `PARALLEL-PLAN.md` Stream 1 and `track2-execution-plan.md`
   scoped in detail; most of each plan's original scope has already shipped, so read this as
   "what's left," not "start here."
3. **Wave 3 (Rewind/Conversations/Shell residual)** in parallel with 1–2 — same relationship to
   `TRACK4-PLAN.md`: most of its PR sequence has landed; this wave is the remainder.
4. **Wave 4 (proactive-assistant polish)** and **Wave 5 (Tasks/Goals depth)** next — Wave 5's two
   largest items (task chat, "Execute") depend on Wave 1's agent-kernel surface, which is already
   shipped per `[04]`, so they can start immediately once staffed, not after a framework lands.
5. **Wave 6 (onboarding intelligence)** is the single largest remaining capability gap in the
   whole audit (enrichment synthesis) — schedule it opportunistically in parallel with 4–5, no
   hard blocking dependency either way.
6. **Wave 7 (app shell & settings polish)** is opportunistic, lowest average value per item.
7. **Wave 8 (Persona)** stays parked — it needs backend routes that don't exist yet; not
   schedulable as Windows client work today.
8. **Wave 9 (BLE/wearables + offline WAL)** stays deferred until product un-defers Phase 7,
   unchanged from every previous pass of this plan.

---

## How this reconciles with the other planning docs

| Doc | What it already covers in detail | What this plan does instead |
|---|---|---|
| `PARALLEL-PLAN.md` | 4 worktree streams for agent runtime, voice/bar, proactive/memory, rewind/shell. Per `[04][06][07][01][02][03][05][11][12]`, **the large majority of all four streams' original scope has shipped** (kernel, control-plane, agent pills, coordinator, Focus/Insight/Memory/Task/Goal assistants, warm-hub PTT, tool-calling, Rewind semantic search, LiveNotes, speaker naming, trial/paywall, etc.). | Wave 1 = Stream 1's residual. Wave 2 = Stream 2's residual. Waves 3–5 = Streams 3–4's residual. This plan does not re-list what already shipped; see each audit file's own "Changed since 2026-08-20" section for the shipped inventory. |
| `track2-execution-plan.md` | A 4-wave PR sequence for voice/PTT depth, synthesized from 10 ground-truth docs. Per `[06][07]`, **Waves 1–3 of that sequence have shipped** (TTS chunking, warm-hub reducer, per-provider barge-in fix, vocab boosting, language-ID feed-forward, system-audio mute, auto-model selection, about-user card, usage limiter) and **Wave 4 (in-session tool-calling, voice turns into kernel history) has also shipped**, ahead of that doc's own sequencing (it expected Wave 4 to block on Track 1's kernel; the kernel landed and both tracks' work landed together). | Wave 2 here lists only what `track2-groundtruth`'s own docs flagged as deferred-not-built (cross-provider failover, BYOK realtime, in-turn vision, capability self-model, a few named tools) plus items `[06]` found still missing on the bar surface. Read `track2-execution-plan.md` for *why* those were deferred — this file does not re-argue it. |
| `TRACK4-PLAN.md` | An 11-PR sequence for Rewind/Conversations/shell. Per `[05][09][11][12][13]`, **PR0–PR4, PR8, PR10, and most of PR6/PR9/PR11 have shipped** (FTS5+embeddings, day-scoped redesign, capture durability, corruption recovery, LiveNotes, KG viewer, SKIP_DIRS/fail-open-deletion fixes, crash-sentinel, post-hoc speaker naming). | Wave 3 here is what's left: PR7 (crash-mid-recording durability — confirmed still absent in `[09]`), the periodic-rescan half of PR9 (confirmed still absent in `[11]`), and the live-naming half of PR6 (confirmed still absent in `[12][13]`). **PR5's conversation-folders/merge/starred redesign is not re-verified by any of `01`–`13`** (it falls between the Rewind, WAL/sync, and app-shell audit files' stated scopes) — flagged below as "needs a status check," not scheduled as a gap, since this plan only schedules what a current audit file confirms. |
| `WIRING-AUDIT.md` | A Critical/Major bug list from 2026-07-13. Its own header says **C1–C9 are fixed** (C10 needed no fix); most Majors are fixed too, confirmed independently by `[07][09]`. | Its still-open items map onto this plan directly: BYOK-on-listen-socket → Wave 2; app-crash-mid-recording durability → Wave 3; Firebase-token→DPAPI migration and KG grounding (`localAgent.ts` disabled) → Wave 1; device-change/meeting-toast-retry → Wave 2/3 respectively. No new items — cross-referenced so this plan and the wiring audit don't drift out of sync with each other. |

---

## Wave 0 — Quick wins (settings/UI wiring onto already-built capabilities)

Every item here is "the backend logic, data model, or component already exists; nothing reads or
writes it from a UI a user can reach." No architecture risk, no cross-file coordination.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Add `focusExcludedApps`/`focusCooldownMinutes` to the assistant-settings writable-key allowlist + a Settings UI for them | XS | [01] | Data model + gate logic already read these; only the write path is missing |
| Wire Insight's `promptStore.ts` setter + a confidence-slider/prompt-editor UI | S | [01] | Storage shape is already versioned-reset-ready |
| Memory extraction interval/confidence/excluded-apps Settings UI (master toggle already exists) | S | [03] | Three real settings, zero UI reading/writing them |
| Settings toggle for `pttMuteSystemAudio` | XS | [06][07] | Preference + mechanism both already work; just no checkbox |
| Settings toggle for `doubleTapForLock`, and confirm with product that Windows' **default-ON** is intentional (Mac ships default-off) | XS | [06] | Behavioral-default mismatch worth a deliberate product call, not just a UI add |
| Settings toggle for the typed-reply voice-answer preference (`floatingBarTypedVoiceEnabled`) | XS | [06] | Preference is wired end to end; no checkbox exists |
| Surface the backend's `profile` summary sentence from memory-log paste-in instead of discarding it | XS | [10] | Field already comes back from `/v1/memories/extract`, just unread client-side |
| Restore or delete `AutoCreatedTasksStep.tsx` (dead code since a 2026-07-23 commit made Goal the terminal onboarding step) | XS | [10] | Decide product intent, then either re-wire the import or delete the file+test |
| Swap the agent pill's generic Bot icon for the tinted provider logo mark (assets already exist for the Connections panel) | XS | [13] | Pure asset-wiring, no new asset needed |
| Swap the literal `'…'` typing indicator on the default main-chat surface for the existing 8-dot `OmiThinkingSpinner` (already used on the bar overlay) | XS | [13] | Component exists; it's scoped to the wrong `variant` |
| Build a citation-card renderer against `ChatMsg.citations` | S | [04][13] | Data is plumbed end-to-end from the SSE stream; zero rendering consumer exists |
| Confirm whether `PARALLEL-PLAN.md` decision-gate #8's required safeguards (fallback telemetry, continuity guard test) actually landed before the default chat engine flipped to the kernel-routed `pi_mono` path | S (verification) | [04] | Both `[04]` and `PARALLEL-PLAN.md` flag this as unresolved — a real risk if the flip happened without the safeguards, cheap to check |
| Resolve why `glow_overlay_enabled` (generated API field) is never read by the renderer even though the glow feature works | XS (verification) | [13] | Either it's gated some other way this pass didn't find, or the field is Mac-only — a quick check with the settings/API owner |

**Total: roughly 1–2 weeks of small, independent items.** No dependency on anything else in this
plan — several of these should ship before any other wave starts.

---

## Wave 1 — Chat & agent-runtime richness (Stream 1 residual)

`[04]`'s headline finding: the ACP coding-agent runtime, kernel, control-plane, and agent-pill UX
that `PARALLEL-PLAN.md` Stream 1 scoped are **already shipped** (2026-07-11 → 2026-07-29). This
wave is what Stream 1's own scope still leaves open, per `[04][11][13]`.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| `toolCall`/`thinking`/`discoveryCard` content-block renderers | M | [04][13] | Types are published in `shared/chatContent.ts`; `agentSpawn`/`agentCompletion` already render — these three don't |
| Chat resource/artifact card rendering (open/reveal) | S/M | [04] | Kernel-side artifact machinery (`artifactStorage.ts`, `kernelArtifacts.ts`) is real and used; no chat-surface component consumes `ChatResource` |
| Stall-detection banner (running→slow→stalled ladder) | S | [04] | Only a coarse 180s hard watchdog exists today |
| Re-enable `localAgent.ts`'s agentic `execute_sql` pre-step (`ENRICH_ENABLED = false`) with the latency budget engineered down | M | [04][11] | Loop is fully built and tested; it was disabled for exceeding its 2.5s budget, not because it doesn't work |
| Upgrade `screenContext.ts` to send a real image, not OCR text only | M | [04][06] | `PARALLEL-PLAN.md` marks this file Stream-1-owned/"do not edit" for other streams — same rule applies here |
| Structured recovery-CTA UI (retry/sign-in buttons) consuming the already-published 5-state `ChatErrorState` | S | [04] | Error copy is already sanitized/friendly; no actionable button exists yet |
| Natural-language multi-agent-spawn parsing from bar text (`spawnFromUserQuery`-style: "spawn 3 agents", "ask hermes to…") | S | [04] | The pill *projection* is a faithful, complete port; only this text-parsing step is thinner than Mac's |
| Decide + build (or explicitly reject) a persistent default-chat-backend picker vs. today's per-message mention-detection | M (pending decision) | [04] | `[04]` flags this as a legitimate open design question, not a bug — needs a product call first |
| Markdown GFM table support | S | [13] | Renderer still degrades tables to plain text |

**Total: roughly 3–4 weeks.** Independent of Waves 2–3; can run on its own team concurrently with
them. Wave 5's task-chat and "Execute" items (below) benefit from this wave's tool-transparency
work but do not strictly block on it — they already have a kernel/tool surface to wire into today.

---

## Wave 2 — Voice/PTT residual depth (Track 2 residual)

Per `[06][07]`, nearly all of `track2-execution-plan.md`'s 4-wave sequence has shipped — TTS
chunking, the warm-hub turn reducer, per-provider barge-in, vocab boosting, language-ID
feed-forward, system-audio mute, auto-model selection, the about-user card, the usage limiter, and
in-session tool-calling with voice turns recorded into kernel history. This wave is the residue
that doc's own ground-truth docs flagged as deliberately deferred, plus a few smaller bar-surface
gaps `[06]` found unrelated to that plan.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Close the voice tool-catalog gap: `ask_higher_model`, `create_calendar_event`, `point_click` have no Windows-serviceable executor | M | [07] | Manifest entries exist tagged voice-eligible; the executor kind is macOS-only or missing entirely |
| Cross-provider failover on a classified live auth/quota error | M | [07] | Same-provider reconnect + circuit breaker now exists and is solid; `hub/hubClose.ts` explicitly documents cross-provider failover as out of scope for "this minimal slice" |
| Client-direct BYOK realtime connection | M | [07] | Blocked on a Windows BYOK key store (Wave 1/Stream 1 territory per `track2-execution-plan.md` §6) |
| In-turn screen/vision context for voice (pixels, not just a text/OCR tool call) | L | [07] | Largest remaining realtime-voice gap; currently `get_work_context` is callable but no image ever reaches the model |
| Deterministic agent-kickoff acknowledgement phrases + exposed playback-speed control | S | [07] | Both confirmed absent by grep; polish on an already-working TTS pipeline |
| Decide whether the realtime voice/hub path should be gated by the same chat usage quota that gates typed/PTT chat | S | [06][07] | Currently ungated on either platform's Windows-relevant contract — flagged, not scored, in both audit files; needs a product call before building anything |
| Rating (thumbs)/share-link on chat responses | S | [06] | Copy button exists; feedback loop and shareability don't |
| File-attachment drag-drop on the floating bar's own input | S | [06] | Exists on the main-window Hub Ask bar already; the bar-specific input never got it |
| Two independent global shortcuts for Ask AI vs. PTT (today: one shared accelerator, tap/hold) | S | [06] | Infrastructure for a second rebindable accelerator already exists (`main/shortcuts.ts`) |
| Live cross-monitor cursor-follow while the bar is open | XS | [06] | Display resolved once at reveal, never re-tracked |
| Deterministic post-STT transcript corrector (Mac's `PTTTranscriptContextualCorrector`) | S (backlog) | [06] | Explicitly deferred by `track2-groundtruth`, not an oversight — low priority |

**Total: roughly 3–4 weeks**, dominated by the vision-in-voice item. Independent of Waves 1 and 3
— separate files, per `PARALLEL-PLAN.md`'s ownership table.

---

## Wave 3 — Rewind / Conversations / Shell residual (Track 4 residual)

Per `[05][09][11][12][13]`, `TRACK4-PLAN.md`'s PR0–PR4, PR8, PR10 and most of PR6/PR9/PR11 have
landed. This wave is the confirmed remainder.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| App-crash-mid-recording segment durability (`TRACK4-PLAN.md` PR7's `rescue_segments`) | M | [09] | Confirmed still absent on every capture lane — a hard process crash loses whatever hasn't reached SQLite yet |
| Reconnect resilience for the screen-session and meeting system-audio capture lanes | S/M | [09] | The continuous-mic lane already got this fix (`liveMicSession.ts`/`liveRescue.ts`); the other two lanes still have zero reconnect on drop |
| Periodic (not just one-shot) background file-index re-scan | S | [11] | `TRACK4-PLAN.md` PR9's SKIP_DIRS + fail-open-deletion fixes shipped; only the periodic-timer half remains — a session left open across a working day never refreshes |
| Live speaker naming during an active recording | M | [12][13] | Post-hoc naming (`TRACK4-PLAN.md` PR6) shipped faithfully; live naming is the confirmed remaining half |
| Speaker color-coding on the two live-recording surfaces (`TranscriptPopup.tsx`, `LiveConversation.tsx`) | S | [13] | The full Mac color/avatar system already exists and is wired for *saved* conversations; pairs naturally with the item above |
| Rewind full-screen playback transport (skip-to-start/end, step-frame, speed menu) | S | [05][13] | A page-level Play/Pause now exists; the richer transport controls still don't |
| Rewind keyboard navigation (arrow-key frame stepping, scroll-to-scrub) | S | [05][13] | `Ctrl/Cmd+F` and `Escape` now work; these two specific interactions — the ones the original gap was really about — still don't |
| Rewind search bar polish: app-filter menu, Today/Yesterday/This-Week quick-date chips | S | [13] | Debounce, keyboard shortcuts, clear button, and a real date picker all shipped; these two remain |
| Search-results filmstrip interaction polish (horizontal hover-lift, scroll-progress capsule) | S | [13] | Now shows real thumbnails + semantic badges; still a vertical list, not Mac's hover-choreographed filmstrip |
| Screen-observations continuous log (a row per analysis pass, not just per successful extraction) | M | [05] | `contextSummary`/`currentActivity` exist only on Memory/Task extraction outcomes today |
| Transcription/live-notes panel on the Rewind page itself | M | [05] | LiveNotes shipped on the Conversations/recording surface (`TRACK4-PLAN.md` PR8); the Rewind page's own panel (PR8's original secondary scope) never landed |
| Screenshot-thumbnail-grid polish (hover delete, OCR badge, group-by-app) + per-app icon rendering | S | [13] | Bundle as one pass — same component family |
| Interactive timeline-bar polish (playhead glow, dashed gap indicators, hover tooltip) | S | [13] | DOM scrubber works; the visual richness doesn't |
| Video-chunk (H.265) storage vs. raw per-frame JPEGs | L (parked) | [05] | `TRACK4-PLAN.md` **already decided**: keep JPEGs, revisit later — don't schedule unless that decision is revisited |
| **Needs a status check before scheduling:** Conversations folders/starred/merge redesign (`TRACK4-PLAN.md` PR5) | — | — | Not re-verified by any of `01`–`13` this pass — falls between the Rewind, WAL/sync, and app-shell audit files' stated scopes. Confirm current status before putting this on a roadmap. |

**Total: roughly 3–4 weeks** excluding the parked video-chunk item. Independent of Waves 1–2 —
separate files per `TRACK4-PLAN.md`'s ownership table.

---

## Wave 4 — Proactive-assistant polish (Focus / Insight / Memory)

The frameworks and the four assistants (Focus, Insight, Task, Memory) are shipped and
coordinator-registered per `[01][02][03]`. This wave is the remaining user-facing/cross-device
polish, distinct from Wave 0's pure settings-wiring items.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Focus dashboard/history page (status banner, stats grid, session-history browse) | S/M | [01] | Data layer (`focus/persist.ts`, `focus/stats.ts`) is written and unit-tested; no IPC or page reads it yet |
| Insight history cross-device sync (today: local-only `insights` table) | M | [01] | Mac's equivalent page is a filtered view over backend memories, so read/dismissed state travels with the account; Windows' page is device-bound |
| Bidirectional assistant-settings sync (server round-trip, not just cross-window local broadcast) | S | [01][03] | Genuinely standalone now that a real framework with real settings exists to sync — no longer "nothing to sync" |
| Memory read/dismiss flags + wire the already-built "this device only" filter to a UI toggle | S | [03] | Filter logic and matching are tested; the Memories page hardcodes `thisDeviceOnly: false` with no chip exposing it |
| Wire the Gmail "session" (cookie-replay) connector into the same memory-synthesis path the OAuth lane already uses | S | [03] | Both lanes read mail; only the OAuth lane currently synthesizes memories from it |
| Staged-task semantic deduplication (hourly pass over the whole staged pool) | M | [02] | Backend only guards an exact-string duplicate at promote time; near-duplicates worded differently both survive |
| Task relevance-prioritization ranking job | M | [02] | `relevance_score` is a real, synced, unused-by-Windows column; `Tasks.tsx` still sorts by due-date only |
| Promotion notification (toast on a staged task promoting to an action item) | XS | [02] | Pipeline is done and deliberately silent today; `assistants/core/notify.ts` is a drop-in delivery path |

**Total: roughly 2–3 weeks.** Can run fully in parallel with Waves 1–3 and 5 — no shared files.

---

## Wave 5 — Tasks/Goals depth

The two largest items here consume Wave 1's already-shipped agent-kernel/control-tools surface —
they don't need to wait for a future kernel, since one already exists per `[04]`.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Per-task "Investigate" AI chat sidebar wired to the agent kernel | M | [02] | A `task_chat` surface kind is already reserved in `agentKernel/types.ts`'s type system with zero wiring — the substrate has a slot, nothing is built on it |
| "Execute" task-row agentic action wired to the existing desktop control-tools stack | M | [02] | `agentKernel/controlTools.ts`'s `route_desktop_intent`/`build_desktop_context_packet` already exist generally; no task row invokes them |
| Daily recurring-task auto re-investigation | M | [02] | Backend wire fields (`recurrence_rule`/`recurrence_parent_id`) exist and are unused by any client code |
| Tasks page richness: filter/sort/tag chips using the already-real `sourceCategory`/`sortOrder`/`indentLevel` columns | S | [02] | Schema has the fields; the UI reads none of them |
| Task-agent status indicator on task rows | XS | [02] | Moot until the Investigate/Execute wiring above exists; trivial once it does |
| Bring `QuickGoalsWidget.tsx`'s Home "suggest a goal" flow up to the same generate→preview→create quality as the Goals page | S | [02] | The two entry points now visibly diverge in quality — a Windows-internal consistency fix, not a Mac-parity one |
| Deepen onboarding's AI goal generation to use the rich context assembler the main Goals page already has | S | [02][10] | Onboarding's `GoalStep.tsx` still calls a thin, app-names-only prompt despite a richer pipeline existing elsewhere in the codebase |

**Total: roughly 3–4 weeks.** The first two items can start immediately in parallel with Wave 1
rather than queued behind it — the kernel surface they need is already merged.

---

## Wave 6 — Onboarding intelligence

The single largest remaining capability gap in the entire audit. Per `[10]`, three of the old
audit's biggest claimed gaps (Data Sources step, memory-log import, connector-driven memories)
turned out to already be shipped — this wave is what's still genuinely missing.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Enrichment synthesis: merge file-scan + email + calendar + memory-log signal into one profile summary, a compact KG entity list, and goal suggestions | M | [10][11] | The largest single remaining gap in this file — real per-source LLM extraction exists (Gmail sync, memory-log paste) but nothing merges it into Mac's "connective tissue" moment |
| Move (or duplicate) the already-built local semantic entity-extraction job into onboarding's own timing, and surface its narrative result to the user | M | [11] | The entity-extraction/narrative-synthesis engine itself has existed since the app's first commit; it just runs silently, post-onboarding, and is never shown |
| Web research (search the user by name/email/org to enrich their profile) | M | [10] | Confirmed still fully absent — no search call anywhere in the renderer or main process |
| Data Sources step polish: live per-source scan progress, per-source profile-summary surfaced in the UI, KG integration nodes on connect | S/M | [10] | Calendar/Gmail OAuth + memory-log paste already work; these three finishing touches don't exist |
| Surface the Exports step (Notion/Obsidian/ChatGPT/Claude/agent MCP setup) inside the onboarding flow | S | [10] | The underlying export capability already exists elsewhere in the app (Settings → Advanced, Hub → Connections) — this is exposure, not construction |
| Language step: multi-select with a primary, not a single English/Other choice | S | [10] | — |
| Accessibility-equivalent permission step (active-app awareness) | S | [10] | May reflect a genuine platform difference from macOS Accessibility, but there's still no messaging/consent step of any kind |
| Voice/Ask demo depth: wait for a completed AI round trip instead of unlocking Continue on capture/timer alone | S | [10] | Applies to both `AskDemoStep.tsx` and `VoiceIntroStep.tsx` |
| Post-onboarding prompt suggestions | S | [10] | Downstream of the enrichment item above — little personalized content to suggest from until that lands |

**Total: roughly 4–5 weeks.** No hard dependency on Waves 1–5, though the enrichment item is
meaningfully more valuable once it can draw on the memory/AI-profile infrastructure that already
exists (it already does — no additional wave needs to land first).

---

## Wave 7 — App shell & settings polish

Lowest average value per item in this plan; schedule opportunistically.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Permissions repair page (Grant/Reset/Fix flow for denied/broken/stale states) | M | [12] | Sidebar footer still has only two on/off toggles; real registry-backed mic-permission detection exists with no repair UI wired to it |
| Daily/Weekly score gauge + recent-conversations widget on the redesigned Home | S | [12] | The Hub itself shipped and is now the default landing surface; these two widget slots are still empty |
| Dedicated Floating Bar + Permissions Settings sections (Windows currently folds both into other tabs) | S | [12] | Mac promoted Permissions into its own Settings sidebar section in the interim, widening this gap slightly |
| Settings search: scroll-to/highlight the specific matched control (search itself is already genuinely cross-tab) | S | [12] | Downgraded from a capability gap to a polish gap — the harder half already shipped |
| Referral program / signup-first-redemption UI | S (product-decision-gated) | [12] | A brand-new Mac feature (2026-08-20/21); confirm product wants a Windows equivalent before building |
| Help / Crisp support chat | M (parked) | [12] | `TRACK4-PLAN.md` already parks this as a vendor decision, low priority — About tab links `help.omi.me` meanwhile |
| Sentry heartbeat breadcrumb (periodic, distinct from the already-shipped crash-sentinel) | XS | [12] | Boot-time crash detection now exists (`crashSentinel.ts`); the separate periodic-breadcrumb telemetry Mac also has still doesn't |
| Close the Gmail loopback-OAuth-vs-session-cookie lane seam (Hub card says "Requires setup" while Settings' session lane already works out of the box) | S | [12] | A real, confusing inconsistency between two surfaces offering the same feature |
| Sound-cue feedback pairing with the already-shipped Glow overlay (focus-lost/regained audio) | XS (backlog) | [13] | The visual half now exists; only the audio half is missing |
| Full adoption of the named CSS radius scale at older call sites (cosmetic tech debt) | XS (backlog) | [13] | The scale itself now exists; most call sites still use ad hoc Tailwind classes |
| Spatial overlay (screen-anchored coach-mark) | L (backlog) | [12] | Low value; the Exports/MCP hub it would eventually support is already built and shipped without it |
| Sidebar tier-gating | — (skip) | [12] | No current product signal that progressive nav-item unlocking is wanted on Windows |

**Total: roughly 2–3 weeks** of scheduled items, plus a few backlog/parked/skip items.

---

## Wave 8 — Persona (parked, backend-blocked)

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Persona / AI-clone (public persona built from public memories, chat-able by others) | XL if/when unblocked | [03] | Confirmed still fully absent, and **cannot be built as Windows client work today** — the backend has no persona routes at all, even in the generated OpenAPI client. This is a backend project first. |

Not schedulable until backend work exists. Revisit if/when that lands.

---

## Wave 9 — BLE/wearables + offline WAL (deferred, hardware-gated)

Unchanged in substance from every prior pass of this plan. Per `[08][09]`, nothing shipped here
(nor was anything expected to) — the entire subsystem remains explicitly deferred (Phase 7) and
is corroborated as such by every audit file that touches it.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| WinRT BLE scan/discovery + GATT UUID registry (→ replaces CoreBluetooth) | L | [08] | Mac's own session/reliability layer (lease + generation-fencing + operation broker) is the reusable design to replicate, independent of transport choice — study it before writing any Windows BLE code |
| Device connection base class + 7 device-type subclasses (Omi/OpenGlass, Friend, Bee, Fieldy, Frame, Limitless, PLAUD) | XL | [08] | Limitless alone is a bespoke hand-rolled protobuf implementation with three prior crash-hardening passes to transliterate correctly |
| BLE audio pipeline (frame reassembly + Opus/AAC/µ-law/LC3 decode) | L | [08] | The least platform-coupled piece — highest-leverage file to port first once BLE exists at all; LC3 itself is unimplemented on *both* platforms today |
| WAL raw-audio buffering + `POST /v2/sync-local-files` upload/reconciliation | M | [09] | Zero Windows counterpart exists; hard-blocked on BLE (no frame source to buffer) |
| BLE SD-card storage sync + WiFi sync + Storage Sync UI | M | [09] | Meaningful only once a device connection exists to pull from |

**Total: multi-month.** Do not schedule until product un-defers Phase 7 and test hardware is
available on the Windows box — nothing here is separable from BLE support existing first.

---

## Dependency graph (informal)

```
Wave 0 (quick wins) ─── no dependencies, do immediately, mostly independent of everything below

Wave 1 (chat/agent runtime residual)  ──┬── feeds Wave 5's task-chat / "Execute" items
                                         │   (kernel/tool surface already shipped — not a hard block,
                                         │    just where the tool-transparency work that makes those
                                         │    features legible also lives)
Wave 2 (voice/PTT residual)      ─── independent — separate files (PARALLEL-PLAN.md ownership table)
Wave 3 (rewind/conv/shell residual) ─ independent — separate files (TRACK4-PLAN.md ownership table)

Wave 4 (proactive-assistant polish) ─── independent — no shared files with 1–3

Wave 5 (tasks/goals depth) ──── two items benefit from Wave 1's tool surface, already shippable now
Wave 6 (onboarding intelligence) ─ independent; more valuable once memory/AI-profile work is
                                    consumed — that work already shipped, so no wait needed
Wave 7 (app shell/settings polish) ─ independent, opportunistic, lowest average value

Wave 8 (Persona)        ─── parked — blocked on backend routes that don't exist
Wave 9 (BLE + offline WAL) ─ deferred — blocked on product un-deferring Phase 7 + test hardware
```

## What this plan deliberately does not do

- **No calendar commitment.** Sizes are relative-effort ordering signals, not sprint estimates.
- **No headcount/team-assignment recommendation.** Waves 0–7 are independent enough to staff
  opportunistically; how many run concurrently is a staffing decision, not a sequencing one.
- **No re-litigating "Windows-ahead" areas.** Every audit file's own callouts (adaptive-noise-gate
  waveform, local KG schema, one-shot UI-automation planner, markdown link-safety, tray icon
  states, the Focus glow overlay's live-target-tracking, Windows' DB-corruption salvage covering
  every table vs. Mac's screenshots-only recovery, and more) are not touched here — porting any of
  those *toward* Mac would be a regression, not progress.
- **No re-deriving execution detail that already exists.** Where `PARALLEL-PLAN.md`,
  `track2-execution-plan.md`, or `TRACK4-PLAN.md` already specify file-level PR sequencing for a
  slice of work, this plan references that doc and scopes itself to the remainder rather than
  restating it.
- **No product-scope calls.** Referral UI, Help/Crisp, the default-chat-backend picker, the
  `doubleTapForLock` default-polarity mismatch, and the realtime-voice usage-quota question are
  all flagged as needing a decision, not silently resolved either way.
