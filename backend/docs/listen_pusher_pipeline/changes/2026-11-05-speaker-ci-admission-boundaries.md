# Preserve recurring binding after batch speaker resolution

Recurring voice binding uses shared batch rollout admission after segments have
conversation-level scopes. Requiring original unit scopes is specific to audio
reconstruction; applying that requirement to binding suppressed manual profile
confirmation and consequently prevented person revocation from clearing links.
The rollout switches, percentages, evidence requirements and privacy checks are
unchanged. A regression test keeps resolved binding eligible while preventing
those scopes from reopening the audio pass.

The isolated Pusher canary expectation now includes `BATCH_FINAL_PASS_ENABLED`
alongside every existing ConfigMap reference. All four must use the proposed
canary ConfigMap. The capture-loss test's extracted persistence hook supplies its
settlement closure, with additional checks for once-only success/failure callbacks.

GCS SDK exception identities live at the database transport boundary. The speaker
retry classifier keeps legacy SDK timeouts/connections transient and TLS errors
terminal without importing the legacy HTTP client into application utilities.
