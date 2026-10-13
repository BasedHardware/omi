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
grant, then persists the selection. Failure to persist the default remains
retryable. An unfinished browser flow shows instructions and a manual status
check; it never becomes an endless spinner or a confirmed grant.

## Implementation and release checklist

- [x] System-browser referral signup with reachable launch retry.
- [x] Shared OAuth handoff uses real launch outcome and bounded deadline.
- [x] Terminal, retryable read failures preserve saved connection information.
- [x] Fresh post-auth reads fence old reads and account changes.
- [x] Task selection follows server-confirmed authorization.
- [x] Hermetic production-widget, native-bridge and provider regressions.
- [ ] Merge the fix and ship an Android store release (also validate iOS).
- [ ] On Samsung S26 Ultra, complete referral Google signup and return to Omi.
- [ ] Verify the reported integration(s) connect and display the server result.
- [ ] Identify the separate repeated Try Again screen with app version and a
      screenshot or exact screen name; investigate any remaining failure.

Featurebase incident: https://github.com/BasedHardware/omi/issues/21378.
The report does not identify the failing integration(s), app version or general
error screen. These code defects are verified; the complete customer outcome is
not. No account contents or recordings are changed by this fix.

References:
- https://pub.dev/packages/url_launcher#checking-supported-schemes
- https://developers.googleblog.com/upcoming-security-changes-to-googles-oauth-20-authorization-endpoint-in-embedded-webviews/
