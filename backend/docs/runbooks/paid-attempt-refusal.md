# Paid-attempt refusal plans

The operator's normal dry-run remains the prerequisite for any apply. New plan
digests bind at most two attempts per unit; the second is allowed only after a
caught provider failure, never while running or after validated words/empty.
Both attempts count toward estimated spend and decoded-audio budgets. A refusal
creates no new intent. Audio, prior intent history, privacy and ledger fences
remain intact. A new token fences late writes from a failed first attempt.

## Historical no-call evidence

`batch_pipeline_speech_redrive.py --attest-refused-before-call` is **dry-run only**.
It accepts the existing exact-owner/time/ID arguments, either
`--prepared-independent --paid-epoch 1 --max-seconds <bound> --usd-cap <cap>` or
`--independent-language --paid-epoch 3`, and
`--zero-vendor-files-proof <private.json>`. It needs no encryption or vendor key
and does not download audio. `--apply` refuses before constructing cloud clients.
Use ro-prod to execute a real read-only plan; hermetic tests use strict fakes.

The private JSON proof has exactly these fields (fill real evidence hashes, not
the illustrative values below):

```json
{
  "version": 1,
  "vendor": "soniox",
  "source": "vendor_usage_export",
  "files_created": 0,
  "complete": true,
  "window_start": "2026-11-02T02:21:00Z",
  "window_end": "2026-11-02T02:38:00Z",
  "recorded_at": "2026-11-02T04:00:00Z",
  "usage_evidence_sha256": "<64 lowercase hex characters>",
  "apply_log_sha256": "<64 lowercase hex characters>",
  "scope_sha256": "<64 lowercase hex characters>"
}
```

`scope_sha256` is `redrive_scope.digest(redrive_scope.scope_body(owner,
'batch_pipeline_prod', quarantined_after_epoch, quarantined_before_epoch, silent,
sorted_exact_ids))`. Proof must cover every selected intent's actual start
(or preparation for an unstarted marker), with an inclusive start/exclusive end.
The export must be complete for the shared vendor account, not just a sampled
dashboard or one API page. `recorded_at` must be after the window closes. These
are operator attestations backed by retained exports and logs; JSON alone is not
independent vendor verification. Retain source evidence privately for lead review.

The plan seals the proof hash and full current job/intent fingerprint in a
create-only 0600 cohort file. A changed job or proof refuses replay. Output is
counts/digests only. Validated words/empty receipts, explicit spent markers,
active jobs, results or terminal dispositions refuse even if the proof says zero.
Renewed intents also refuse, including an empty history field or an original-token
field: a proof covering only the current window cannot classify earlier spend.
The flag cannot reopen any unit. A separate reviewed apply implementation and
the lead's authorization are required before historical mutation or spend.

For the 2026-11-02 incident, ask David/the lead for an authorized Soniox usage
read covering 02:21–02:38Z, with zero files created and evidence retained, plus
the lead's apply-log digest. This requires David's key access; do not request
that the key itself be shared. For older marker-refused units, use their actual
prior intent windows; a later refused command proves nothing about prior spend.
