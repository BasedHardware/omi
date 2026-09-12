# Explicit automation effects

Every `DesktopAutomationActionRegistry.register` call requires an `effects` set.
Include every effect reachable through its parameters or asynchronously started
work. `[]` is reserved for side-effect-free observations and pure fixtures.
Names such as `probe`, `state`, or `snapshot` never determine safety: #13208
found an import probe and a state-clearing action mislabeled as read-only.

- `.localState`: changes app/UI state, defaults, local storage, or active work.
- `.localArtifact`: writes/export files, including screenshots.
- `.networkOrModel`: invokes the agent runtime, network services, or a model, including API reads.
- `.remoteWrite`: may modify remote user data, directly or through queued work.

Declare the union for parameter-dependent actions. Dynamic chat/tool dispatch
may reach all four effects. Incidental logging/analytics is outside this
product-effect contract. Existing handler authorization stays in force.

Discovery returns the stable, sorted `effects` array and derives the existing
coarse `safety` field from it. Mandatory effect descriptions come from the typed declaration; optional
specific descriptions supplement them. Surface
and category hints are not authorization decisions.

Use `./scripts/omi-ctl action about_snapshot --read-only` for an observation-only
invocation, or send `"readOnly": true` in the top-level `POST /action` JSON.
The registry rejects any declared effect before invoking the handler, including
handlers that launch asynchronous work. Invalid policy values fail before
dispatch. Ordinary invocations keep their existing behavior.

This is a declaration and dispatch contract, not a sandbox for arbitrary Swift
code. Review the actual handler/callees when assigning effects. Tests use injected
mutation handlers to prove pre-dispatch refusal and pin historical import,
delete, loading-snapshot, and artifact-writing cases without invoking services.
