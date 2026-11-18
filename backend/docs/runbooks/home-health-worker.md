# Home health review and repair

The worker produces an aggregate review of the legacy Home conversation list. It finds captures that appear unfinished, waits past the transcript deadline, missing or overdue notes, and ready cards with title, preview, or emoji gaps. The JSON includes stable `issue_key` and `stage` values, the observed symptom, a next diagnostic check, the affected and observable rows, and a repeated-symptom count across owners. Three or more similar cards in the same window count as a repeat for an owner.

Use the feedback to prioritize what to reproduce with a synthetic account. A neutral emoji is an intentional option, so its frequency is a quality signal. A transcript receipt and a summary receipt are separate signals. A missing notes receipt describes delivery metadata, and does not establish that stored notes are empty. A summary receipt with a blank preview can indicate a display gap even when the notes exist.

## Review a cohort

From `backend/`, use the worktree's `.venv`. In production use `ro-prod` for review. Use a past UTC finish-time window, at least 15 minutes and at most 24 hours. A completed report is written to standard output. The command has no publishing destinations.

```sh
. ~/.local/bin/gcp-agent-env.sh ro-prod
.venv/bin/python -m scripts.home_health_worker \
  --project based-hardware --lane batch_live_v1 \
  --start "$WINDOW_START_UTC" --end "$WINDOW_END_UTC" > home-review.json
```

The query takes the newest rows per status, with a default of 200 and at most 500 per status. A one-row lookahead marks capped groups. `survey_documents` includes the lookahead when every nonempty status group meets the privacy threshold. Compare equal lane, status coverage, window duration and deployed Home flags. Use the fleet Home census for representative fleet rates. This worker cannot see rows without a finish clock, other ingestion lanes, the encrypted prepared feed, or device-local state. Receipt absence by itself does not prove a transcript is absent. Existing noisy or intentionally short rows are treated as such where the visibility policy has the evidence.

No user or row reference, content, credential, or raw exception leaves the process. The survey reads only the legacy card fields and lifecycle metadata. It does not fetch transcripts, audio, photos, full notes or prepared-display ciphertext. It does not decrypt protected fields. Locked or unsupported protection levels are counted separately. At least five owners must contribute to a published metric and its affected cell. Compare aggregate receipts internally and use stable issue keys to update a recurring finding. Keep the report out of public issue bodies until the existing issue owner has reviewed it.

## Arm an eligible obligation

Use `--apply --max-writes N --execute-before <UTC deadline>` only for an explicitly authorized batch-live cohort. The production apply identity is `prod-operator`. Just before applying, the CLI uses the installed agent environment and `gcloud` with `ro-prod` to inspect every `backend-integration` revision receiving traffic. Both summary switches must be effectively enabled. The admission kill switch uses the serving default when the revision leaves it unset. The CLI stops if it cannot verify the settings or if the receiving configuration changes during the read. It attempts at most one row per owner and at most 50 total in one invocation. A failed partial survey cannot enter apply. Each Firestore call, including commit and transaction retries, uses the remaining deadline. A request already sent can take effect after a client timeout, so a timeout ends the run and a later review rechecks admission. Candidate counts are preliminary and the transaction outcome is authoritative.

The transaction reloads the conversation, checks the same projection, content, and finalization generation, then verifies account and source protection, BYOK, the bound finalizer, and outbox ownership. It refuses a row that acquired notes, protection, an outbox, or a user-authored title or overview. The write is limited to the shared first-summary scheduling fields and verified finalizer receipt. The accepted clock or original finish time is preserved. The serving summary repair applies its own age and capacity bounds. The worker does not enqueue provider calls, restart transcripts or seals, overwrite a card, or change deployment settings.

`armed` means scheduling metadata committed. Repeat the read-only review of the same window after the normal repair sweep and compare `notes_not_scheduled`, `notes_overdue`, and `summary_receipted_cards` in that order. Use the existing summary repair and delivery metrics to verify that admitted work produced a summary. Keep recurring execution read-only so a single real fix shows up in subsequent receipts without repeatedly requesting work.
