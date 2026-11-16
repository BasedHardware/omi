# Fetch-decode payload-poison custody

The worker's fetch_decode boundary books a deterministic decode/parse poison
— a bare builtin `ValueError` raised while parsing or decoding the unit's own
stored bytes — through the bounded GPU retry ladder: one anonymous
`batch_worker_failed error_class=ValueError stage=fetch_decode` ERROR line
per attempt, five per drive, ending in the anonymous
`stage=unknown worker_reason=unclassified` terminal quarantine. Production
burned this family as the top worker signature (×791/30m at its peak) because
no retry can repair it: every attempt re-reads the same pinned bytes and
raises the same fault. A NaN admitted duration that `round()` refuses inside
the retained-manifest builder, a storage client refusing a malformed request
argument, and a text decode surfacing `UnicodeDecodeError` are the concrete
raise shapes; `json.JSONDecodeError` rides the same builtin class.

## The typed custody handoff

The boundary now claims the family with the closed token
`decode_payload_invalid` and ends the chain at its first occurrence, exactly
like the typed decode trio it sits beside:

- `diarizer.batch_pipeline.decode_payload_is_deterministic(error)` is the
  verdict: a `ValueError` instance that is NOT one of the typed decode-family
  classes (`StagedAudioInvalid`, `StagedArtifactInvalid`,
  `RetainedAudioInvalid` and its `InvalidRetainedManifest` subclass,
  `RetainedAudioOutsideAdmittedSource`, `DecodedDurationMismatch`,
  `BatchValidationError`). Top-level `isinstance` only — never an exception
  message — so the split cannot drift with payload wording.
- `decode_payload_failure_reason(error, stage, untyped_reason)` is the arm:
  stage-scoped to `fetch_decode` and gated on the anonymous `unclassified`
  attribution, so the typed arms' tokens and every other stage's faults are
  untouched.
- The `fail()` boundary books the terminal `ValidationFailureWork` route with
  the typed reason, the measured VAD evidence and the receipt — custody for
  the fenced independent-recognizer recovery lane, unchanged durable state
  semantics, no GPU ladder walk.
- `VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS` admits the token, so both
  terminal report channels demote together with the rest of the disposition
  family: the worker's emit books the INFO
  `event=batch_validation_disposition outcome=recovery_handoff` transition
  (keeping the `error_class=ValueError` diagnostic field), and the scheduler
  verdict terminal and the recover sweep's lease-expiry terminal book the
  INFO `event=batch_validation_disposition outcome=held_for_disposition`
  line instead of the anonymous
  `event=batch_quarantined reason=worker_failed` ERROR. The poison token at
  any other stage keeps its ERROR fault line; `unclassified` faults of other
  classes keep theirs.

## What changed for the sensor

The `error_class=ValueError stage=fetch_decode` worker-fault family loses its
ERROR channel entirely for the poison class: one INFO transition line per
settled unit instead of five ERROR lines per drive plus the anonymous
terminal quarantine. The `empty_asr` / `no_owned_words` and
`unsupported_language` families demoted the same way before; this joins the
bare-ValueError cohort to them.

## Scope discipline

- The transport families (`GoogleAPIError`, `TimeoutError`,
  `ConnectionError`), contention, `wave.Error` and every other non-ValueError
  class keep today's attribution and ladder custody.
- The typed decode family keeps its own tokens and its own chain-end
  behavior; the poison verdict excludes them defensively even though the
  boundary consults it only after those arms.
- `pack_windows`' padded-budget `ValueError` and provider call faults at
  later stages stay stage-scoped away from the arm.
- The verdict reads the exception type only; the report never carries an
  exception message.

## Tests

`tests/unit/test_fetch_payload_custody.py` pins the family end to end,
including the real poison raise site (a NaN admitted duration through the
real `materialize()` builder). The grid bands pin the full decision surface
cell by cell — every enumerated fault shape of the live venv (Google API
exception classes, legacy Cloud exceptions, builtins, typed family,
`BatchValidationError` reasons, hostile payloads, subclass shapes) across
every closed stage and attribution context, plus the shared terminal report's
channel for every (stage, reason) diagnosis across attempts and both flag
states — each cell cross-verified against the live boundary when the band was
generated.

## Ladder-walk bands

`tests/unit/test_decode_poison_walk_band_00..63.py` pin the custody walk
itself: every closed (stage, reason) diagnosis in both custody shapes
(terminal `worker_failure` and evidence-only) plus the bare and combined
shapes, driven through the real `Scheduler` over `MemoryStore` across every
bounded ladder walk — first-failing attempt through the exhaustion cap,
under both quarantine flags, with each interim custody sequence (bare,
evidence-refreshing with the same pair, with a foreign pair) — asserting the
full transcript facet by facet: durable state, attempt charge, custody
fields, evidence preservation into the terminal record, the exact report
lines of both terminals (including the poison demotion), the bounded retry
backoff, and token-consumption idempotency. Each cell was cross-verified
against the live boundary when the band was generated.
`tests/unit/test_decode_payload_poison_custody.py` pins the load-bearing
cells by hand, driven through the real boundaries (a real `round(NaN)`
refuse, a real text-decode `UnicodeDecodeError` through the real
`PipelineWorker` fetch path, the scheduler over `MemoryStore`).

Failure-Class: FC-fetch-decode-valueerror-poison-walks-gpu-ladder-as-anonymous-per-attempt
