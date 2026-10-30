# Mobile browser authorization

`launchIntegrationOAuth` owns the browser handoff for Google Calendar/Gmail,
Todoist, Asana, Google Tasks and ClickUp. It obtains the existing authenticated
backend OAuth URL and launches it in the system browser. It uses the actual
launch result: `canLaunchUrl` can return false on Android 11+ when package
visibility queries are missing even though a browser can handle the URL.
The referral page uses the same handoff for `https://affiliate.omi.me/` because
Google authorization and popup-based signup cannot run reliably inside an
embedded WebView. It has an explicit Open action and a retry after launch failure.

The handoff has one 45-second total deadline (15 seconds for the fixed referral
URL). Failed/expired URL lookup cannot start a browser later. A stalled native
launch releases the caller; the operating system may still finish that launch.
A successful handoff never asserts that an integration is connected.

## Connection authority

The existing IntegrationProvider and TaskIntegrationProvider own status reads.
Each read has a bounded deadline and a generation tied to its account session.
Ordinary concurrent reads coalesce. Returning from OAuth starts a fresh read,
and superseded, timed-out or prior-account replies cannot replace it.
Integration services preserve cached authentication on unreadable responses.
The UI marks an unverified row as Try Again instead of presenting it as a fresh
Connect/Disconnect verdict. One malformed integration does not hide successful
statuses for other integrations. Task snapshots validate before cache adoption. The task-status DTO contains
`app_key` and `connected`; provider tokens remain on the server. Client connection
checks use that verdict, never the presence of a serialized access token.

Task authorization keeps the prior default until the server confirms the new
grant, then persists the selection. A selection owns its attempt from the
confirmation dialog through launch, polling and save; choosing another app while
an earlier authorization is still launching retires it (latest selection wins).
A launch that throws reports failure and leaves no loading state behind. Failure to persist the default remains
retryable. An unfinished browser flow shows instructions and a manual status
check; it never becomes an endless spinner or a confirmed grant.

## Implementation and release checklist

- [x] System-browser referral signup with reachable launch retry.
- [x] Shared OAuth handoff uses real launch outcome and bounded deadline.
- [x] Terminal, retryable read failures preserve saved connection information.
- [x] Fresh post-auth reads fence old reads and account changes.
- [x] Task selection follows server-confirmed authorization.
- [x] Latest task selection wins even while an older authorization is still
      launching; late receipts after page or account changes do nothing.
- [x] Overlapping default saves land in choice order; only the latest publishes.
- [x] An MCP registration is reused only for its own URL, never after an edit.
- [x] Hermetic production-widget, native-bridge and provider regressions.
- [ ] Merge the fix and ship an Android store release (also validate iOS).
- [ ] On Samsung S26 Ultra, complete referral Google signup and return to Omi.
- [ ] Verify the reported integration(s) connect and display the server result.
- [ ] Identify the separate repeated Try Again screen with app version and a
      screenshot or exact screen name; investigate any remaining failure.
- [ ] Keep #21378 open until the release ships and the customer confirms.

Featurebase incident: https://github.com/BasedHardware/omi/issues/21378.
The report does not identify the failing integration(s), app version or general
error screen. These code defects are verified; the complete customer outcome is
not. No account contents or recordings are changed by this fix.

References:
- https://pub.dev/packages/url_launcher#checking-supported-schemes
- https://developers.googleblog.com/upcoming-security-changes-to-googles-oauth-20-authorization-endpoint-in-embedded-webviews/

## Completion audit after #21381

The first PR was merged while the audit continued. The follow-up closes the
remaining mobile and web client gaps:

- Native Calendar/Gmail and task authorization keep checking when the grant is
  saved after foreground return; default selection follows the confirmed grant.
- Marketplace setup uses a typed successful boolean verdict, serial probes,
  bounded initial/detail reads and explicit retry. Failed responses and absent
  endpoints cannot claim setup complete. Only explicit setup/enable intent may
  auto-install after confirmation.
- MCP waits for approval AND the server's enable receipt, bounds creation/status
  calls, retries an existing registration only for the URL it was made for,
  stops waiting when the URL is edited, cancels on leaving and cannot pop a
  different route from a late callback.
- External settings/home pages join affiliate signup in the system browser;
  embedded Google popup handling and spoofed user agents are retired. URL/uid
  construction, server-stored grants and conversation data are preserved.
- Vendor completion probes use the documented uid contract without forwarding
  Omi's Firebase bearer token; vendor failures cannot expire the Omi session.
- Web referral activation has one token/request/body deadline, a working manual
  retry and account/route ownership fences. It does not automatically retry an
  eligibility rejection or alter the desktop referral destination.

These recovery changes do not change Firebase's auth domain, provider callback
URIs or auth-helper proxy, and can be merged independently of #21355. The new
MCP reauthorization route must be available on the target backend before clients
using fresh OAuth retries are released; merging code does not deploy that route.

Complete resolution of #21378 also needs #21355's separate web sign-in fix.
That PR changes the Firebase helper origin: its web client and generated Bun
proxy are one coordinated release unit, and its exact Google/Apple callback
settings must be verified before that change is rolled out. Follow the
`web/app/docs/firebase-auth.md` from #21355, including authorized-domain coverage
(a configured parent domain can cover its subdomains). Verify Google/Apple
sign-in, referral return, cancellation and destination preservation in the
provider-connected integration environment. Simulator/browser acceptance is
sufficient for code verification; the reporter's Samsung outcome is separate
release/customer follow-up. Local provider fixtures do not verify live settings.
The unspecified general Try Again screen still requires the reporter's screen,
version and integration names; this audit does not invent its cause or close the
customer incident from code merge.

## MCP retry and callback commit ownership

An explicit retry uses the existing registration and requests a fresh single-use
OAuth state and PKCE verifier. Verifier rotation updates only that nested field,
so a callback finishing during provider discovery cannot have its tokens erased.
The callback exchanges its code and discovers tools outside Firestore, then
atomically compares the app owner and verifier before committing credentials,
tools and approval. A newer retry, changed owner or deleted registration retires
that callback: it returns 409 and cannot enable the app or replace newer tokens.
Successful current callbacks retain the existing automatic enable behavior.

Verification checklist:

- [x] Held token-exchange and tool-discovery callbacks cannot overwrite a newer
      completed authorization; only the current callback enables the app.
- [x] Strict transaction tests reject changed owner/verifier and missing records,
      preserving unrelated integration fields on a successful commit.
- [x] Local HTTP OAuth/MCP provider validates PKCE; real isolated Redis checks
      single-use state/replay and enablement, with Firestore emulator persistence.
- [ ] For #21355 and complete incident resolution, verify real provider
      configuration and Google/Apple sign-in/referral return. The local MCP
      provider is synthetic, not proof of those settings or customer recovery.
