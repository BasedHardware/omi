# Floating control bar architecture

This package owns the compact/notch presentation, Push-to-Talk coordination, and
the realtime voice transport. UI views render `FloatingControlBarState`; they do
not own a second chat provider or make semantic routing decisions.

## Realtime hub

`RealtimeHubController` is the single owner of mutable voice-session state and
the facade used by `PushToTalkManager`. Its files are separated by lifecycle,
PTT ingress, provider callbacks, and authorized tool effects, but each
`RealtimeHubController` extension operates on that one state owner. Keep the
dependency direction as follows:

- `RealtimeHubController+SessionLifecycle` owns warm-session creation,
  replacement, context refresh, and output cleanup.
- `RealtimeHubController+PushToTalk` owns begin/feed/commit/cancel ingress.
- `RealtimeHubController+SessionDelegate` translates provider callbacks into
  reducer events and durable tool requests.
- `RealtimeHubController+Tools` performs only already-authorized local effects.
- Policy and value types (`RealtimeHubInputAdmission`, `RealtimeHubTools`,
  `RealtimeHubSessionPolicies`, and `RealtimeTurnPersistence`) stay pure or
  independently testable; they never acquire a second controller instance.

The controller may call the kernel-facing manager for typed context and durable
journal operations, but it must not reach directly into `ChatProvider` or make
agent-routing decisions. Provider tools remain untrusted until the kernel
returns an authorized command.

## Verification

Run the focused Swift tests with `xcrun swift test --package-path Desktop`, then
run `desktop/macos/scripts/agent-logic-harness.sh`. For PTT behavior changes,
also exercise a named `omi-*` development bundle; never target the production
Omi app.
