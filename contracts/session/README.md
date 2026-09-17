# Mobile session contracts

Versioned contracts binding the isolated local mobile-session lane (session
orchestration, seeding, evidence) shared by every consumer in the mobile
development-foundation program.

| Contract | Version | Owner | Consumers |
| --- | --- | --- | --- |
| [session-evidence-v1.schema.json](session-evidence-v1.schema.json) | 1 (frozen by Spine A / V8) | C1 session orchestration (`scripts/dev-harness`, SCA-487) | C2 semantic journeys, C3 capture replay, C4 verification integration, C5 device qualification |

## session-evidence-v1

One document per session, emitted by the session CLI
(`scripts/dev-harness/mobile-session.sh evidence <session-id>`), stored at
`<state-root>/mobile-sessions/<session-id>/evidence.json`.

Normative acceptance is `dev_harness.session_evidence.validate_evidence`, not
JSON Schema alone. The schema describes structure; the validator adds:

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

## Freeze policy (V8)

The optional `live` field was added **before** this freeze for V1 operation
attribution. Existing receipts omit it. Top-level source/artifact keep cold
build identity; live.loaded_source names the loaded Dart inputs. See
[LIVE_SESSIONS.md](../../scripts/dev-harness/LIVE_SESSIONS.md).

v1 permits only whitespace/key ordering and annotation edits (`title`,
`description`, `$comment`, `examples`). No validation change, even an additive
optional field: v1 readers use `additionalProperties: false`, so new writers
would break old readers. Adding/removing fields, required keys, enum values,
types, constraints, refs, or changing meaning/units requires a new v2 file and
explicit consumer migration. Do not overwrite v1 or its pinned test digest.
Open runner-version maps may acquire entries already allowed by the schema.

The active spine freeze test hashes the entire validation structure, including
nested definitions, and runs in the harness owner suite/local+CI manifest.
Annotation text cannot redefine semantics; reviewers own that boundary.
The Python validator also owns cross-field identity, path safety, chronology,
and accounting rules. V1 builder must implement live validation without
changing the frozen schema or relaxing old receipt rules. Its live validator
must reject traversal, successful reload/restart with daemon_code != 0, success
without loaded_source, unequal loaded/requested identities, and reversed times.
The protected `test_live_receipt_validates_structure_and_cross_field_claims`
is normative V1 acceptance; consumers must call the validator, even if JSON
Schema accepted the document. A live receipt is unsupported until it passes.
