# Home health review and repair

The worker produces an aggregate review using the default legacy Home list's visibility rules. It treats kept sync pieces held for notes as pending and finds captures that appear unfinished, waits past the transcript deadline, missing or overdue notes, and ready cards with title, preview, or emoji gaps. The JSON includes stable `issue_key` and `stage` values, the observed symptom, a next diagnostic check, the affected and observable rows, and a repeated-symptom count across owners. Three or more similar cards in the same window count as a repeat for an owner.

Use the feedback to prioritize what to reproduce with a synthetic account. A neutral emoji is an intentional option, so its frequency is a quality signal. A transcript receipt and a summary receipt are separate signals. A missing notes receipt describes delivery metadata, and does not establish that stored notes are empty. A summary receipt with a blank preview can indicate a display gap even when the notes exist.

## Review a cohort

From `backend/`, use the worktree's `.venv`. In production use `ro-prod` for review. Use a past UTC finish-time window, at least 15 minutes and at most 24 hours. A completed report is written to standard output. The command has no publishing destinations.

```sh
. ~/.local/bin/gcp-agent-env.sh ro-prod
.venv/bin/python -m scripts.home_health_worker \
  --project based-hardware --lane batch_live_v1 \
  --start "$WINDOW_START_UTC" --end "$WINDOW_END_UTC" > home-review.json
```

The query takes the newest rows per status, with a default of 200 and at most 500 per status. A one-row lookahead marks capped groups. Status groups below the privacy threshold are excluded from the review metrics and feedback. `survey_documents` counts the metadata scan including its lookahead when all status and row-category counts can be published. After a failed query, remaining groups report `not_scanned`. Compare equal lane, status coverage, window duration and deployed Home flags. Use the fleet Home census for representative fleet rates. This worker cannot see rows without a finish clock, other ingestion lanes, the encrypted prepared feed, or device-local state. Receipt absence by itself does not prove a transcript is absent.

The worker first scans protection, lifecycle and title provenance metadata. Status groups below the reporting threshold stop after this metadata read. In the same read-only transaction, the worker fetches the owner title where curation can release a visibility hold. It fetches the remaining card fields for eligible, visible completed rows with explicit cloud-sync opt-in. A settling row whose transcription exception requires reading notes is counted as `display_unknown`. No user or row reference, content, credential, or raw exception leaves the process. At least five owners must contribute to a published metric and its affected cell. Compare aggregate receipts internally and use stable issue keys to update a recurring finding.

`home_visibility_policy` records the operator's effective Home settings used for the run. Its source is `operator_environment`. Confirm those settings against the intended serving cohort before comparing a receipt to live Home behavior.

The survey omits transcripts, audio, photos, section bodies, tasks, events, producer-session maps, and prepared-display ciphertext. Unlike the full list reader, it can overcount blank or generic titles beside section-only notes, tasks, or events. For an empty-transcription receipt, it checks the audio close flags and bounds but lacks the producer-session evidence used by the full list. Verify these observations against a synthetic case before changing rendering or visibility.

## Arm an eligible obligation

Use `--apply --max-writes N --execute-before <UTC deadline>` only for an explicitly authorized batch-live cohort. The production apply identity is `prod-operator`. Just before applying, the CLI uses the installed agent environment and `gcloud` with `ro-prod` to inspect every `backend-integration` revision receiving traffic. Both summary switches must be effectively enabled. The admission kill switch uses the serving default when the revision leaves it unset. The CLI stops if it cannot verify the settings or if the receiving configuration changes during the read. It attempts at most one row per owner and at most 50 total in one invocation. A failed partial survey cannot enter apply. Each Firestore call, including commit and transaction retries, uses the remaining deadline. A request already sent can take effect after a client timeout, so a timeout ends the run and a later review rechecks admission. Candidate counts are preliminary and the transaction outcome is authoritative.

The transaction checks metadata, the projection and finalization generation, account and source protection, and BYOK before reading card text and section bodies. It verifies the bound finalizer and outbox ownership. It refuses a row that acquired notes, protection, an outbox, or a user-authored title or overview. A generated title, task, or event can be present on a row that still needs its first summary. This repair writes only the shared scheduling fields and verified finalizer receipt. It preserves the card, the accepted clock or original finish time, and an existing valid summary lane. The serving summary repair applies its own age and capacity bounds.

`armed` means scheduling metadata committed. After a complete scan, an apply with fewer than five candidates sets `candidate_owners_state` to `below_reporting_minimum`, makes no attempts, and exits 0. An apply with `outcomes_state` set to `below_reporting_minimum` suppresses the entire outcome breakdown and interruption flag and exits 1 to signal an inconclusive result. That receipt covers a sparse outcome cell or an apply phase with no attempts. Recheck admissions with a read-only review before retrying. After the normal repair sweep, compare `notes_not_scheduled`, `notes_overdue`, and `summary_receipted_cards` in that order. Use the existing summary repair and delivery metrics to verify that admitted work produced a summary. Keep recurring execution read-only so a single real fix shows up in subsequent receipts without repeatedly requesting work.
