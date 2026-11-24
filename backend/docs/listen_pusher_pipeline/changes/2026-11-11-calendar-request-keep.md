# Preserve explicit calendar requests before compute thinning

Synthetic instructions such as “Put my bike service on the calendar.” and
“Add the annual inspection to my calendar.” previously missed the reminder-only
keep exemption. A sub-12-English-word or sub-4-second capture could therefore
receive a deterministic minimum with empty overview/action items and skip
ordinary derived work. Both examples reproduce on the unmodified source.

One bounded segment-level keep helper now covers direct put-on-calendar and
add-content-to-calendar instructions, including polite requests. The short-clip
floor, deterministic relevance, content classification and minimum salience use
the same contract. New calendar matches never join speakers or segments. Tests
retain future-tense/past statements and calendar mentions as negative controls;
new candidates also pass the finite exclusion guard below. Existing reminders
and user/manual/privacy/media authority remain.

For the new calendar branch only, an otherwise matching bounded candidate with a
standalone `not`, `never`, `no`, `cannot`, `without`, `except`, `excluding`,
`avoid`/`avoiding`, `omit`/`omitting`, `instead of`/`rather than` (space or hyphen
separated), an `n't` contraction, or a cancellation
marker (`cancel`/`cancels`, `canceled`/`cancelled`, `canceling`/`cancelling`,
`cancellation`/`cancellations`) keeps the prior policy instead of gaining an
exemption. This conservatively declines ambiguous objects such as a cancelled
appointment. Candidate matching and marker detection share NFKC/apostrophe
normalization; word boundaries preserve names such as Notion, notebook and
notifications. The unchanged legacy reminder regex is evaluated first, including
its existing negated phrases, with either value of the new switch.
This is a finite conservative candidate-exclusion policy, not general natural
language understanding; ambiguous matching requests keep the prior policy.

This guard retains input for normal downstream adjudication. It neither creates
an event/action nor guarantees accepted extraction. The general floor and its
derived-work suppression remain for unprotected clips.

`EXPLICIT_CALENDAR_REQUEST_KEEP` defaults on. Set it to `false` (also off/0/no)
to restore the prior reminder-only exemption across all four consumers. This is
a **cost-cut reversal for protected cases**: affected fleet users/capture fraction,
extra model dollars/day and churn effect are unknown. Source flags/defaults do
not prove runtime exposure. There is no rollout or production change in this PR.

Verification uses synthetic commands, below-floor negative controls, explicit
rollback, existing authority/language contracts, and the real `_get_structured`
capture-end/recovery path with an offline sentinel at the notes-model boundary.
After deployment through the normal release owner, measure aggregate protected
request incidence, accepted-result yield and incremental model spend; preserve
cohort suppression and distinguish keep from accepted extraction.

Contract: [request preservation](../../listen_pusher_pipeline.mdx#explicit-calendar-request-preservation).
