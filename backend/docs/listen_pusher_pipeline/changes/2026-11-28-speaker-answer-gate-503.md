# Speaker answers use 503 for retryable account-gate contention

## What changed

When the account destructive-operation fence is busy, these answer paths return
`account_gate_busy` with HTTP 503 and `Retry-After`:

- Review answers in `routers/review.py`.
- Speaker-tag prompt answers in `routers/speaker_tag_prompts.py`.
- Manual speaker assignments in `routers/conversations.py`.

The speaker-label rejection route retains its 409 mapping. The 2026-11-24 note is
historical for the three routes above.

## Why

Released clients treat 409 as stale evidence: Review can mark an item answered
elsewhere, and speaker-answer clients can discard a prompt or mark speaker data stale.
Account-gate contention is retryable and happens before the answer is written, so 503
with `Retry-After` preserves the answer for retry without weakening the write fence.

503 may be counted by server-error telemetry. This change does not alter production
alerts or SLO configuration; monitor the `account_gate_busy` detail while evaluating
that telemetry.

## Rollout / rollback

No flag, schema or production state change. Revert only the reviewed mapping commit if
verification regresses; the account fence continues to block writes.

## Evidence

- Issue SCA-4949.
- Focused assignment and HTTP-boundary tests; bounded pre-push checks.

## Contract link

See the assign-speaker contract in `../../listen_pusher_pipeline.mdx` (§ speaker
assignment range edits); this note records the route-specific retryable status.
