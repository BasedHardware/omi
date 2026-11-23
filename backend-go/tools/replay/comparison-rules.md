# Approved ordinary-sync comparison rules

Source: slice B diagnostic report attached to SCA-3887. David approved the rules below on
2026-11-23. Every rule has a positive executable check and a negative test. The diagnostic
keeps values in comparisons and emits only paths, kinds, labels, and bounded failure reasons.
Differences without a matching executable rule remain unlabelled.

## Protected payloads

The comparator decrypts both sides with the synthetic replay fixture key, using the owner ID
as the HKDF salt and the production `user-data-encryption` info string. It parses the resulting
JSON and compares the plaintext structures. A different nonce is allowed; failed authentication,
malformed compression, or different plaintext leaves the row unexplained.

| Field | Check |
| --- | --- |
| `conversation.transcript_segments` | Decrypt both sides and inflate the marked payload. Compare `text`, `start`, `end`, `speaker`, and `is_user`; absent `speaker` uses the model default `SPEAKER_00`. Ignore only known Python model defaults, including derived `speaker_id` and `speaker_identity_status`; Go must preserve every non-default field present in Python's stored segment. The value-free `$bytes` wrapper is decoded before comparison, and an already-decoded Go segment list is compared as plaintext. |
| `conversation.user_corrections` | Require a true compression marker and storage consistent with each side's protection level; decrypt/inflate both blobs and compare correction lists. |
| `conversation.home_display` | Decrypt both envelopes and compare card content. |
| `episodes/{id}.content` | Decrypt both envelopes and compare episode content. |
| `episodes/{id}.home_display` | Decrypt both envelopes and compare card content. |

## Episode attach memo

Differences in `episode_links/{cid}.attach_completed`, `.attach_finalized`, and
`.attach_revision` are by design only when each side's decrypted transcript reproduces its
`content_key`, `attach_revision == attach_completed == content_key`,
`attach_owner_id == episode_id`, and `attach_finalized` is null or equals `attach_completed`.
The harness emits only a boolean check result and a value-free failure code when a precondition
fails. Alternating engines do not reuse the other engine's memo because their re-encoded
transcript inputs can differ.

## Clocks

Each timestamp must preserve its field's wire type and fall inside that side's own
`[started_at, finished_at]` replay window. Scheduled post-finish writes may use the stated
five-second grace; TTLs are checked against their write anchor instead of the replay window.

| Field | Additional check |
| --- | --- |
| Conversation `updated_at`, `notes_written_at`, `terminal_family_at`, `title_changed_at` | Firestore timestamp; own replay window. |
| Conversation `summary_completed_at` | Numeric Unix seconds; own replay window. |
| `episodes/{id}.compose_deferred_at`, `created_at`, `title_changed_at` | Firestore timestamp; `created_at` alone permits up to 5 seconds after finish for the scheduled episode write. |
| `goals/{id}.updated_at` | Firestore timestamp; own replay window. |
| `goals/{id}/goal_history/{day}.recorded_at` | Firestore timestamp; `date` and document day must match the timestamp's UTC day. |
| `llm_usage/{day}.last_updated` | Firestore timestamp; bucket day must match the timestamp's UTC day. |
| `hourly_usage/{day[-HH]}.last_updated` | Firestore timestamp; bucket day must match the timestamp's UTC day (with an optional valid hour suffix) and allow up to five seconds for the scheduled post-finish usage write. |
| `memory_state/apply_control.updated_at` | Firestore timestamp; own replay window. |
| `memory_state/head.updated_at`, `memory_outbox/{id}.available_at`, `memory_commits/{id}.updated_at`, `memory_operations/{id}.created_at` and `.updated_at` | Firestore timestamp; own replay window. |
| `memory_items/{id}.captured_at`, `.updated_at`, `.valid_from` | Firestore timestamp; own replay window. |
| `memory_items/{id}.expires_at` | TTL timestamp after the item's write and within five seconds of `captured_at + 30 days`; it is not constrained to the replay window. |
| `memory_source_replacements/{id}.committed_at`, `.control_state.updated_at` | Firestore timestamp; own replay window. |
| `episode_links/{id}.updated_at` | Firestore timestamp; up to 5 seconds after finish for the scheduled link write. |
| `episode_segment_receipts/{id}.updated_at`, `conversations/{id}/analytics_markers/{marker}.created_at` | Firestore timestamp; own replay window. |

Malformed, missing, or out-of-window values add `invalid_clock` evidence and cannot justify a
timestamp difference. The five-second allowance is limited to episode creation and episode-link
writes; it is not applied to conversation or memory clocks.

## Generated IDs and tokens

IDs may differ only after each side binds them to its own write or queue job.

| Field | Check |
| --- | --- |
| Admitted job and fanout IDs | Validate each side's IDs against its own queue job and stored row. Do not compare IDs across engines; ordinary-sync Python has no Go admission. |
| `finalization_engine`, `finalization_owner_epoch`, `finalization_revision` | Go values must be present and bind to its admitted job, owner epoch, and revision. The Python row must not contain these Go fence fields. |
| `go_sync_minimum_discarded`, `go_sync_minimum_revision` | Go receipt fields must be present together, use the expected types, and bind to the Go row's sync content revision and discarded outcome. The Python row must not contain them. |
| Home version fields and `home_feed_control.generation` | Existing UUIDv4 checks require a fresh, seeded-value-free, side-unique token with its same-side Home receipt or preparation link. |
| `memory_state/released_memory_changes_v1.token` | Require a fresh UUIDv4 value, absent from seeded values, unique on that side, and stored in the matching owner's state document. |
| Goal event ID and path | Each event ID matches its path, parent goal and latest progress sequence; semantic payloads are compared after removing only the independently checked ID and timestamp. |
| `batch_pipeline_privacy/{sha256(uid)}.memo_token` and `.memo_schema` | Both sides must have a fresh Python-format UUIDv4 hex token absent from seeded values, matching memo schema, generation/account_epoch/purging/blocked/memo_blocked equal to each side's seed and to the other side, and exactly one measured document write with zero reads and deletes per finalization. |

`invalid_token_binding` rows include a per-slot `failure_reason` such as
`prepared_source_version_mismatch` or `home_dirty_receipt_missing`. The reason contains no token
value and does not label the difference by itself.

The `home_dirty_receipt_missing` reason remains unlabelled. The diagnostic records successful
`home_dirty` writes to the exact receipt document (`true`, `false`, or delete) per case and side;
the final-state difference still needs a lead ruling before it can become a comparison rule.

The ownership-fence, minimum-receipt, and fanout fields are checked from replay observations;
the reader audit found no app, API, or MCP response exposing those fields, and no Python query or
index depends on them. Internal lifecycle reads remain in place for fencing. The finalization job
pointer is the exception: the Go status route exposes it as `job_id`, so its row is a `go_gap`.
The value-free report emits no stored row values.

## Go gap and Python bug

`go_finalization_notes_input_hash` and `go_finalization_notes_output_hash` are `go_gap` on
SCA-3551: Go will write Python's notes keys instead. They are not approved as by design.
`conversation.finalization_job_id` is also `go_gap`: the Go status route resolves that pointer
and returns it as `job_id`, while the Go ID breaks Python's status lookup. The case-specific
SCA-3874 exception retains precedence for its unreadable-ciphertext case.

The only Python-bug exception is the unreadable-ciphertext case `unreadable-ciphertext-dead-letters`,
filed as SCA-3874. While Python still discards the conversation and Go fails closed, remaining
unexplained rows in that case receive `python_bug:SCA-3874`; independently verified by-design
rules and Go gaps keep their own labels. The reporter requires both statuses and the status,
discarded, and transcript sentinel differences, so it fails when Python's behavior is fixed or
the case changes.

The lead-approved pass-3 Go-gap groups from SCA-4012 are stored in
`approved-go-gaps-sca-4012.csv`. The reporter applies those path/field patterns only to current
unlabelled rows; existing by-design labels and the SCA-3874 case-specific exception retain
precedence. A `<document>` pattern covers differences under that document, and a field pattern
covers its nested leaf differences. The report's unexplained gate count is `go_gap + unlabelled`;
`python_bug:<issue>` exception rows are listed separately and excluded from that count.

All other differences keep `label: null` until a lead approves an executable comparison rule or
files a Python-bug issue with file-and-line evidence and a Done check.
