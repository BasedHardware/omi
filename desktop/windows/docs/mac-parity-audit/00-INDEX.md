# Omi Mac → Windows Parity Audit — Master Index

> **What this is.** A documentation-only survey of features, capabilities, behaviors, and enhancements the **macOS** Omi desktop app has that the **Windows** app does not (or does more weakly). It exists to feed a later planning session — **no fixes, plans, sequencing, or effort estimates are proposed here.** Each entry says *what the feature is, where it lives (files + symbols), how it works, and the exact Windows status*.
>
> **How it was produced.** A fleet of 13 parallel research agents, one per macOS subsystem, each read the Swift/TS source deeply (several ran their own sub-fleets of line-by-line deep-reads), then verified the Windows side by reading and grepping `desktop/windows/` before declaring any gap. Every "Absent/Partial" claim is grounded in a specific file check, not assumption.
>
> **Scope of the baseline.** Windows has already shipped Phases 0–6 (tray lifecycle, hidden-capture-window + AudioWorklet + VAD, conversation sync, top-edge bar + orb, meeting detection, realtime voice, OAuth, backend chat). Those are **not** reported as gaps. BLE/wearables (Phase 7) and the ACP coding-agent runtime are known-absent.
>
> **Shared backend caveat.** Both apps call the same Python backend and desktop Rust backend, so some "Mac features" are backend-driven and already reachable from Windows — several already have generated API clients with **zero callers** (see *Quick Wins*). Local-only-to-Mac features (proactive assistants, on-device embeddings/VAD, CoreBluetooth) are flagged as such.
>
> **Baseline date.** Files `01`–`13` and the sequencing plan (`14`) were **fully redone on
> 2026-08-22**, re-verified against current source rather than the earlier 2026-08-20 snapshot
> that the first pass of this audit and plan had been built from (that snapshot had gone stale:
> several "absent" items had actually shipped in the weeks before it was written). This redo also
> **reconciles explicitly** with the other execution-planning docs already living in this
> directory — `PARALLEL-PLAN.md`, `track2-execution-plan.md`, `TRACK4-PLAN.md`, and
> `WIRING-AUDIT.md` — crediting what they show as already shipped and scoping `01`–`14` to what
> those docs leave open, rather than re-deriving their territory.

**~200 distinct items documented across 13 areas.** Detail lives in the per-area files below; this index is the map + the cross-cutting synthesis.

---

## The 13 area files

| # | File | Area | Items | Headline |
|---|------|------|:---:|----------|
| 01 | [`01-proactive-focus-insight.md`](01-proactive-focus-insight.md) | Proactive engine — Focus & Insight | 16 | The coordinator + Focus + Insight all shipped **2026-07-14–19**, weeks before the stale audit; remaining gaps are narrow — no Focus dashboard page, no prompt/confidence-editor UI, Insight history is **local-only** (no cross-device sync) |
| 02 | [`02-proactive-tasks-goals.md`](02-proactive-tasks-goals.md) | Tasks & Goals AI engine | 20 | Screen-based task extraction, the promotion pipeline, auto goal generation, and goal insight/celebration all shipped; still absent: per-task **"Investigate" chat**, task-row **"Execute"**, staged-task semantic dedup, and a task-prioritization ranking job |
| 03 | [`03-memory-persona-profile.md`](03-memory-persona-profile.md) | Memory extraction, Persona, AI profile | 11 | Continuous memory extraction, the **AI User Profile**, embeddings, and connector imports all shipped; **Persona/AI-clone remains fully absent and backend-blocked**; extraction settings UI and cross-device sync are the real remaining gaps |
| 04 | [`04-chat-agent-runtime.md`](04-chat-agent-runtime.md) | Chat + ACP agent runtime | ~24 | The full ACP kernel, control plane, and agent-pill UX **already shipped 2026-07-11–29** (the old "absent, no PR yet" verdict was wrong the day it was written); remaining gaps are tool-call/thinking/discovery-card rendering, a disabled local-context enrichment step, and screen context still text-only |
| 05 | [`05-rewind.md`](05-rewind.md) | Rewind depth delta | 17 | Semantic search, FTS5, the search UI, date navigation, OCR bounding boxes, and DB-corruption recovery **all shipped and exceed the old claims**; genuinely still weaker: raw-JPEG storage (video chunking is a parked decision), a thin playback transport, no continuous observation log |
| 06 | [`06-floating-bar-ask-ptt.md`](06-floating-bar-ask-ptt.md) | Floating bar / Ask AI / PTT | 17 | TTS read-aloud, the usage limiter, vocabulary boosting, language-ID feed-forward, system-audio mute, and the about-user card all shipped; screen context is **still OCR text only**, and rating/share-link, bar-specific drag-drop, and a second shortcut remain missing |
| 07 | [`07-realtime-voice.md`](07-realtime-voice.md) | Realtime voice depth | 10 | The warm-hub PTT session, in-session tool-calling, rich system instructions, and kernel-recorded voice turns all shipped; the model still **can't see pixels mid-turn**, and cross-provider failover / BYOK realtime remain unbuilt |
| 08 | [`08-bluetooth-wearables.md`](08-bluetooth-wearables.md) | Bluetooth / wearables | 17 | Entire BLE stack still absent (Phase 7 deferred) — **no Windows-side change**; this rewrite mainly corrects a stale Mac reference (a session/reliability-layer rewrite the old audit missed) |
| 09 | [`09-wal-sync-offline.md`](09-wal-sync-offline.md) | WAL / offline / storage sync | 7 | WAL/storage-sync/WiFi-sync remain fully absent, blocked on BLE; but Windows' own continuous-mic realtime-STT path already got **reconnect+resume+silence-keepalive** — only the screen-session/meeting-audio lanes and crash-mid-recording durability are still open |
| 10 | [`10-onboarding.md`](10-onboarding.md) | Onboarding intelligence | 26 | The **Data Sources step** and ChatGPT/Claude memory-log import both shipped; **enrichment synthesis** and web research remain the largest gaps, and the Auto-created Tasks closing screen **regressed into dead code** |
| 11 | [`11-fileindex-knowledge-graph.md`](11-fileindex-knowledge-graph.md) | File index / KG / memory graph | 10 | Incremental scanning, the full-screen interactive 3D graph viewer, and local LLM entity-extraction (KG synthesis) all shipped; periodic re-scan is still absent, and the chat local-context enrichment pre-step remains deliberately disabled |
| 12 | [`12-app-shell-pages-system.md`](12-app-shell-pages-system.md) | App shell / pages / system | 13 | The redesigned **Home Hub**, Imports/Exports connector hub, **LiveNotes**, post-hoc speaker naming, and trial/paywall gating all shipped; **live** speaker naming, a Permissions repair page, and Help/Crisp support remain absent |
| 13 | [`13-ui-components-visual.md`](13-ui-components-visual.md) | UI components & visual layer | 18 | Glow overlay, goal celebration, chat-session history, agent-pill status, font scale, and Mica window vibrancy all shipped; tool-call/thinking/discovery-card rendering and GFM markdown tables remain the largest visual gaps |

---

## Executive summary — the shape of the gap

The 2026-08-20 audit's framing — "the whole intelligence and agentic layer is missing" — was wrong the day it was written. A five-week porting wave (**2026-07-11 through 2026-07-29**) had already shipped the proactive-assistant coordinator and all four assistants (Focus/Insight/Memory/Task/Goal), the full ACP coding-agent kernel + control plane + agent-pill UX, Rewind's semantic-search stack, the warm-hub voice/PTT architecture, LiveNotes, post-hoc speaker naming, trial/paywall gating, and most of the Home Hub / Imports-Exports connector surface — all of it *before* that audit's own stated date. Windows is not "a recorder with a chat box bolted on top of a capture core" any more; it has the same layered intelligence architecture Mac does, running end to end. What remains falls into three genuinely different buckets:

1. **Depth and polish on shipped subsystems (the majority of what's left).** Almost every area file's remaining gaps are narrow and specific rather than architectural: a Focus dashboard page with no UI reading an already-tested data layer (file 01), a disabled `localAgent.ts` enrichment step that works but blew its own latency budget (files 04, 11), a voice tool catalog missing three named tools (file 07), Rewind's playback transport and keyboard scrubbing (file 05), and chat's `toolCall`/`thinking`/`discoveryCard` block types with no renderer even though `agentSpawn`/`agentCompletion` already render (files 04, 13). None of these need new frameworks — they need wiring, UI, or tuning on top of infrastructure that already exists.

2. **A handful of genuinely large, still-open capability gaps.** **Onboarding's enrichment synthesis** — the LLM call that would merge file-scan + email + calendar + memory-log signal into one profile summary, a compact knowledge-graph entity list, and goal suggestions — is the single largest remaining gap in the whole audit (files 10, 11); the per-source extraction it would consume already exists, but nothing stitches it together the way Mac's "connective tissue" moment does. Alongside it: **web research** in onboarding (file 10), a **per-task "Investigate" chat** and task-row **"Execute"** that would wire the already-shipped agent kernel to a specific task (file 02), **live speaker naming** during an active recording (files 12, 13), and **in-turn vision** for both chat and voice — the model still only ever gets OCR text, never pixels (files 04, 06, 07).

3. **Hardware + offline, and one backend-blocked feature — unchanged, deliberately deferred.** The entire BLE/wearable stack (7 device types, codecs, GATT, the WAL offline-buffering that rides on it) remains absent because Phase 7 is explicitly deferred (files 08, 09) — nothing shipped here because nothing was expected to. **Persona/AI-clone** (file 03) is the one feature that can't be built as Windows client work today regardless of priority: the backend has no persona routes at all.

---

## Consolidated top gaps by theme (cross-area)

Value = impact on the Windows product (H/M/L). Tables below list only what's **still genuinely open** per the freshly rewritten files 01–13 — items that shipped between 2026-07-11 and 2026-07-29 (the large majority of what the 2026-08-20 pass called "absent") have been removed; each area file's own "Changed since the 2026-08-20 audit" section has the full shipped inventory if that history is needed.

### A. Proactive-assistant framework — *shipped; remaining gaps are dashboards, tunability, and cross-device sync*
| Gap | Area | Value |
|---|---|:---:|
| Focus dashboard/history page — data layer (`focus/persist.ts`, `focus/stats.ts`) is written and unit-tested, no IPC or page reads it | 01 | M |
| Insight prompt-editor + confidence-slider UI; Focus exclusion-list/cooldown Settings UI (data model ready, no write path) | 01 | S (quick win) |
| Insight history is local-only — Mac's equivalent syncs cross-device via the backend memories API | 01 | M |
| Memory extraction interval/confidence/excluded-apps Settings UI + prompt editor (master toggle already exists) | 03 | M |
| Bidirectional assistant-settings sync (server round-trip, not just cross-window local broadcast) | 01 / 03 | L |
| Memory read/dismiss flags + wire the already-built "this device only" filter to a UI toggle | 03 | S |

### B. AI understanding of the user — *mostly closed; Persona is the one hard remainder*
| Gap | Area | Value |
|---|---|:---:|
| **Persona / AI-clone** — confirmed still fully absent, and **backend-blocked**: no persona routes exist even in the generated OpenAPI client | 03 | M (parked) |
| Onboarding-exploration chat transcript → seed-profile path (Mac-only, no Windows equivalent) | 03 | L |
| Gmail "session" (cookie-replay) connector reads mail but isn't wired to the same memory-synthesis path the OAuth lane already uses | 03 | L |
| Home widget (`QuickGoalsWidget.tsx`) still calls the thin `GET /v1/goals/suggest` with no preview, while the Goals page's own "Suggest" got a richer generate→preview→create flow — the two entry points now visibly diverge | 02 | M |

### C. Coding-agent / ACP runtime — *kernel, control plane, and pills shipped; rendering and a few policy calls remain*
| Gap | Area | Value |
|---|---|:---:|
| `toolCall` / `thinking` / `discoveryCard` content-block renderers — types are published, only `agentSpawn`/`agentCompletion` render | 04 / 13 | H |
| Chat resource/artifact card rendering (open/reveal) — kernel-side artifact machinery is real and used, no chat-surface consumer | 04 | M |
| Stall-detection banner (running→slow→stalled) — only a coarse 180s hard watchdog exists today | 04 | M |
| `localAgent.ts`'s agentic `execute_sql` pre-step remains disabled (`ENRICH_ENABLED = false`) — built and tested, but exceeded its latency budget | 04 / 11 | M |
| `screenContext.ts` still sends OCR text only, never an image, into chat turns | 04 / 06 | H |
| Persistent default-chat-backend picker vs. today's per-message mention-detection — an open product-design question, not a bug | 04 | M (decision-gated) |
| Voice tool catalog gap: `ask_higher_model`, `create_calendar_event`, `point_click` have no Windows-serviceable executor | 07 | M |
| Cross-provider failover on a classified live auth/quota error; client-direct BYOK realtime connection | 07 | M |

### D. Rewind depth — *semantic search and the search UI are done; transport and storage-format remain*
| Gap | Area | Value |
|---|---|:---:|
| Video-chunk (H.265) storage vs. raw per-frame JPEGs — a storage-scalability concern, but **already a parked decision** (keep JPEGs, revisit later), not scheduled | 05 | H (parked) |
| Full playback transport (skip-to-start/end, step-frame, speed menu) — a page-level Play/Pause now exists, the richer transport doesn't | 05 / 13 | M |
| Keyboard navigation: arrow-key frame stepping, scroll-to-scrub — `Ctrl/Cmd+F` and Escape now work, these two don't | 05 / 13 | M |
| Screen-observations continuous log (a row per analysis pass, not just per successful extraction) | 05 | M |
| Transcription/live-notes panel on the Rewind page itself (LiveNotes shipped on Conversations, not here) | 05 | M |
| Search-bar polish (app-filter menu, quick-date chips) and filmstrip hover-choreography | 13 | S |

### E. Voice / PTT depth — *warm-hub, tool-calling, and turn history are done; vision and failover remain*
| Gap | Area | Value |
|---|---|:---:|
| **In-turn screen/vision context for voice** (pixels, not just a text/OCR tool call) — the largest remaining realtime-voice gap | 07 | L |
| Cross-provider failover on a live auth/quota error; client-direct BYOK realtime | 07 | M |
| Voice tool-catalog gaps (see row C above) | 07 | M |
| Rating (thumbs) + share-link on chat responses; bar-specific file-attachment drag-drop (exists on the Home Ask bar already) | 06 | S |
| Two independent global shortcuts for Ask AI vs. PTT (infra for a second accelerator already exists); live cross-monitor cursor-follow | 06 | S / XS |
| Deterministic post-STT transcript corrector — a documented, deliberate deferral, not an oversight | 06 | S (backlog) |

### F. Chat & UI richness — *agent cards, sessions, and font scale shipped; tool transparency and tables remain*
| Gap | Area | Value |
|---|---|:---:|
| `toolCall` / `thinking` / `discoveryCard` cards (see row C) | 04 / 13 | H |
| **Markdown GFM tables** — renderer still degrades tables to plain text | 13 | S |
| Live speaker color-coding on the two live-recording surfaces (the full color/avatar system already exists for saved conversations) | 12 / 13 | S |
| Citation-card renderer — citations are plumbed end-to-end from the SSE stream; no component reads `ChatMsg.citations` | 04 / 13 | S (quick win) |
| Provider logo mark on agent pills (assets already exist, feed the Connections panel instead); typing indicator on the default main-chat surface still literal `'…'` (the 8-dot ring exists, scoped to the bar only) | 13 | XS (quick wins) |

### G. Onboarding intelligence — *Data Sources + memory-log import shipped; enrichment synthesis is the largest gap in the whole audit*
| Gap | Area | Value |
|---|---|:---:|
| **Enrichment synthesis** — merge file-scan + email + calendar + memory-log signal into one profile summary, a compact KG entity list, and goal suggestions | 10 / 11 | H |
| **Web research** (search the user by name/email/org to enrich their profile) — confirmed still fully absent | 10 | H |
| Move (or duplicate) the already-built local semantic entity-extraction job into onboarding's own timing, and surface its narrative result to the user | 11 | M |
| Data Sources step polish (live per-source scan progress, a surfaced profile-summary sentence, KG integration nodes on connect) | 10 | M |
| Surface the Exports step inside onboarding (the underlying capability already exists elsewhere in the app) | 10 | S |
| Language multi-select; an Accessibility-equivalent permission step; voice/Ask demo waiting for a real AI round trip | 10 | S |
| **Regression:** the Auto-created Tasks closing screen is now unreachable dead code (Goal became the terminal step 2026-07-23) — needs a product decision (restore or delete) | 10 | XS |

### H. App shell & pages — *Home Hub, connectors, LiveNotes, and paywall shipped; live naming and repair flows remain*
| Gap | Area | Value |
|---|---|:---:|
| **Live speaker naming** during an active recording (post-hoc naming shipped faithfully; this half is still absent) | 12 / 13 | M |
| Permissions repair page (Grant/Reset/Fix flow) — real registry-backed detection exists with no repair UI wired to it | 12 | M |
| Help / Crisp support chat — a parked vendor decision, not a build gap | 12 | M |
| Daily/weekly score gauge + recent-conversations widget on the now-default Home Hub | 12 | S |
| Referral program UI — a brand-new Mac feature (2026-08-20/21); needs a product decision before scheduling | 12 | S (decision-gated) |
| Dedicated Floating Bar + Permissions Settings sections; settings-search scroll-to-highlight | 12 | S |

### I. Bluetooth / wearables + offline (Phase 7 deferred — entire subsystem, no change)
| Gap | Area | Value |
|---|---|:---:|
| CoreBluetooth-equivalent scan/discovery + GATT UUID registry + transport abstraction (→ WinRT BLE) | 08 | H |
| 7 device connections (Omi/OpenGlass, Friend, Bee, Fieldy, Limitless, PLAUD, Frame-stub) | 08 | H/M |
| BLE audio pipeline (frame reassembly, Opus/AAC/µ-law/LC3 decode) | 08 | H |
| **WAL offline audio buffering** + `/v2/sync-local-files` upload/reconciliation; BLE SD-card storage sync; WiFi sync — blocked on BLE | 09 | H/M |
| App-crash-mid-recording segment durability, and reconnect resilience for the screen-session/meeting-audio capture lanes — **not BLE-shaped, doesn't need Phase 7**, but still open on Windows' own realtime-STT path | 09 | M |

### J. File index / knowledge graph — *scanning and the KG viewer/synthesis engine shipped; two narrow gaps remain*
| Gap | Area | Value |
|---|---|:---:|
| Periodic (not just one-shot) background file-index re-scan — a session left open across a working day never refreshes | 11 | M |
| Chat local-context enrichment pre-step remains disabled (see row C) | 04 / 11 | M |

---

## Quick wins — already built, just unwired or disabled

These need *connection*, not construction. (Two items from the earlier pass of this index no longer belong here: the **Rewind unified search bar** was never actually dead-code-gated — it works today via a persistent search bar, `Ctrl/Cmd+F`, and Escape — and **BrainGraph interactivity** is not a bug to fix — the full-screen `/knowledge-graph` viewer is already fully interactive; only the two small preview cards on Memories/Onboarding are non-interactive **by design**, matching a tradeoff Mac itself made when it dropped its own inline-preview surface entirely on 2026-07-22.)

- **Focus exclusion list/cooldown** and **Insight prompt/confidence editor** — both settings models already exist and are read by the gate logic; neither has a write path or UI (file 01).
- **Memory extraction settings** (interval/confidence/excluded apps) — three real settings, zero UI reading or writing them (file 03).
- **`pttMuteSystemAudio`, `doubleTapForLock`, and the typed-reply voice-answer preference** — all three preferences are wired end to end into working mechanisms; none has a Settings checkbox yet (files 06, 07).
- **Memory-log paste-in profile summary** — the backend's `/v1/memories/extract` already returns a synthesized `profile` sentence; the client computes and discards it (file 10).
- **Citation-card renderer** — citations are plumbed end-to-end from the SSE stream into `ChatMsg.citations`; no component renders them (files 04, 13).
- **Agent-pill provider logo** — the tinted Hermes/OpenClaw logo assets already exist (feeding the Connections panel); the pill itself still shows a generic Bot icon (file 13).
- **Typing indicator on the default chat surface** — the real 8-dot `OmiThinkingSpinner` component exists and is used on the bar overlay; the main-window surface still falls through to a literal `'…'` string because it's scoped to the wrong `variant` (file 13).
- **Promotion notification** — the staged-task→action-item pipeline is fully built and deliberately silent; `assistants/core/notify.ts` is a drop-in delivery path for a "task added" toast (file 02).
- **`AutoCreatedTasksStep.tsx`** — still compiles and passes its own test, but has been unreachable dead code since a 2026-07-23 commit made Goal the terminal onboarding step; needs a product decision (restore the import, or delete the file) rather than more building (file 10).

## Windows-ahead — do NOT regress these when porting

The Windows app is *better* than Mac in a few places; a naive port would be a downgrade:

- **PTT waveform** — Windows' adaptive noise-floor gate + 60fps rAF easing is arguably ahead of Mac's static boost curve (files 06, 13).
- **Local KG** — Windows' KG schema (summary/source/aliases/sourceRefs) + off-thread worker + coalescing write-queue is **more sophisticated** than Mac's (file 11).
- **Focus glow overlay** — a single continuous click-through ring with live target-tracking (it follows a moving/resizing window and dismisses on minimize) is *more* capable than Mac's one-shot four-window edge workaround, which doesn't track a moving target at all (file 01).
- **Rewind DB-corruption recovery** — Windows' salvage engine covers *every* table with per-row isolation, where Mac's `.recover`-based approach salvages only the `screenshots` table and discards the rest (file 05).
- **Goal-suggestion preview flow** — the Goals page's "Suggest" button now does generate→preview→create; Mac blind-creates with no review step (file 02).
- **One-shot UI-automation planner** (`actionPlanner.ts` + native approval dialog) — a real Windows-only capability with no Mac equivalent (file 04).
- **Markdown link safety** — Windows restricts clickable links to http(s)/mailto as a deliberate prompt-injection defense over OCR'd screen content (file 13).
- **Conversation-record sync resilience** — Windows' `outbox.ts` CAS+dedupe is solid, and the continuous-mic realtime-STT lane now has reconnect+resume+silence-keepalive that's arguably as rigorous as Mac's WAL reconciler for that lane (file 09).
- **Onboarding step transitions** — an animated fade+slide per step vs. Mac's hard, unanimated cut (file 13).
- **Tray per-state icon set** (3 states) vs Mac's single static icon (file 13).
- **Windows-exclusive additions with no Mac equivalent at all** — one-shot Obsidian/plain-Markdown/Notion memory export, and a real paid-app purchase flow in the Apps marketplace (file 12).
- **Design tokens** — Windows' palette is neutral by default (`--accent` is white), with purple surviving only as a scoped, documented, product-approved exception (`lib/macPalette.ts`, governed by a binding "Track 4 ruling") rather than an accidental leak; any Mac component leaning on `OmiColors.purplePrimary` still needs a **conscious** remap, not a literal color port (file 13).

## Caveats & follow-ups (honest limits of this pass)

- **Resolved by this pass, no longer open questions:** whether the Windows backend sends citations to the client (it does — confirmed plumbed end-to-end, just unrendered, file 13); whether trial/paywall gating is a deliberate product decision or a gap (it's neither — it's already fully built and shipped, file 12); whether Rewind search, `localAgent`'s enrichment flag, and BrainGraph's `interactive` prop needed re-checking for silent re-wiring (they were re-checked directly against current source this pass, not assumed — see Quick Wins above for the corrected framing on the latter two).
- **The default chat engine's flip to the kernel-routed `pi_mono` path** intersects a `PARALLEL-PLAN.md` decision gate with explicit required safeguards (fallback telemetry, a continuity-guard test, staged rollout). This pass confirmed the flip happened but did **not** verify those safeguards actually landed first — a real risk worth a cheap check before treating that gate as closed (file 04).
- **Two Mac-side citation questions this pass couldn't resolve:** whether Windows' 12-bundle desktop-tool-policy count (vs. Mac's cited 11) reflects a genuine platform difference or a stale Mac count; and whether Windows' fourth external coding-agent adapter (Codex) means Mac gained Codex support too since its reference snapshot, or Windows built support for a provider Mac doesn't have (file 04).
- **The `BUILD_PLAN.md` citation for the Phase-7/BLE deferral decision is unverifiable** — no file by that name exists anywhere in this repo's git history. The deferral conclusion itself still checks out (independently corroborated by three other audit files), but that specific pointer should not be trusted at face value (file 09).
- **An unresolved backend-contract discrepancy**: whether production actually honors `client_session_id` for `/v1/conversations/from-segments` idempotency — two conflicting claims exist with no way to re-verify from the client side (file 09).
- **Mac's Brain Map may already be a different surface for some accounts.** A server-gated "Canonical Memory Atlas" (cluster/territory-based, under active Mac development through 2026-08-16) replaces the legacy SceneKit force-directed graph this audit compares against once an account's `canonicalLifecycleExposed` flag is set — this audit evaluated only the legacy path and did not assess the canonical atlas at all (file 11).
- **Two Windows-only pages may have no Mac counterpart to be "behind":** the standalone Insights history page and the Agents settings tab. Flagging for confirmation with whichever future pass owns those areas, not scored as a gap either direction (file 12).
- **`glow_overlay_enabled`** (a generated API field) is still never read by the Windows renderer even though the glow feature itself works — either it's gated some other way this pass didn't find, or the field is Mac-only (file 13).
- **UI file 13** left 5 Mac visual files not fully read (CitationCardView, SpeakerBubbleView, AudioLevelWaveformView, Glow*Window mechanics, SpatialOverlayRenderGeometry) — the highest-value items were covered directly regardless.
- This audit does **not** rank, sequence, or estimate — beyond what `14-sequencing-plan.md` (below) already derives from it.

## Sequencing & effort plan

[`14-sequencing-plan.md`](14-sequencing-plan.md) is a from-scratch rewrite of the sequencing work, built directly from files `01`–`13` above and explicitly reconciled against the other planning docs already in this directory (`PARALLEL-PLAN.md`, `track2-execution-plan.md`, `TRACK4-PLAN.md`, `WIRING-AUDIT.md`) rather than re-deriving their territory. It orders the work into **Wave 0** (days of pure settings/UI wiring onto already-built capabilities — the Quick Wins above), **Waves 1–3** (the residual, still-open slice of the chat/agent-runtime, voice/PTT, and Rewind/shell work those other planning docs already scoped in detail — most of each has shipped), **Wave 4** (proactive-assistant dashboards and cross-device sync), **Wave 5** (Tasks/Goals depth, including task-chat and "Execute," which can start immediately since the agent kernel they need is already merged), **Wave 6** (onboarding intelligence — the single largest remaining capability gap), **Wave 7** (app-shell/settings polish), and two explicitly non-schedulable waves: **Wave 8** (Persona, parked on backend work) and **Wave 9** (BLE/wearables + offline WAL, deferred until product un-defers Phase 7). Each item is sized XS–XL and traced back to its finding in files 01–13.
