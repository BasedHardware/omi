# Mobile session contracts

Versioned contracts binding the isolated local mobile-session lane (session
orchestration, seeding, evidence) shared by every consumer in the mobile
development-foundation program.

| Contract | Version | Owner | Consumers |
| --- | --- | --- | --- |
| [session-evidence-v1.schema.json](session-evidence-v1.schema.json) | 1 (proposed; pending C2/C3/C4 consumer review) | C1 session orchestration (`scripts/dev-harness`, SCA-487) | C2 semantic journeys, C3 capture replay, C4 verification integration, C5 device qualification |

## session-evidence-v1

One document per session, emitted by the session CLI
(`scripts/dev-harness/mobile-session.sh evidence <session-id>`), stored at
`<state-root>/mobile-sessions/<session-id>/evidence.json`.

Guarantees encoded in the schema (and enforced again by the Python validator
`dev_harness.session_evidence`, which consumers should treat as the executable
form of this contract):

- **Identity binds source to artifact to run.** `source.git_sha` +
  `source.dirty_digest` identify the checkout; `artifact.sha256`/`git_sha`
  identify what actually runs. States `ready`/`running` require an `artifact`
  whose `git_sha` matches `source.git_sha` — a stale build cannot be reported
  ready.
- **Fail-closed endpoints.** `endpoints` accepts loopback HTTP only and pins
  `egress_policy: loopback-only`. Production profiles (`mobile_beta`,
  `production`) are not valid session-evidence targets.
- **No credentials, ever.** No field carries tokens, secrets, passwords, or
  key material; the validator rejects credential-shaped keys anywhere in the
  document.
- **Honest accounting.** `counts` must account exactly (`passed + failed +
  skipped == executed`) whenever anything executed, and a zero-execution
  receipt is only valid while no run has been claimed (`creating`, `ready`,
  `blocked`).
- **Blocked is explicit.** `status.blocked_reason` is required exactly when
  `status.state` is `blocked`.

Change policy: v1 is proposed by C1, not frozen by a single worker. Additive
changes require consumer tests in every affected consumer (C2–C5) and a bumped
`schema_version` after coordinator + consumer review; do not widen v1 in place
until that review lands.
