# Omi Mobile App Feature Vector for Flow-Walker
## Codex-Validated Report — 2026-03-12

### Purpose
Prioritized feature map to guide jin's flow-walker for maximum coverage of core Omi mobile app flows. Uses two scoring dimensions from the Omi Issue Triage Guide.

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
- 1 = needs human setup first, then walker can verify
- 0 = unreachable (BLE, SMS, external OAuth, real payment)

---

## Feature Vector (sorted by priority × walker_score)

### CORE DAILY (priority 9-15, walker_score 2-3)

| # | Feature | Layer | Priority | Walker | Coverage Status |
|---|---------|-------|----------|--------|-----------------|
| 1 | Conversation list & browse | capture (5) | 15 | 3 | ✅ covered |
| 2 | Conversation detail (transcript/summary/actions tabs) | capture (5) | 15 | 2 | ✅ covered |
| 3 | Memory list & browse | memory (4) | 12 | 2 | ✅ covered |
| 4 | Memory search | memory (4) | 12 | 2 | ✅ covered |
| 5 | AI Chat open/close (Ask Omi) | intelligence (3) | 9 | 2 | ✅ covered |
| 6 | Action items view | intelligence (3) | 9 | 2 | ✅ covered |
| 7 | Daily summary/score (home cards) | intelligence (3) | 9 | 2 | ✅ covered |
| 8 | Global search | retrieval-action (3) | 9 | 2 | ✅ covered |
| 9 | Task management (create via FAB, toggle) | retrieval-action (3) | 9 | 2 | ⚠️ partial |
| 10 | Conversation recording (phone mic) | capture (5) | 15 | 1 | ✅ covered (needs mic perm) |

### CORE WEEKLY (priority 6-12, walker_score 2)

| # | Feature | Layer | Priority | Walker | Coverage Status |
|---|---------|-------|----------|--------|-----------------|
| 11 | **Memory review/approval** | memory (4) | 12 | 1 | ❌ GAP |
| 12 | Memory categories & filter | memory (4) | 8 | 2 | ⚠️ partial |
| 13 | **Add/edit memory manually** | memory (4) | 8 | 2 | ❌ GAP |
| 14 | Memory graph visualization | memory (4) | 8 | 2 | ✅ covered |
| 15 | **Custom vocabulary** | understand (4) | 8 | 2 | ❌ GAP |
| 16 | **Speaker identification (People)** | understand (4) | 8 | 1 | ❌ GAP |
| 17 | **Goals tracking** | intelligence (3) | 6 | 2 | ❌ GAP |
| 18 | **Conversation sharing/export** | retrieval-action (3) | 6 | 2 | ❌ GAP |
| 19 | **Conversation folders** | retrieval-action (3) | 6 | 2 | ❌ GAP |
| 20 | App marketplace browse | retrieval-action (3) | 6 | 2 | ✅ covered |
| 21 | App detail & install | retrieval-action (3) | 6 | 2 | ✅ covered |
| 22 | Offline sync UI | capture (5) | 10 | 2 | ✅ covered |

### SETUP-ONLY (priority 3-5, mostly covered)

| # | Feature | Layer | Priority | Walker | Coverage Status |
|---|---------|-------|----------|--------|-----------------|
| 23 | Transcription settings | understand (4) | 4 | 2 | ✅ covered |
| 24 | Language selection | understand (4) | 4 | 2 | ✅ covered |
| 25 | Speech profile | understand (4) | 4 | 1 | ✅ covered |
| 26 | Device connection | capture (5) | 5 | 0 | ⚠️ UI only |
| 27 | Task integrations | retrieval-action (3) | 3 | 0 | ✅ list only |
| 28 | Calendar integration | retrieval-action (3) | 3 | 0 | ⚠️ OAuth blocked |

---

## Top 7 Coverage Gaps (core features, reachable, no walker coverage)

| Rank | Feature | Priority | Walker Score | Navigation Path |
|------|---------|----------|--------------|-----------------|
| 1 | Memory review/approval | 12 | 1 | Needs conversation processing → auto-created memories → review dialog |
| 2 | Custom vocabulary | 8 | 2 | Settings → Profile → Custom Vocabulary (needs scroll in Profile) |
| 3 | Add/edit memory manually | 8 | 2 | Memories tab → FAB → dialog → (needs text input) |
| 4 | Speaker identification (People) | 8 | 1 | Settings → Profile → Identifying Others (needs scroll) |
| 5 | Goals tracking | 6 | 2 | Home → Goals widget → Add Goal |
| 6 | Conversation sharing/export | 6 | 2 | Conv detail → share button → share sheet |
| 7 | Conversation folders | 6 | 2 | Home → folder tabs above conversation list |

---

## BFS Run Plan for Flow-Walker

### Phase 1: Core Shell (depth 1) — ALL PASS ✅
Walker already covers this at depth 2. Validated steps:
1. Home baseline → screenshot + element count
2. Settings drawer open/close
3. Search toggle open/close
4. Bottom nav: Tab 0 → 1 → 2 → 3 → 0

### Phase 2: Core Branches (depth 2-3) — MOSTLY PASS ✅
| Step | Path | Status |
|------|------|--------|
| 2.1 | Conv list → tap item → detail → Summary tab → Action Items tab | ✅ PASS (if conversations exist) |
| 2.2 | Action Items → FAB → task form sheet | ✅ PASS (open only, can't type) |
| 2.3 | Action Items → task checkbox toggle | ✅ PASS_IF_ITEMS_EXIST |
| 2.4 | Memories → graph icon → graph view | ✅ PASS |
| 2.5 | Memories → FAB → add memory dialog | ✅ PASS (open only) |
| 2.6 | Apps → first app card → app detail | ✅ PASS |
| 2.7 | Apps → filter/category buttons | ✅ PASS |
| 2.8 | Home → Ask Omi button → chat page | ✅ PASS (open only, can't type) |
| 2.9 | Home → Goals widget → Add Goal | ✅ PASS (new — targets gap #5) |
| 2.10 | Conv detail → share button | ✅ PASS (open sheet, can't complete share) |
| 2.11 | Home → folder tabs | ✅ PASS (new — targets gap #7) |

### Phase 3: Settings Drawer Rows (depth 2) — PARTIAL ⚠️
| Step | Path | Status |
|------|------|--------|
| 3.1 | Settings → Profile | ✅ PASS |
| 3.2 | Settings → Notifications | ✅ PASS |
| 3.3 | Settings → Plan & Usage | ✅ PASS |
| 3.4 | Settings → Offline Sync | ✅ PASS |
| 3.5 | Settings → Device Settings | ✅ PASS |
| 3.6 | Settings → Integrations | ❌ FAIL (below fold — **needs scroll**) |
| 3.7 | Settings → Phone Calls | ❌ FAIL (below fold — **needs scroll**) |
| 3.8 | Settings → Developer | ❌ FAIL (below fold — **needs scroll**) |
| 3.9 | Settings → Referral | ❌ FAIL (below fold — **needs scroll**) |

### Phase 4: Deep Sub-Pages (depth 3-4) — MOSTLY FAIL ❌
| Step | Path | Status |
|------|------|--------|
| 4.1 | Profile → Language | ✅ PASS |
| 4.2 | Profile → Custom Vocabulary | ✅ PASS (navigation; text entry blocked) |
| 4.3 | Profile → Speech Profile | ❌ FAIL (needs scroll in Profile page) |
| 4.4 | Profile → Identifying Others | ❌ FAIL (needs scroll) |
| 4.5 | Profile → Data Privacy | ❌ FAIL (needs scroll) |
| 4.6 | Integrations → Calendar connect | ❌ FAIL (scroll + OAuth) |
| 4.7 | Integrations → Task providers | ❌ FAIL (scroll in integrations) |

---

## Recommendation for Jin

### Immediate (depth 3, no code changes needed)
Run depth 3 on current walker. Expected: **24 → 27-29 screens** (+3-5). New screens from Phase 2 depth-3 branches (conv detail tabs, FAB sheets, goals widget, folder tabs).

### Next Priority: Implement Scroll
Scroll-then-press unlocks **8-12 additional screens** in settings/profile. This is the single highest-leverage feature to implement:
- Settings drawer rows 6-9 (Integrations, Phone Calls, Developer, Referral)  
- Profile sub-pages below fold (Speech Profile, People, Data Privacy)
- App list scrolling (more apps visible)

### After Scroll: Input/Fill
Text input unlocks actual feature testing (not just "open dialog"):
- Custom vocabulary add word
- Memory add/edit content  
- Chat send message
- Search type query

### Priority Order
1. **Depth 3** run with current capabilities (now)
2. **Scroll** implementation (highest leverage new capability)
3. **Input/fill** implementation (deepest feature testing)
4. **iOS support** (platform coverage)

---

## App Page Count Summary

| Category | Pages | Walker Reachable | Currently Covered |
|----------|-------|-----------------|-------------------|
| Core tabs (4 main + sub-pages) | ~25 | ~20 | ~18 |
| Settings (drawer + sub-pages) | ~30 | ~18 (with scroll) / ~12 (without) | ~13 |
| Standalone features | ~15 | ~8 | ~6 |
| Onboarding | ~12 | 0 (one-time) | 1 (manual) |
| **Total** | **~82** | **~46 (with scroll) / ~40 (without)** | **~38** |
