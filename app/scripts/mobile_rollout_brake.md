# Android production rollout brake

Manually dispatch Codemagic workflow `android-rollout-brake` with `BRAKE_ACTION=status|halt|resume|stage`
and `BRAKE_VERSION_CODE=<exact code>`. Mutations also require `CONFIRM=brake`.
Read status first, perform the authorized action once, then read status again. Keep each
Codemagic build ID and its `BRAKE_RESULT` line. A failed or uncertain mutation requires
a fresh status read before another action; never blindly retry it.

Before even a status read, disable `mobile_rollout_watch.yml` and `mobile_daily_train.yml`.
The tool checks both are manually disabled and their GitHub runs have completed, failing
before opening a Play edit if verification fails. Also wait for previously dispatched
Codemagic `mobile-daily-train`, `mobile-rollout-advance`, and `mobile-store-promote` builds
to finish. Do not run any other Play writer or use Play Console concurrently. GitHub
dispatch completion does not prove the Codemagic build it started has finished.
Confirm that Play Console has no unrelated changes waiting to be sent for review:
an API edit commit can submit those too. `CONFIRM=brake` attests these operator
prerequisites in addition to authorizing the selected status change.

These are operator prerequisites: the tool does not hold a distributed lock against
other Codemagic workflows, other API users, or Play Console. Concurrent edits invalidate
one another, so a new writer can still make the operation fail closed. Keep the writers
disabled until the separate final status is verified; do not restore them without the
release owner's approval. The brake never re-enables them itself.

`BRAKE_ACTION=stage` replaces a halted release with a fixed build. It takes
`BRAKE_VERSION_CODE=<new code>`, `BRAKE_SUPERSEDES_VERSION_CODE=<halted code>`,
`BRAKE_USER_FRACTION=<0..1>`, a one-line `BRAKE_NOTES_LINE` and `CONFIRM=brake`. It refuses unless production holds
the superseded code as `halted` beside completed releases only, the new code sits alone
on internal or alpha under one newer marketing version, and the fraction does not exceed
the halted one. It writes one `inProgress` release named with the train's gate receipt
(`1.0.569 (gate YYYY-MM-DD-HHMM)`) so the ladder can advance it later. Notes copy the
halted release's What's New and append `BRAKE_NOTES_LINE` (replacing the last line when
appending would pass Play's 500-character limit) to en-US and to every locale
holding the identical English text; real translations stay unchanged. Completed releases
stay untouched. Read status of the halted code first and of the new code afterwards.

Halt and resume change status only. Country-targeted mutations are explicitly unsupported:
Play allows `countryTargeting` only on `inProgress` releases, and stripping it would change
more than status. Use an approved Play Console procedure for those releases. A brake
commit uses `ERROR_IF_IN_REVIEW` to refuse cancellation/resubmission of existing reviews.
Readback must match the complete expected production track, including its original fraction.
Unused-edit cleanup failures emit a static warning without hiding a verified result.

Google's contracts: [edit concurrency](https://developers.google.com/android-publisher/concurrency-considerations),
[commit review behavior](https://developers.google.com/android-publisher/api-ref/rest/v3/edits/commit),
and [release field constraints](https://developers.google.com/android-publisher/api-ref/rest/v3/edits.tracks).
