# Integration connections

IntegrationProvider and TaskIntegrationProvider own saved connection state.
Service authentication methods only start a browser authorization attempt through
`launchIntegrationOAuth`; a launch is never a connection receipt. Status DTOs are
read from the existing API and provider secrets stay server-side.

`ConnectionWait` owns the lifetime of one user-started authorization wait. It
serializes probes, queues a fresh probe on foreground return, and stops on failure,
account/page cancellation, a connected verdict or its overall deadline. Its
caller's provider/page owns all adoption and mutations. `ConnectionRead` owns the
cancellable deadline for each dependency wait, so non-cooperative SDK replies
cannot leave timers or publish after their owner is cleared/disposed.

Marketplace app-detail setup uses the page's `app_setup_owner.dart` part: one
probe, one wait and a separate install receipt. MCP setup uses the same wait
policy and requires an approved, identity-matching server record before reporting
connection. Each Connect press is one attempt with an immutable submitted URL,
account and generation; every await in it (registration, browser launch, detail
read, wait) rechecks that it still owns the page before polling, navigating,
showing an error or changing the loading state. Editing the URL retires the whole
attempt, including a pending browser launch, so a late launch receipt never polls
the earlier server, and returning to that URL does not revive it. The registration
stays keyed to its own URL and account, so only an explicit new Connect on that URL
reuses it. Native task selection is saved only after a confirmed grant. Each
task selection owns its whole attempt from before its first await: confirmation
dialog, URL lookup and browser launch, polling and the default save. A newer
selection, a departed page or an account change retires it, so a late launch
receipt or delayed grant from an older attempt cannot overwrite that choice.
TaskIntegrationProvider writes defaults one at a time in choice order, skips a
queued choice replaced before it is sent, and publishes only the latest choice,
so overlapping saves cannot leave an older default on the server or screen. External web settings and affiliate pages use the system browser, with an explicit Open
and failed-launch retry; embedded Google OAuth/user-agent spoofing is retired.

No timer, presentation widget or SDK launch callback may assert a saved grant.
Regression coverage: `test/services/integrations/`, the integration provider
suites, `app_install_flow_test.dart`, `android_hanging_flows_test.dart` and
`mcp_connection_recovery_test.dart` (held browser-launch, cached-retry and detail-read Futures).
