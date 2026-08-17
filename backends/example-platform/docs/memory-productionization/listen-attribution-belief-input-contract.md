# Listen attribution-belief input contract

Status: implemented, inert, shadow-only

## Purpose

Finalized Listen captures contain an `is_user` observation that is useful but
noisy. This adapter converts that observation into the modality-neutral
probabilistic attribution input. It never turns the bit, channel label,
first-person language, or transcript rendering into typed owner authority.

## Mapping

The adapter consumes an exact finalized formation snapshot. It requires active
target evidence, event membership in the exact finalized capture, matching
event-payload and evidence source identities, the expected producer-null
source-local channel, the capture-derived independence key, and a boolean
`observed_is_user` value. No caller-supplied owner identity or independence
group is trusted.

It emits one initial source-identity belief input per observed source-local
channel. Each input contains owner, source-local, and unknown hypotheses.
`observed_is_user=true` supports the owner hypothesis;
`observed_is_user=false` supports the source-local hypothesis and counters the
owner hypothesis. `diarization:weak` counters owner attribution. These are
directional factors only: no probability or threshold is selected here.

All factors derived from the same finalized capture share one
capture-derived independence-group reference. Multiple segments on one channel
are aggregated into one observation but remain dependent, preventing repeated
transcript fragments from masquerading as independent confirmation. Original
transcript text is represented only by an exact content digest and never
appears in the belief input or calibrator request. `graph_frontier` is a
derived digest binding the formation work and graph coordinates, not a numeric
graph-head claim.

## Boundaries

The result is accepted only by the isolated attribution-belief shadow
producer. The adapter creates no canonical belief, identity authorization,
entity binding, subject tier, promotion result, route, worker loop, model
default, threshold, or product wording. Cross-session correlation, voice
similarity, corrections, OCR/image factors, and prior-revision aggregation are
future versioned adapters over the same modality-neutral kernel.
