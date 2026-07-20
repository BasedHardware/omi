# Omi RN — Next Build Plan (backend + UI)

## Status (build 3e810156, account georgesg/frontforumfocus)
- UI matches Flutter: Home (Connect+Record, Daily Recaps, Mind Map, input+micro),
  nav = Home / Conversations / Goals / Apps. Settings hidden from nav, reachable via Connect.
- Backend wiring ALREADY PRESENT:
  - `src/auth/firebaseAuth.ts` calls `setAuthToken(token)` on auth change → Bearer token on `omiApi`.
  - Stores call real Omi REST: `listConversations` (/v1/conversations), `getMemories` (/v3/memories),
    `getActionItems` (/v1/action-items). Base URL `https://api.omi.me` (app.json extra).
- Open question: does the signed-in Firebase user have data on api.omi.me, and do CORS/auth
  on the device allow the calls? Empty states seen may just be no data for the new account.

## A. Backend connection (next steps)
1. **Verify live data flow** on device:
   - After sign-in, check logcat for `/v1/conversations` / `/v3/memories` 200 vs 401/403.
   - If 401: confirm `setAuthToken` fires before store `load()` (init order in _layout).
   - If 403/CORS: api.omi.me may require the request to originate from an allowed app; may need
     a dev API key (DevApiKeyProvider equivalent) or a self-hosted backend.
2. **Decide backend target**: live api.omi.me (shared prod) vs self-hosted Omi backend
   (repo has `backend/` — FastAPI). For a real account's data, prod api.omi.me is correct IF the
   Firebase project is the official Omi one (it is: webClientId + google-services.json = com.omi.app).
3. **Wire remaining endpoints** used by Flutter tabs:
   - Conversations tab "Goals" (impact metric) → `/v1/goals` (exists in API comments; add fn).
   - Apps tab "Enable/Open" → real integration toggle via `/v1/integrations` (currently placeholder).
   - Mind Map → `/v1/knowledge-graph` (real graph, not just memory tags).
   - Daily Recaps → `/v1/recaps` or derive from conversations by day (current derive is fine).
4. **Real-time / capture**: Capture tab uses local `captureStore` (no STT yet). To match Flutter,
   need Deepgram STT via `deepgramWsUrl` (key empty → must supply) + push transcript to backend.
5. **Profile/Settings**: sign-out works; add account info, device connect (BLE) later (Phase 3).

## B. UI (next steps, to match Flutter more closely)
1. **Bottom nav icons**: currently text-only ("Home/Conversations/Goals/Apps"). Flutter uses icons.
   Add icons (e.g. Ionicons) + labels per tab.
2. **Home polish**:
   - Daily Recaps: horizontal scroll cards with date (Flutter shows date sub-label) — done structurally,
     add date badge + "View All".
   - Mind Map: tappable nodes → expand graph view (Flutter "Expand").
   - Mic button: wire to open Capture/voice flow instead of no-op.
3. **Conversations tab**: add "Goals" impact header (0/1 style) + "All" filter chip (match Flutter).
4. **Goals tab**: currently action-items list; add impact metric + LATER/NO DEADLINE groups (done).
   Confirm `/v1/action-items` returns data for the account.
5. **Apps tab**: replace placeholder list with real integrations fetch + Enable/Open state.
6. **Settings**: reachable via Connect; add profile, sign-out, device connect entry.

## C. Build/release pipeline
- EAS project moved to `georgesg/frontforumfocus` (new account, fresh quota).
- Builds: `837f44d1` (first redesign), `3e810156` (nav fix) on new account.
- PR #1 on palontologist/omi (branch rn-flutter-home) tracks all RN work.
- Local build blocked (no SDK platforms/build-tools); EAS works.

## Priority order for next build
1. Verify backend live-data (token + endpoints) — blocker for "real" app.
2. Apps tab real integrations + Mind Map from knowledge-graph.
3. Nav icons + Home recaps date badges + mic→capture.
4. Conversations Goals header.
5. Capture STT (Deepgram) when key available.
