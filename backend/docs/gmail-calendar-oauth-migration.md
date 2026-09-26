# Gmail + Calendar: cookie-scraping → Google OAuth (migration plan)

Status: **planned** · Scope: desktop onboarding "connect your context" import.

Ponytail note: this plan is deliberately reuse-first. It builds almost nothing new —
it wires the desktop to OAuth infra the backend already ships. Sections marked
`ponytail:` are corners cut on purpose, with the ceiling named.

## Why

Onboarding imports Gmail + Calendar by scraping browser cookies: it reads the
Chromium "Safe Storage" key from the macOS Keychain and decrypts the cookie DB
(`BrowserGoogleSession` + `GmailReaderService` / `CalendarReaderService`).

That path cannot be made silent or durable:

- macOS **mandates** a Keychain prompt to read another app's item; no entitlement
  removes the first prompt.
- It drifts every macOS version (Tahoe broke `/usr/bin/security` reads) and every
  browser version (cookie formats v10→v20 app-bound, keys migrating to iCloud
  Keychain).

Google OAuth is the only path that is silent, automatic, and version-proof.

## The seam (what changes vs. what does not)

The fetch layer is cleanly separable. Only these two functions change:

- `GmailReaderService.readRecentEmails() -> [GmailEmail]`
- `CalendarReaderService.readEvents() -> [CalendarEvent]`

Everything downstream is source-agnostic and stays byte-for-byte:

```
readRecentEmails()/readEvents()   ← REPLACE (cookies → OAuth)
        ↓ [GmailEmail]/[CalendarEvent]
synthesizeFrom*() (LLM)           ← unchanged
        ↓ ImportEvidenceBatchItem
OnboardingImportEvidenceService.save()
        ↓ POST /v3/memory-imports/batch   ← unchanged
```

`ImportEvidenceBatchItem` is the contract; keep producing it and nothing else moves.

## Reuse map — the backend already ships ~70% of this

| Piece | Where | Reuse |
|---|---|---|
| Google OAuth flow (PKCE, callback) | `backend/routers/auth.py` (scopes: `openid email profile`) | extend |
| Google token refresh + retry | `backend/utils/retrieval/tools/google_utils.py` | copy as-is |
| OAuth callback + Firestore token storage | `backend/routers/integrations.py` → `users/{uid}/integrations/{app_key}` | clone |
| **Live Google Calendar OAuth integration** | `backend/routers/integrations.py` (google-calendar) | **wire desktop to it** |
| Full OAuth+sync connector template | `backend/utils/x_connector.py` | mirror for Gmail |
| Onboarding state machine | `backend/routers/calendar_onboarding.py` | copy → gmail |
| Desktop loopback OAuth callback | `desktop/macos/.../AuthService.swift` | reuse |
| Gmail API client + Gmail scope | — | **build (only real new work)** |

## Architecture (decisions locked)

- **Backend-mediated.** Desktop calls the backend; the backend holds the token and
  calls Google. Keeps the client secret server-side, centralizes refresh via
  `google_utils`, and makes mobile/web free later.
- **Separate Google connector, not incremental-auth-on-sign-in.** Users who signed
  in with Apple have no Google token; a standalone connector works regardless of
  sign-in method (and matches how Calendar already works).
- **Gmail scope: `gmail.readonly`** (matches today's subject+snippet fidelity).
  ⚠️ This is a Google **restricted** scope → heightened verification + a likely
  annual third-party security assessment (CASA). Budget it. Calendar's scope is
  only "sensitive" and is already verified/live — which is why Calendar goes first.

## Phases

### Phase 0 — Calendar over OAuth (do first, small)
The backend Google Calendar integration already exists AND already reads events from
the Google API: `backend/utils/retrieval/tools/calendar_tools.py:290` calls
`googleapis.com/calendar/v3/.../events` with the stored OAuth token (refreshed via
`google_utils`). So Phase 0 is thin wiring, not new OAuth:
- Backend: expose a read endpoint (e.g. `GET /v1/calendar/events?days_back&days_forward`)
  as a thin wrapper over the existing `calendar_tools` list-events call. Hermetic test
  mocks the Google layer and asserts the response maps to the desktop `CalendarEvent`.
- Desktop: `CalendarReaderService.readEvents()` → call that endpoint (with the user's
  Firebase session) instead of scraping cookies.
- Trigger the existing `/v1/integrations/google-calendar` OAuth-url flow from the
  onboarding step when not yet connected; reuse `AuthService` loopback callback.
- Reuse `calendar_onboarding.py` status/skip/reset as-is.
- Result: Calendar import needs no Keychain prompt. Days, not weeks.

### Phase 1 — Gmail backend (bigger)
- Add `gmail.readonly` to a Google connector (clone the X/Calendar callback +
  `google_utils` refresh; store under `users/{uid}/integrations/gmail`).
- New Gmail API client + endpoint: list/get messages via
  `gmail.googleapis.com/gmail/v1/users/me/messages`, refresh-on-401.
- New `gmail_onboarding.py` (copy `calendar_onboarding.py`).
- **Compliance gate:** restricted-scope verification / CASA. Start early; it's the
  long pole, not the code.

### Phase 2 — Desktop swap + flag
- Put both readers behind a `useOAuth` flag at the seam; on failure fall back to the
  (now-fixed) cookie path during rollout.

### Phase 3 — Mobile / web
- Free once backend-mediated. ponytail: not designed here until Phase 2 lands.

## Explicitly NOT doing (ponytail cuts)

- **No new token-encryption scheme.** Reuse the existing `integrations/{app_key}`
  storage (plaintext at app layer, GCP-encrypted at rest), same as Calendar/X.
  Ceiling: if integration-token sensitivity policy changes, migrate all connectors
  together, not just Gmail.
- **No MCP-style multi-client OAuth tables** (`mcp_oauth.py`). YAGNI — one grant per
  user per provider via `integrations/{app_key}`. Ceiling: only needed if third-party
  clients must hold Gmail grants.
- **No incremental-auth-on-sign-in.** Standalone connector instead (works for Apple
  sign-in users).
- **Do not rip out the cookie path.** It stays as the Phase 2 fallback and covers any
  surface OAuth hasn't reached. The two committed cookie fixes (in-process Keychain
  read + unknown-version skip) remain.

## Open items

- Confirm the exact current Google restricted-scope verification requirements before
  committing Gmail work (policy shifts; verify against live Google docs).
- Map `calendar_tools` list-events output → desktop `CalendarEvent` (fields align;
  confirm all-day + attendee shapes).

## External blockers (cannot be done from the repo)

These gate a *working, verified* migration and are outside code:
- **Google OAuth client credentials** (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`) in a
  runnable/deployed backend — needed to exercise any live OAuth flow.
- **A Google-connected test account** to verify the Calendar/Gmail read path end to end.
- **Google Cloud consent-screen scope config**: adding `gmail.readonly` (restricted) and
  the Calendar scope to the app's OAuth consent screen.
- **Gmail restricted-scope verification / CASA** — a Google-side review measured in weeks.

Implication: backend/desktop code can be written with hermetic (mocked-Google) tests,
but the live OAuth path cannot be exercised until the above are in place. Do not mark
the feature "done" on hermetic tests alone.
