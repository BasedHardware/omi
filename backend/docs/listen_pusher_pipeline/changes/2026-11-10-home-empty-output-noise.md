# Home: empty-output blocks are noise regardless of title provenance

Fable audit class 10 (2026-11-10), relay-cl1 ruling f6502a.

A completed conversation whose `summary_blocked_reason` is
`empty_output_exhausted` or `empty_output_lifetime_exhausted`, and whose
structured summary has no overview or section body, now projects as
`home_step=noise` whatever its title provenance. A banked receipt
(`summary_output_present` or `summary_completed_at`) or a live
`summary_due_at` outranks a stale terminal reason, so a recovered or re-opened
row stays `ready`/`writing_notes` instead of disappearing. This is a list-read
presentation change only; it does not alter stored rows, processing, retry or
summary-debt state. Existing failure and curation precedence is unchanged.

The new `HOME_EMPTY_OUTPUT_NOISE` kill switch is on by default. Setting it to
`false`, `0`, `off` or `no` restores the previous `server_minimum`-only rule.
`HOME_STEP_PROJECTION=off` still omits the entire Home projection.

No Flutter change is needed. Current clients consume `home_step=noise`; the
client status/title fallback applies only to older servers without the field.
