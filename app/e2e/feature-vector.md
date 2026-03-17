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
| 14 | **Memory review/approval** | memory (4) | 12 | 1 | ❌ GAP |
| 15 | Memory categories & filter | memory (4) | 8 | 2 | ⚠️ partial |
| 16 | **Add/edit memory manually** | memory (4) | 8 | 2 | ❌ GAP |
| 17 | Memory graph visualization | memory (4) | 8 | 2 | ✅ flow: memory-graph.yaml (stub) |
| 18 | **Custom vocabulary** | understand (4) | 8 | 2 | ❌ GAP |
| 19 | **Speaker identification (People)** | understand (4) | 8 | 1 | ❌ GAP |
| 20 | **Goals tracking** | intelligence (3) | 6 | 2 | ❌ GAP |
| 21 | **Conversation sharing/export** | retrieval-action (3) | 6 | 2 | ❌ GAP |
| 22 | **Conversation folders** | retrieval-action (3) | 6 | 2 | ❌ GAP |
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

## Coverage Gaps (core features, reachable, no flow coverage)

| Rank | Feature | Priority | Walker Score | Navigation Path | Blocker |
|------|---------|----------|--------------|-----------------|---------|
| 1 | Memory review/approval | 12 | 1 | Conversation processing → auto-created memories → review dialog | Needs recent conversation with extractable facts |
| 2 | Custom vocabulary | 8 | 2 | Settings → Profile → Custom Vocabulary | Needs scroll in Profile page |
| 3 | Add/edit memory manually | 8 | 2 | Memories tab → FAB → dialog | Needs text input |
| 4 | Speaker identification (People) | 8 | 1 | Settings → Profile → Identifying Others | Needs scroll + conversation with multiple speakers |
| 5 | Goals tracking | 6 | 2 | Home → Goals widget → Add Goal | Needs text input |
| 6 | Conversation sharing/export | 6 | 2 | Conv detail → share button → share sheet | Share sheet is system UI |
| 7 | Conversation folders | 6 | 2 | Home → folder tabs above conversation list | Needs existing conversations |

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

---

## Coverage Summary

| Category | Total Features | Covered | Gaps |
|----------|---------------|---------|------|
| Core Daily (capture, intelligence) | 13 | 12 | 1 (task mgmt partial) |
| Core Weekly (memory, understand, retrieval) | 12 | 5 | 7 |
| Setup & Auth | 8 | 7 | 1 (calendar OAuth) |
| **Total** | **33** | **24** | **9** |

### What Changed (2026-03-17 update)
- **BLE device flows promoted to CORE DAILY** — device-connect and device-capture proved automatable on physical Pixel 7a with real Omi device (were scored walker=0, now walker=1)
- **3 new flows added**: phone-capture, device-capture, device-connect (15 + 10 + 10 = 29 new steps)
- **Auth flows added to vector**: login, logout, onboarding (previously unlisted)
- **Flow YAML references added** to coverage status for traceability
