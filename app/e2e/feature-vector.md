# Omi Mobile App Feature Vector for Flow-Walker
## Updated 2026-03-17 (originally Codex-validated 2026-03-12)

### Purpose
Prioritized feature map to guide flow-walker E2E coverage of core Omi mobile app flows. Uses two scoring dimensions from the Omi Issue Triage Guide.

---

## Scoring Model

**Combined Priority** = `layer_weight × session_frequency`

| Dimension | Values |
|-----------|--------|
| **Core-to-mission** (layer weight) | capture=5, understand=4, memory=4, intelligence=3, retrieval-action=3 |
| **Session frequency** | daily=3, weekly=2, setup-only=1 |

**Walker Score** (0-3):
- 3 = fully automatable (press-only, deterministic)
- 2 = partially automatable (needs scroll OR conditional content)
- 1 = needs human/physical setup first, then walker can verify
- 0 = unreachable (SMS, external OAuth, real payment)

> **Note (2026-03-17):** BLE device flows were originally scored walker=0 (unreachable). Proved automatable on physical Pixel 7a with Omi device — upgraded to walker=1 (needs physical device setup, then agent can drive full flow via ADB + agent-flutter).

---

## Feature Vector (sorted by priority × walker_score)

### CORE DAILY (priority 9-15, walker_score 1-3)

| # | Feature | Layer | Priority | Walker | Coverage Status |
|---|---------|-------|----------|--------|-----------------|
| 1 | Conversation list & browse | capture (5) | 15 | 3 | ✅ flow: conversations.yaml (9 steps) |
| 2 | Conversation detail (transcript/summary/actions tabs) | capture (5) | 15 | 2 | ✅ flow: conversations.yaml |
| 3 | Conversation recording (phone mic) | capture (5) | 15 | 1 | ✅ flow: phone-capture.yaml (9 steps) |
| 4 | Conversation recording (Omi device) | capture (5) | 15 | 1 | ✅ flow: device-capture.yaml (10 steps) |
| 5 | Device discover & connect (BLE) | capture (5) | 15 | 1 | ✅ flow: device-connect.yaml (10 steps) |
| 6 | Device disconnect & reconnect | capture (5) | 15 | 1 | ✅ flow: device-connect.yaml |
| 7 | Memory list & browse | memory (4) | 12 | 2 | ✅ flow: memories.yaml (6 steps) |
| 8 | Memory search | memory (4) | 12 | 2 | ✅ flow: memories.yaml |
| 9 | AI Chat open/close (Ask Omi) | intelligence (3) | 9 | 2 | ✅ flow: ask-omi-chat.yaml (9 steps) |
| 10 | Action items view | intelligence (3) | 9 | 2 | ✅ flow: action-items.yaml (7 steps) |
| 11 | Daily summary/score (home cards) | intelligence (3) | 9 | 2 | ✅ flow: daily-summary.yaml (stub) |
| 12 | Global search | retrieval-action (3) | 9 | 2 | ✅ covered |
| 13 | Task management (create via FAB, toggle) | retrieval-action (3) | 9 | 2 | ⚠️ partial |

### CORE WEEKLY (priority 6-12, walker_score 1-2)

| # | Feature | Layer | Priority | Walker | Coverage Status |
|---|---------|-------|----------|--------|-----------------|
| 14 | **Memory review/approval** | memory (4) | 12 | 1 | ⚠️ NO UI — backend API exists but Flutter app has no review buttons (user_review field unused in UI) |
| 15 | Memory categories & filter | memory (4) | 8 | 2 | ⚠️ partial |
| 16 | Add/edit memory manually | memory (4) | 8 | 2 | ✅ flow: add-edit-memory.yaml (7 steps) |
| 17 | Memory graph visualization | memory (4) | 8 | 2 | ✅ flow: memory-graph.yaml (stub) |
| 18 | Custom vocabulary | understand (4) | 8 | 2 | ✅ flow: custom-vocabulary.yaml (7 steps) |
| 19 | Speaker identification (People) | understand (4) | 8 | 1 | ✅ flow: speaker-identification.yaml (9 steps) |
| 20 | Goals tracking | intelligence (3) | 6 | 2 | ✅ flow: goals-tracking.yaml (7 steps) |
| 21 | Conversation sharing/export | retrieval-action (3) | 6 | 2 | ✅ flow: conversation-sharing.yaml (8 steps) |
| 22 | Conversation folders | retrieval-action (3) | 6 | 2 | ✅ flow: conversation-folders.yaml (10 steps) |
| 23 | App marketplace browse | retrieval-action (3) | 6 | 2 | ✅ flow: apps-marketplace.yaml (7 steps) |
| 24 | App detail & install | retrieval-action (3) | 6 | 2 | ✅ flow: apps-marketplace.yaml |
| 25 | Offline sync UI | capture (5) | 10 | 2 | ✅ covered |

### SETUP & AUTH (priority 3-5)

| # | Feature | Layer | Priority | Walker | Coverage Status |
|---|---------|-------|----------|--------|-----------------|
| 26 | Login (Google Sign-In) | — | 5 | 1 | ✅ flow: login.yaml (5 steps) |
| 27 | Logout | — | 5 | 2 | ✅ flow: logout.yaml (5 steps) |
| 28 | Onboarding (first launch) | — | 5 | 1 | ✅ flow: onboarding.yaml (9 steps) |
| 29 | Transcription settings | understand (4) | 4 | 2 | ✅ covered |
| 30 | Language selection | understand (4) | 4 | 2 | ✅ covered |
| 31 | Speech profile | understand (4) | 4 | 1 | ✅ covered |
| 32 | Task integrations | retrieval-action (3) | 3 | 1 | ✅ flow: task-integrations.yaml (stub) |
| 33 | Calendar integration | retrieval-action (3) | 3 | 0 | ⚠️ OAuth blocked |

---

## Remaining Gaps

| Rank | Feature | Priority | Blocker | Notes |
|------|---------|----------|---------|-------|
| 1 | Memory review/approval | 12 | **No Flutter UI exists** | Backend has POST /v3/memories/{id}/review endpoint and user_review field, but no approve/reject buttons in Flutter app. Cannot create flow for non-existent UI. |
| 2 | Memory categories & filter | 8 | Partial coverage | Covered in memories.yaml but filter toggles not fully exercised |
| 3 | Task management (create via FAB) | 9 | Partial coverage | Action items list covered but task creation form needs text input |

---

## Published Flow-Walker Reports

| Flow | Steps | Result | Report URL |
|------|-------|--------|------------|
| login | 5/5 | PASS | flow-walker.beastoin.workers.dev/runs/ |
| onboarding | 9/9 | PASS | flow-walker.beastoin.workers.dev/runs/ |
| logout | 5/5 | PASS | flow-walker.beastoin.workers.dev/runs/ |
| ask-omi-chat | 9/9 | PASS | flow-walker.beastoin.workers.dev/runs/O5h8bR6izW.html |
| conversations | 9/9 | PASS | flow-walker.beastoin.workers.dev/runs/cUdrOXGmqV.html |
| apps-marketplace | 7/7 | PASS | flow-walker.beastoin.workers.dev/runs/tdN1QX_6Al.html |
| memories | 6/6 | PASS | flow-walker.beastoin.workers.dev/runs/S3mWAUnXiq.html |
| action-items | 7/7 | PASS | flow-walker.beastoin.workers.dev/runs/CvTQtuBo6K.html |
| phone-capture | 9/9 | PASS | flow-walker.beastoin.workers.dev/runs/HBzorfQBM2.html |
| device-connect | 10/10 | PASS | flow-walker.beastoin.workers.dev/runs/yOluecTPyM.html |
| device-capture | 10/10 | PASS | flow-walker.beastoin.workers.dev/runs/EWHjix-kFv.html |
| conversation-folders | 10/10 | PASS | flow-walker.beastoin.workers.dev/runs/V-TQ-4nmze.html |
| conversation-sharing | 8/8 | PASS | flow-walker.beastoin.workers.dev/runs/N3YxO9Zpnu.html |
| add-edit-memory | 7/7 | PASS | flow-walker.beastoin.workers.dev/runs/0crZDcAVrh.html |
| custom-vocabulary | 7/7 | PASS | flow-walker.beastoin.workers.dev/runs/W3wIFeChiw.html |
| speaker-identification | 9/9 | PASS | flow-walker.beastoin.workers.dev/runs/uguxZ6ptjN.html |

---

## Coverage Summary

| Category | Total Features | Covered | Gaps |
|----------|---------------|---------|------|
| Core Daily (capture, intelligence) | 13 | 12 | 1 (task mgmt partial) |
| Core Weekly (memory, understand, retrieval) | 12 | 11 | 1 (memory review — no UI) |
| Setup & Auth | 8 | 7 | 1 (calendar OAuth) |
| **Total** | **33** | **30** | **3** |

### What Changed (2026-03-18 update)
- **5 new flow-walker reports published** on physical Pixel 7a device:
  - add-edit-memory (7/7 PASS) — create, edit, delete memory via FAB
  - custom-vocabulary (7/7 PASS) — add/delete transcription vocabulary words
  - speaker-identification (9/9 PASS) — add person, name speaker in transcript
  - conversation-folders (10/10 PASS) — folder tabs, create/filter
  - conversation-sharing (8/8 PASS) — share link, copy transcript, visibility
- **goals-tracking flow blocked**: DailyScoreWidget not rendering on Pixel 7a despite preference enabled — "Add Goal" entry point unavailable when no goals exist
- **Total published reports: 16** (was 11)

### What Changed (2026-03-17 update #2)
- **6 new flows added closing all actionable gaps**:
  - conversation-folders.yaml (10 steps) — folder tabs, create/filter/delete
  - goals-tracking.yaml (7 steps) — create/track/edit/delete goals
  - add-edit-memory.yaml (7 steps) — create/edit/delete memories via FAB
  - custom-vocabulary.yaml (7 steps) — add/delete transcription vocabulary
  - conversation-sharing.yaml (8 steps) — share link, copy transcript, visibility
  - speaker-identification.yaml (9 steps) — people management, name speakers
- **Memory review/approval reclassified**: Not a gap but a missing Flutter UI feature (backend exists, app doesn't expose it)
- **Coverage: 30/33 features** (91%) — remaining 3 are partial/blocked, not actionable gaps

### What Changed (2026-03-17 update #1)
- **BLE device flows promoted to CORE DAILY** — device-connect and device-capture proved automatable on physical Pixel 7a with real Omi device (were scored walker=0, now walker=1)
- **3 new flows added**: phone-capture, device-capture, device-connect (15 + 10 + 10 = 29 new steps)
- **Auth flows added to vector**: login, logout, onboarding (previously unlisted)
- **Flow YAML references added** to coverage status for traceability
