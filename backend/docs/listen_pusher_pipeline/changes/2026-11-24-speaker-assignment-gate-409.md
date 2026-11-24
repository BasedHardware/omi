# Speaker assignment answers `account_gate_busy` while a destructive gate is live

## What changed

Manual speaker writes that hit the per-account destructive-operation fence now answer
the existing retryable `account_gate_busy` response (409 + `Retry-After`) instead of
escaping as an unhandled 500.

Mapped boundaries:

- `_assign_manual_speaker` in `routers/conversations.py` — segment, speaker and bulk
  assignment routes (`PATCH /v1/conversations/{id}/segments/{idx}/assign`,
  `/assign-speaker/{speaker_id}`, `/segments/assign-bulk`).
- `POST /v1/conversations/{id}/speakers/{speaker_id}/reject` in `routers/speaker_labels.py`.
- `POST /v1/speaker-tag-prompts/answer` in `routers/speaker_tag_prompts.py`.
- Review answers in `routers/review.py`; the offered answer is released for retry
  (`utils/review.py`) because the fence aborts before any write.

`DestructiveOperationInProgress`, `DestructiveGateTakeover` and
`LegalHoldAuthorityUnavailable` all map to the same 409, matching
`routers/memories.py`.

## Why

Cloud Error Reporting group `CJuCg4y69unbAw` recorded 13 events in 24 hours (12 in one
hour) on `PATCH /v1/conversations/{id}/assign-speaker/{speaker_id}`, all one client
retrying while the account's deletion gate was `running`. The fence itself is correct
and unchanged; only the HTTP boundary mapping was missing.

## Rollout / kill switch

No flag. Revert the mapping commit to restore the previous behaviour (the fence keeps
blocking writes; the 500 returns). No stored state, schema or fence authority changes.

## Evidence

- Issue SCA-4074.
- Tests: `tests/unit/test_account_gate_busy_http.py`,
  `tests/unit/test_speaker_labels_contract.py`,
  `tests/unit/test_speaker_tag_prompts_router.py`,
  `tests/unit/test_speaker_tag_prompts_service.py`,
  `tests/unit/test_review_stale_answers.py`.

## Contract link

See the assign-speaker contract in `../../listen_pusher_pipeline.mdx` (§ speaker
assignment range edits); this note adds only the error mapping, not a wire field.
