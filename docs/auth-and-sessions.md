# Auth, sessions, and the native transport contract

All authentication and authenticated networking is native (Objective-C++ /
Java / Kotlin); JavaScript never holds session tokens or performs
authenticated fetches. This doc describes the flows and the wire contract;
file pointers first:

- `react-native/src/v5BackendOrigin.ts` — software-plane selection
  (`omi.backend.softwarePlane`), v5 origin validation, the
  `stampedV5Origin` launch/persistence rule.
- `react-native/src/legacyOmiChat.ts`, `legacyOmiReads.ts` — Old-plane
  transport (`api.omi.me`).
- `react-native/src/deviceSessionClient.ts`, `taskMutationClient.ts`,
  `chatClient.ts`, `recordingJournalClient.ts` — New-plane clients.
- Native hosts: `macos/RnRuntime-macOS/OmiAuthModule.mm`,
  `OmiBackendModule.mm`, `OmiAuthMobileCallback.h`; iOS counterparts;
  `android/app/src/main/java/com/rnruntime/OmiBackendTransport.java` (with
  documented Java mirrors of the shared C++ policy).
- Policy lives in `native-core/src/omi_backend_policy.cpp` — capture-path
  allowlist, timeout table, hostname classification. See
  [`native-core/AGENTS.md`](../native-core/AGENTS.md).

## Old and New backend

On macOS, **Settings → General → Backend** (also under AI & Automation)
selects **Old backend** (the existing `api.omi.me` account) or **New
backend** (the configured v5 origin); see
[desktop-app.md](desktop-app.md#home-conversations-settings). The native
transport reports its API contract explicitly:

- **Old** uses `/v2/messages` history and terminal chat streams,
  `/v1/conversations`, `/v3/memories`, and `/v1/action-items`. Old task
  edits use PATCH; after an uncertain result, a retry reads the task to
  confirm it instead of repeating a potentially non-idempotent write.
  Legacy records have no invented revision, account epoch, or snapshot
  completeness. Old chat cancellation stops the local request; server work
  may still finish.
- **New** keeps the ratified envelopes and admission protocol
  (`packages/contracts`, served by `apps/backend-worker` and
  `backends/example-platform`).

Chat terminals and audio packets use the shared Base64 codec
(`react-native/src/base64.ts`) without relying on browser `atob`/`btoa`
globals, which are absent in the macOS runtime.

## Platform sign-in flows

- **Android** uses the existing Google authorization and Firebase REST
  session flow through a native browser intent and PKCE, with the
  app-specific `omi-rnruntime://auth/callback` redirect. Tokens stay native
  and are encrypted in private preferences with an AndroidKeyStore AES-GCM
  key. Native HTTP reads and refreshes that session; Android generation SSE
  resumes with `Last-Event-ID`, returns terminal frames, and closes streams
  on cancellation or session invalidation; explicit sign-out suppresses
  environment credential fallback. After returning from the browser,
  Cancel sign-in immediately retires the pending native attempt while
  preserving any existing session; unused attempts also expire after five
  minutes. End-to-end provider completion and AndroidKeyStore persistence
  still require device verification.
- **iOS and macOS** share the native Firebase session implementation. iOS
  presents the system authentication session with the app-specific
  `omi-rnruntime://auth/callback` redirect and PKCE and stores only its own
  sandboxed keychain session; macOS retains its browser and loopback
  callback.
- **Desktop handoff** (sign in on the web, land in the app) is the Worker's
  `/v1/auth/desktop/*` flow — see
  [backend-worker.md](backend-worker.md#desktop-sign-in-handoff).

`scripts/test-apple-auth` validates the mobile callback rejection rules
using Foundation on macOS and runs in CI; live provider sign-in still
requires device verification.

## Capture ownership

Native capture uses an encrypted, ownership-bound recording journal: the
first recording requires an authenticated portable ownership receipt; later
offline capture may reuse only its exact cached login/origin binding after a
classified connectivity failure; replay obtains fresh ownership before
sending indexed packet batches. Existing Worker transcripts remain readable,
but the Worker cannot establish journal ownership. Native keys and receipts
stay outside JavaScript. See
[native-recording-journal.md](native-recording-journal.md).

## Device identity

Apple and Android read the available model, firmware, hardware,
manufacturer, and serial characteristics from the standard Device
Information service; connected-device details show Unknown for absent or
invalid values. Coverage matrix:
[hardware-device-parity.md](hardware-device-parity.md).
