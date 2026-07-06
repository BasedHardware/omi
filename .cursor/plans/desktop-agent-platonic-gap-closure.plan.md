# Desktop Agent Platonic Architecture — Gap Closure Plan

**Status:** COMPLETE — G1–G12 closed + QA bundle; green gauntlet `20260706T022442Z` at train HEAD `d3a7288e51` (`--suite all`, `omi-continuity-qa`).
**Branch:** continue on `desktop-agent-platonic` (stacked fix branches `desktop-agent-gc<N>-<slug>`).
**Baseline:** `f598c4a27` (branch HEAD at time of review).

### Progress tracker

| Gap | Severity | Status | Branch | Notes |
|-----|----------|--------|--------|-------|
| G1 — Warm bindings blind to voice turns | **Blocker** | ✅ Done | `desktop-agent-gc1-binding-delta` | `2032d3c38` |
| G2 — Owner-switch gauntlet failure | High | ✅ Done | `desktop-agent-r1-owner-swap` (`19b65da45`, merged onto `desktop-agent-platonic`) | step 06 green on `omi-gauntlet`: full pass `20260705T075032Z` (`7638f2f4f` train HEAD; manifest `git` `c3abf9785`) — `swap_test_owner`, disjoint `conversation_id`, owner-A markers absent from owner-B trace |
| G3 — No green gauntlet at HEAD | **Blocker** (gate) | ✅ Done | — | GREEN at `7638f2f4f`: `.harness/agent-continuity-gauntlet/20260705T075032Z` (`passed: true`, `--suite all`, all 6 steps) |
| G4 — Coordinator session-id fallback chains | Medium | ✅ Done | — | single `sessionId` field |
| G5 — Dead identity vocabulary in Swift | Low | ✅ Done | — | `floatingSessionKey` deleted; case-insensitive INV-5 |
| G6 — Migration shims without deletion dates | Medium | ✅ Done | — | ship+2 TODO markers + coordinator doc |
| G7 — Stale `delegate_agent` references | Low | ✅ Done | — | kernel-support error string |
| G8 — Phase 7 leftovers | Low | ✅ Done | — | ChatPrompts dead params; FCBW ≤4016 |
| G9 — Plan doc corruption | Trivial | ✅ Done | — | §7 stale rows removed |
| G10 — Transcript dedupe in assembler | **High** | ✅ Done | — | packet policy-only; transcript sole history |
| G11 — Source attribution on injected context | Medium | ✅ Done | — | `[live:typed|voice|memory|recording]` labels |
| G12 — Stale memory/seed refresh | Medium | ✅ Done | — | per-turn `<user_facts>` refresh |

**Post-QA bugs (not in original gap list):**
- PTT seed-stale silence → fixed `87f4904a` (await session + prefetch on arm)
- Typing indicator after spawn → fixed `65013a9ea`

**All invariants INV-1 … INV-9 from the parent plan remain binding.** This plan adds no capabilities (INV-7 applies). Every fix PR must leave every touched file smaller than it found it (Phase 7 ceiling), except where a test file grows to cover a fix.

---

## 0. Why this plan exists

The parent plan is marked "COMPLETE WITH DOCUMENTED GAPS", but the review of 2026-07-04 found the gaps are not documentation-tier:

1. **The standing INV-6 gauntlet has never passed.** All four evidence bundles under `desktop/macos/.harness/agent-continuity-gauntlet/` are `passed: false`. The two most recent failures are real defects, not harness flakes (root cause confirmed by code inspection, G1/G2 below).
2. The failing assertion — *"typed follow-up trace missing kernel conversation_history injection"* — is gauntlet step 3, the exact typed↔PTT continuity scenario the parent plan's Phase 4 exists to fix. The flagship promise of the refactor is currently broken in the warm-binding (most common) case.
3. Two commits (`a14f90d0c`, `f598c4a27`) landed after the last evidence run with no gauntlet evidence at all.

Nothing merges to `main` until G1–G3 are closed with a green evidence bundle at branch HEAD. G4–G9 are cleanup-tier and may land in the same train or immediately after, but before the branch is declared done.

---

## G1 — Warm bindings are blind to voice turns (BLOCKER)

**Defect.** `assembleTurnContext` (`agent/src/runtime/turn-context.ts:134`) injects the `conversation_turns` transcript tail **only when `!bindingCarriesNativeHistory`**. PTT turns enter the kernel via `recordSurfaceTurn` (`conversation-turns.ts`) and are written to `conversation_turns`, but they never enter the typed adapter's *native* session history. Therefore, on a warm native binding (typed turn → PTT turn → typed follow-up in one live session), the typed model never sees the voice turn.

**Why the parent plan's wording caused this.** Phase 3 said: *"binding carries native history → inject nothing redundant."* The implementation reads this as "inject nothing." Voice turns are **not redundant** with native history — they were never delivered to the binding. The correct reading: inject exactly the turns the binding has not seen.

**Design (prescriptive).**

1. Track delivery per binding. Add a high-water mark to the binding: `last_delivered_turn_created_at_ms` (column on `adapter_bindings` in `sqlite-store.ts`, or a small `binding_turn_delivery` table if the binding row is shared across concerns — prefer the column; do not create a new store, INV-1).
2. On every run executed through a binding, after `assembleTurnContext`, advance the high-water mark to the newest `conversation_turns.created_at_ms` for that conversation at assembly time (including the user turn appended by `kernel-core.ts` for this run).
3. `assembleTurnContext` gains one rule replacing the boolean gate:
   - binding **not** native → inject bounded tail (unchanged, `CONVERSATION_TRANSCRIPT_TAIL_LIMIT`);
   - binding native → inject only turns with `created_at_ms > last_delivered_turn_created_at_ms`, bounded by the same limit, labeled as a delta (e.g. `# Recent turns from other surfaces` — but do NOT special-case voice: any turn the binding hasn't seen qualifies, which also future-proofs multi-surface writes).
4. `recordSurfaceTurn` needs no change — it writes turns; the delta logic picks them up naturally.
5. Keep exactly one assembler. FORBIDDEN: a second injection path in Swift, in the hub, or in `recordSurfaceTurn` callbacks; per-surface caps that differ from the one policy in `turn-context.ts`.

**Tests (same PR).**
- Kernel unit test: warm native binding + interleaved `recordSurfaceTurn` (origin `realtime_voice`) → next assembled prompt contains the voice turn exactly once; a second follow-up with no new turns injects nothing.
- Kernel unit test: fresh binding after voice turns → tail injection includes them once (no double injection with the delta path).
- Existing "no duplicate history when binding is native-resumable" test updated to assert the delta is empty when the binding has seen everything — not that injection never happens.

**Acceptance.** Gauntlet step 3 assertion (`typed follow-up trace … conversation_history injection`) goes green in a live named-bundle run; QueryTracer excerpt in the evidence bundle shows the PTT marker delivered exactly once.

---

## G2 — Owner-switch isolation check fails (HIGH)

**Defect.** Latest gauntlet run fails `owner-switch surface isolation (kernel): conversation identity drifted` (baseline `runtime_chat_id: 'default'` vs current `''`). Additionally, step 06 is a kernel vitest stand-in; the manifest itself records *"full auth swap E2E remains manual"*, which falls short of the parent plan's Phase 0 item 4 / Phase 2 acceptance (automated owner-switch check in the gauntlet).

**Actions.**
1. Root-cause the drift first (Investigate before fixing — it may be a gauntlet-lib identity-snapshot bug rather than a kernel one; the empty-string baseline fields suggest the snapshot reads Swift-side identity that no longer exists post-Phase 2, i.e. the *check* may be probing deleted vocabulary). If the check probes legacy fields, rewrite it to assert kernel truth: same `(ownerId, surfaceRef)` → same `conversationId` across the run; different `ownerId` → disjoint `conversationId` and no cross-owner turns in `conversation_turns`.
2. Then automate the auth swap far enough to satisfy the parent plan: extend the automation bridge with a `swap_test_owner` action (test-bundle-only, behind the existing non-prod automation gate) that calls the kernel's `clearOwnerState` + re-registers with a second synthetic owner id, and assert user A's markers are absent from user B's assembled context. Full Firebase auth-UI swap stays manual and is recorded as such in the gauntlet manifest — but the *kernel-level* isolation must be exercised in-process, per run, not in a separate vitest.

**Acceptance.** Step 06 passes in the live gauntlet run; evidence shows owner B's first assembled prompt contains no owner-A marker.

---

## G3 — Green gauntlet at HEAD (BLOCKER, exit gate)

**Actions.**
1. After G1/G2 land, run the full live gauntlet against a named `omi-*` bundle built from branch HEAD: `cd desktop/macos && OMI_APP_NAME=omi-gauntlet OMI_SKIP_TUNNEL=1 ./run.sh`, seed auth, then `./scripts/agent-continuity-gauntlet.sh`.
2. The evidence bundle (`.harness/agent-continuity-gauntlet/<ts>/`) must show `passed: true` with `git` equal to the branch HEAD SHA. Commit the manifest path + SHA into the parent plan's §7 table.
3. Investigate the two older PTT failures (`hub session did not become active`) only if they reproduce at HEAD — they predate the last fixes and may be environment (sign-in/provider keys). If they reproduce, they block; if not, note the runs as superseded.
4. From this point forward: a green gauntlet bundle is required **at train HEAD before the train is declared done or merged**, plus at any single commit that touches `turn-context.ts`, `conversation-turns.ts`, `kernel-*.ts`, or surface-session code *if more commits will follow it on the train*. Docs-only commits must say so in the commit body instead.

**Definition of Done for the whole plan:** one evidence bundle, `passed: true`, `git == HEAD`, all six steps green.

---

## G4 — Coordinator session-id fallback chains (MEDIUM)

**Defect.** `SessionIdentityForbiddenIdentifiersTests.swift` allowlists 7 hand-written files as "protocol layer". Most are genuine wire-decoding, but `DesktopCoordinatorService.swift:645–867` contains repeated `stringValue(session["omiSessionId"]) ?? stringValue(session["sessionId"])` fallback chains — the D2 fallback-chain pattern surviving in projection form. The allowlist is doing work the architecture should.

**Actions.**
1. Make the runtime emit **one** canonical field. Coordinator/status payloads from TS include `sessionId` only (kernel session id); delete the `omiSessionId` duplicate from the TS emitters (`grep -rn "omiSessionId" agent/src` and collapse). This is a bundled subprocess — no old clients (same argument as parent Phase 6 item 1).
2. Swift decoders read the single field; delete every `??` identity fallback in `DesktopCoordinatorService.swift` and `AgentControlService.swift`.
3. Shrink the allowlist in `SessionIdentityForbiddenIdentifiersTests.swift` to the files that still genuinely decode the wire field (target: `AgentBridge.swift`, `AgentRuntimeProcess.swift`, `AgentClient.swift`; each remaining entry gets a one-line justification comment).
4. FORBIDDEN: renaming the field to dodge the grep (e.g. `kernelSessionId` everywhere while keeping dual emission). One field, one name, `sessionId`, display-only in Swift (INV-8).

**Acceptance.** Allowlist ≤ 3 files; `grep -rn '?? stringValue(session' Desktop/Sources` returns zero identity fallbacks; harness + gauntlet green.

---

## G5 — Dead identity vocabulary + grep evasion (LOW)

**Actions.**
1. DELETE `floatingSessionKey` (`FloatingControlBarWindow.swift:2013` + its three write-only assignments). It is never read and survives the INV-5 test only because `floatingSessionKey` does not contain the lowercase substring `sessionKey`.
2. Harden the test: match forbidden identifiers case-insensitively (`SessionKey`, `OmiSessionId`, …) and add `SessionKey` to the list. Re-run; fix any new hits it exposes rather than allowlisting them.

---

## G6 — Migration shims need written deletion dates (MEDIUM)

**Defect.** INV-2 permits temporary shims only with "a scheduled deletion date written into this plan." The parent plan's §7 lists `import_legacy_*` and sqlite legacy columns as "scheduled burn" with no date.

**Actions.**
1. Enumerate the shims: `grep -rn "import_legacy" agent/src` + legacy columns in `sqlite-store.ts` migrations + the Phase 2 UserDefaults importer if still present.
2. For each, write into this plan (table below) the removal trigger: **two desktop releases after the release that ships this branch** (record the concrete version numbers once the shipping release is cut). Add a `TODO(<issue>)` referencing this plan at each shim site (repo rule: markers must reference tracking).
3. Add a changelog-adjacent reminder: an entry in `desktop/macos/docs/agent-coordinator.md` maintenance section listing the shim burn-down.

| Shim | Site | Delete in |
|------|------|-----------|
| `legacy_default` grant source enum + sqlite CHECK | `types.ts`, `sqlite-store.ts` grants table | ship+2 releases after platonic ships |
| `import_legacy_main_chat_sessions` | `surface-session.ts`, `index.ts`, `AgentRuntimeProcess.swift` | ship+2 releases after platonic ships |
| sqlite `legacy_client_scope` / `legacy_session_key` | `sqlite-store.ts` sessions table | ship+2 releases after platonic ships |
| UserDefaults session importer | removed in Phase 2 | n/a |

---

## G7 — Stale `delegate_agent` references (LOW)

**Actions.**
1. `kernel-support.ts:471` — `requiredChildSessionId` throws `"delegate_agent continue mode requires childSessionId"`. The tool no longer exists. Rename the message to the surviving mechanism (`send_agent_message` / delegation continue) and audit siblings: `grep -rn "delegate_agent\|manage_agent_pills\|get_task_agent_status" agent/src Desktop/Sources` — remaining hits must be either deleted or clearly historical comments (the two `control-tool-manifest.ts` description strings saying "Replaces get_task_agent_status and manage_agent_pills" are acceptable — they document lineage to the model is FORBIDDEN territory though per INV-4; reword them to describe what the tool does, not what it replaced).

---

## G8 — Phase 7 leftovers (LOW)

**Actions.**
1. `ChatPrompts.swift`: DELETE the dead `conversationHistory` parameter and the `{conversation_history}` / `{prev_messages_str}` template substitutions (lines ~1210–1248) — no live caller passes history (verified 2026-07-04). While in the file, re-run the liveness audit the parent Phase 7 required: any prompt variant with zero call sites is deleted in the same commit.
2. `FloatingControlBarWindow.swift`: currently 4018 lines vs 4016 on `main` — the Phase 7 ceiling says strictly smaller. G5's deletion already fixes the arithmetic; confirm the final line count is below 4016 in the PR description.

---

## G9 — Fix the parent plan document (TRIVIAL)

**Actions.**
1. In `.cursor/plans/desktop-agent-platonic-architecture.plan.md`, delete the four stale rows embedded in the §7 debt table (the `4 — PTT … ⏳ Pending`, `5 — Pills …`, `6 — Burn …`, `7 — Decomposition …` rows at lines ~37–40) — they are leftovers from an earlier progress table and contradict the completed tracker above.
2. Update §7: mark "Live gauntlet E2E + evidence bundle" with the G3 evidence path once green; add a pointer to this gap-closure plan.

---

## Execution mechanics

- **Order:** G1 → G2 → G3 (gate) in one train; G4–G9 may be parallel small PRs after G3 is green (they must not invalidate the G3 evidence — if any of them touches runtime context/identity code, re-run the gauntlet at the new HEAD).
- **Per-PR verification:** `./scripts/agent-logic-harness.sh` → clean release build (`rm -rf .build && xcrun swift build -c release --triple arm64-apple-macosx`) → live gauntlet for G1/G2/G3 and for any PR touching `turn-context.ts`, `conversation-turns.ts`, `kernel-*.ts`, or surface-session code.
- **Changelog:** G1 is user-visible reliability ("Fixed typed chat not seeing recent voice turns") → one `changelog/unreleased/*.json` fragment. G2 if the kernel fix (not just the check) changes behavior. G4–G9 internal → no fragment.
- **Review checklist:** the parent plan's §5 checklist applies verbatim to every PR here.
- **Merge:** nothing lands on `main` without explicit user go-ahead (repo rule), and not before G3's Definition of Done.

## Out of scope

Same as the parent plan §6. Additionally out of scope here: any redesign of the delta-injection format beyond what G1 requires; backfilling voice turns recorded before G1 ships (the delta starts from the binding high-water mark at migration; do not build a reconciliation pass).
