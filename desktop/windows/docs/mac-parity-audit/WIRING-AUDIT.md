# Windows Core-Feature Wiring Audit — vs Mac (proven reference)

> 2026-07-13. Ten parallel auditors compared the Windows app's **already-shipped** subsystems
> against the working Mac app and the backend contracts. This is about wiring correctness of
> what exists — feature *gaps* live in the parity audit (00-INDEX.md) and the split plan
> (PARALLEL-PLAN.md). Every finding below is source-cited in the per-subsystem reports;
> "needs runtime test" items are flagged. Severity: **Critical** = user-visible breakage or
> data loss; **Major** = degraded behavior vs Mac; Minor = hygiene.

## Critical (fix first)

| # | Subsystem | Finding |
|---|---|---|
| C1 | Transcription | **Client-side VAD gate can starve `/v4/listen`**: Windows only forwards voiced audio (`AudioSessionHost.ts:80-99` → `createVadGate`); backend closes the socket after 90s of inactivity (`transcribe.py:758-796`, close 1001). Any quiet stretch ≥ ~90s silently kills live transcription. Mac deliberately streams ALL audio ("backend handles its own VAD"). Fix: silence keepalive (`b'\x00'*320` per pipeline doc §6) or drop the gate for conversation mode. Corroborated independently by two auditors. |
| C2 | Conversations | **Always-on "live conversation" mic path has zero local persistence/recovery** (`liveMicSession.ts`, `liveStore.ts`): segments are in-memory only; 3 reconnect attempts (~4.8s) then error-stop. Mac persists every segment to SQLite and falls back to `from-segments` upload when cloud reconciliation is exhausted (issue #9083). A network blip = the recording is simply lost. |
| C3 | Conversations | **Action-item toggle inside ConversationDetail always 422s** (`ConversationDetail.tsx:231-266`): embedded items never have an `id` (backend embedded model has none), so it always hits the fallback that sends `{action_item_idx, completed}` — backend requires parallel arrays `items_idx`/`values`. Every checkbox click fails, optimistic UI reverts. (Mac renders these read-only; Windows added the interaction with a wrong contract.) |
| C4 | Chat | **Windows discards the `done:` final payload** (`useChat.ts:467-472` returns null for it): loses the citation-stripped final text (so literal `[1]`/`[2]` markers persist in UI + local history), `memories` citations, `chart_data`, `ask_for_nps`, and the server message `id` — which is why rating/share/report can never be wired (zero call sites for those generated endpoints). |
| C5 | Chat | **No abort path for chat generation** (`send()` has no AbortController; `reset()` doesn't touch the in-flight reader): a dismissed generation's `finally` still persists into the same infinite thread → zombie replies resurface; busy-flag unlatches so a new send can interleave with the zombie. Mac: interrupt over kernel stdin + generation counters + 180s watchdog. |
| C6 | Meeting detect | **Double mic-session race, acknowledged in-code but unfixed** (`meetingSession.ts:15-22`): manual recording + `mode:auto` meeting detection opens a SECOND concurrent `/v4/listen` mic session for the same audio ("Phase 3" comment). Mac's detector only gates the one existing session, so this class can't happen there. |
| C7 | Shell | **OCR helper subprocess leaks on every quit**: `will-quit` never calls `helperProcess.dispose()` (zero production call sites) → orphaned `omi-*-ocr-helper.exe` accumulates across launches. (Runtime check: Electron job-object behavior might mitigate — verify.) |
| C8 | Memories | **Bulk memory import serially POSTs one memory at a time** (`AdvancedTab.tsx:99-130`) — the exact fan-out (up to hundreds of requests) the backend's `/v3/memories/batch` (cap 100) was built to stop; heuristic-fallback path is uncapped and can collaterally 429 chat/sync/goals. Batch wrapper exists in the generated client, uncalled. |
| C9 | Memories | **No edit and no visibility toggle on the Memories page** — Windows' only remediation is delete+recreate, which destroys id/lineage the backend's temporal model preserves. Typed wrappers already exist, uncalled. ⚠ Twist: Mac sends `{value}` as a JSON **body**, but the backend binds `value` as a required **query param** — Mac's own edit/visibility may 422 in production (no test coverage on either side). Verify against a dev backend; if Windows builds this, use the query-param form, don't copy Mac. |
| C10 | Tasks/Goals | **Mac is NOT ground truth for goal completion** — Mac's `completeGoal()` PATCHes fields (`is_active`, `completed_at`) the backend's `GoalUpdate` doesn't accept (→ 400) and `getCompletedGoals()` calls a route that doesn't exist (→ 404). Windows' drive-progress-to-target simulation is the currently-correct pattern. Do not "fix" Windows toward Mac here; the backend contract is the reference. |

## Major

- **Transcription**: no reconnect on `/v4/listen` drop (Mac: 10-attempt backoff + watchdog, resumes the SAME conversation via `client_conversation_id` — Windows treats any close as terminal and never sends `client_conversation_id`); **BYOK headers never attached** to the WS upgrade (BYOK users silently don't get their keys applied to transcription).
- **Conversations**: no app-wide background retry sweep for the sync outbox — retries only run when the Conversations page mounts (Mac: unconditional 60s timer from launch). A PTT-only user's failed sync is wedged for the whole session.
- **Chat**: the desktop persistence contract (`/v2/desktop/messages` with `client_message_id`, `message_source`, `app_id`/`session_id`) is entirely unused on Windows — chat persists only to local SQLite with unreconciled client UUIDs; one-way continuity leak — Windows-authored turns persist into the shared backend thread as a side effect of `/v2/messages` (other platforms see them) but Windows never reads `GET /v2/messages`, so threads continued on mobile/web are invisible on Windows. Also: Gemini barge-in only clears the local player (`geminiSession.ts:94-98`) — Mac needed full session-replace + token re-mint; Windows may reproduce the bug Mac worked around (live test needed). OpenAI transport is WebRTC/server-VAD vs Mac's WS/client-heuristic (legit, but barge-in feel may differ).
- **Auth**: Firebase session (ID + refresh token) stored in unencrypted IndexedDB while the *less* sensitive Google-integration token gets DPAPI `safeStorage`; **no 401 handling at all** on the primary API client (dead/revoked session = app fails forever with no re-auth prompt; Mac kicks to `.needsReauth`); **sign-out does no cache teardown** (second account on the same machine can see prior account's cached data until re-sync — runtime-verify blast radius).
- **Memories→chat grounding**: Windows chat sees only a lossy KG summary that can be up to 12h stale (`STALE_MS`, `kgSynthesis.ts:10`) with the live memory-query tool loop disabled (`ENRICH_ENABLED=false`); Mac injects the freshest 30 memories into the system prompt every turn plus an always-on SQL tool. Memories created since the last KG rebuild are invisible to Windows chat.
- **Audio**: no device-change handling (Mac rebuilds the capture stack with retries on default-device/format change); no silent-mic recovery (Windows detects dead mic at PTT release with Mac's exact thresholds but only shows a hint forever — no BT-fallback/rebuild escalation).
- **Meeting detect**: "ask" toast auto-dismisses after 30s with no retry (missed prompt = meeting permanently forfeited); insight/what's-new toasts clobber the ask-toast (shared last-writer-wins window); default end-grace is 2 min of continued recording vs Mac's 8s (confirm intentional); tab-switch inside an already-foregrounded browser can evade detection (no title-change hook, no poll).
- **Rewind**: no 30s keyframe anchor (static screens produce zero frames → timeline gaps for hours); no battery-aware throttling (Mac triples interval); sleep vs lock conflated (no suspend/resume handling → frozen stream after sleep-without-lock).
- **Shell**: no cross-launch crash/clean-exit detection (Mac: `lastSessionCleanExit` + Sentry report + Rewind DB integrity-check trigger).
- **Bar/PTT**: default question routing differs architecturally (Mac: local agent-SDK bridge with local tools; Windows: backend `/v2/messages` with backend RAG tools — same finding as chat C-level; needs a product call, both are "real" systems); **screen OCR text sent to the backend on every message with no consent gate** (Mac never sends screen content for chat; its PTT OCR is local-only STT correction) — privacy divergence, check onboarding consent; summon-hotkey PTT release is `GetAsyncKeyState` polling with a 5-minute worst-case stuck bound vs Mac's seconds (mitigated + logged, rare).
- **Tasks**: Tasks page caps at 300 items with no pagination (`has_more` unused; Mac pages at 100 + reconciliation sweep) and never auto-refreshes (module cache + manual button only — Home widgets refresh on focus, so Home can be fresher than the Tasks page). Onboarding screen-permission step is a placeholder that always "grants."

## Notable Minor / informational

- Dead `uid` query param on the listen socket with a factually wrong comment; PTT `keywords` param not sent (feature gap, Stream 2).
- Meeting mic+system = two separate transcription-only streams stitched client-side (documented workaround for a real backend two-socket race — informational).
- `mergeLanes.ts` can emit `start==end` segments; backend rejects the whole batch on any one (`end > start` strict) — shared risk, unguarded on both platforms.
- KG write queue: `terminate()` on quit drops a pending graph write without flushing (stale graph until next 12h-stale rebuild); wholesale-replace transactions are atomic, so no corruption.
- `outbox.ts` comment claims prod ignores `client_session_id` (2026-07-10) but the backend shipped real uuid5 idempotency on 2026-06-29 — probably deploy lag; re-verify before trusting either claim.
- Memory pagination caps inconsistent across three duplicate fetch-all loops (5000 vs 100k); `purgeAppMemoriesOnce` misses items past 5000.
- `sandbox: false` on the main BrowserWindow (defaults otherwise secure) — hardening note.
- Stale comment: backend honors client-supplied memory category (comment claims it may ignore it).
- Mac sends `sort_by`/`deleted` params the backend ignores (stale Mac code, not Windows).

## Where Windows is verified correct (or ahead)

Endpoint/param/payload parity held everywhere else it was checked: listen/PTT socket URLs + params byte-for-byte; PCM 16k mono int16 both platforms (pcm16 vs linear16 codec labels are both raw-PCM passthrough server-side — ruled out); PTT gating constants an exact 1:1 port; from-segments payload field-for-field; delete/star/title/progress endpoints; realtime token-mint contract verified byte-for-byte incl. error taxonomy; Gemini audio formats; usage-report delta handling; OAuth PKCE + state validation on both flows (Google-integration flow is a clean, complete port incl. DPAPI storage + 401-retry); single-instance/tray/auto-update; retention wiring; Rewind exclusions (ahead of Mac: private-browsing window-title markers); idle-pause (Windows-only addition); outbox CAS + tolerance-matched dedupe; anti-stuck PTT machine + watchdog; renderer crash reload-with-backoff; stale-callback protection in voice (independent but equivalent design).

## Runtime-test queue (top items)

1. 90s-silence disconnect on a live conversation session (C1).
2. Live-conversation network-blip data loss (C2).
3. Action-item toggle 422 repro in ConversationDetail (C3).
4. Cited answer → `[1]` bracket leakage; reset-mid-stream zombie persistence (C4/C5).
5. Manual recording + auto meeting detect → double session (C6).
6. Orphaned OCR helper after quit; Electron job-object behavior (C7).
7. Account-switch data exposure after sign-out (auth Major).
8. Gemini barge-in stress test (stale audio after talk-over).
9. Sleep-without-lock Rewind stream behavior.
10. Re-verify `client_session_id` idempotency against currently-deployed backend.

## Suggested fix routing (matches PARALLEL-PLAN.md streams)

- Stream 1 (agent/chat): C4, C5, chat continuity leak, screen-OCR consent gate.
- Stream 2 (voice/bar): Gemini barge-in, PTT keywords, hotkey-poll hardening notes.
- Stream 3 (proactive/memory): C8, C9, memory pagination dupes, KG quit-flush.
- Stream 4 (rewind/shell/conv pages): C3, C7, keyframe/battery/suspend, crash detection, Tasks pagination/refresh, meeting-toast retry.
- Unassigned high-priority (capture core — fix before or alongside streams): C1, C2, C6, reconnect + BYOK on listen socket, auth trio (token storage, 401 handling, sign-out teardown), outbox background sweep.
