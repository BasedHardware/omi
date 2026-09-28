# Listen attribution blind-calibration sheet contract

Status: P6 implemented offline artifact contract; no product activation

## Purpose

This artifact turns the paired Listen attribution-belief experiment into one
fresh human truth task per exact source-channel observation. The grader sees
the ordered transcript and which segments form the target observation, but not
what the system thought the channel was or what either calibration strategy
predicted.

This is the truth-label input required for held-out calibration. It is not a
calibrator, threshold selector, authority record, product response, or release
decision. The builder and importer never self-grade speaker identity.

## Exact inputs

`buildListenAttributionBlindArtifacts` requires:

- a minted `memories.experiments.shadow` context for the exact owner and epoch;
- a parsed paired offline-replay cohort with at least two repeats;
- every runtime-verified result named by that cohort, exactly once;
- one exact stored Listen belief input and its accepted formation snapshot for
  every cohort unit; and
- a private 32-to-128-byte HMAC key copied during the call.

The builder rematerializes the full belief-input set from each snapshot and
checks the source snapshot, set, input, staging, copied-input, cohort,
assignment, result, belief, evidence-factor, observation, frontier,
calibration-contract, and receipt coordinates. A result cannot be paired with
different transcript context merely because its public shape is plausible.

This pure builder is not a source-of-record loader. Its caller must obtain the
stored input, accepted snapshot, cohort, and verified results through their
authoritative, authorized repositories and keep the artifact pair in trusted
offline custody. The self-consistency digests detect mixing or mutation; they
are not signatures that authenticate an attacker-created sheet/key pair. No
route or untrusted client may construct these inputs directly.

## Public sheet

`listen-attribution-blind-sheet-v1` contains:

- opaque HMAC-derived sheet and row references;
- the cohort digest and separate hidden-key digest;
- the complete ordered transcript context for each unique observation; and
- only an ordinal, exact text, and `target: boolean` for each segment.

It contains no account, owner identifier, system `observed_is_user` value,
source coordinate, formation/input/result reference, model, strategy, arm,
repeat, probability, hypothesis, factor, frontier, or answer key. Row order and
references are secret-randomized. The HMAC key is never persisted in either
artifact.

Marking target segments is necessary to state which source channel is being
graded, but it can focus the grader's attention. It conveys no system owner
guess; grader instructions and held-out sampling must still treat contextual
speaker attribution as potentially ambiguous.

The public sheet is deliberately sensitive because it contains transcript
text. It is an offline grader artifact subject to the same handling and
deletion obligations as the source transcript; it must never enter telemetry,
product memory, or the text-free experiment tables.

## Hidden key and labels

`listen-attribution-blind-key-v1` maps each public row to the exact stored input,
observation/content digest, and all baseline/candidate result references across
repeats. It contains no transcript text, probability, strategy, role, repeat,
or system channel bit.

David labels each public row exactly once:

- `owner`: the target speaker is the account owner;
- `non_owner`: the target speaker is not the account owner; or
- `unclear`: the supplied context is insufficient or genuinely ambiguous.

`expandListenAttributionBlindLabels` requires exact sheet/key digest agreement
and a complete unique label set. It preserves `unclear`; no code coerces it to
owner or non-owner. The output remains evaluation evidence and cannot mint
identity authority or change a memory.

## Guarantees and nonclaims

The artifact prevents arm/probability leakage through its defined fields and
binds labels back to exact paired results. It cannot make inherently ambiguous
audio certain, prove that transcript context contains enough truth, authenticate
the human grader, or select a probability threshold. Those are separate held-
out data, grading-session, statistical, and release gates.

There is no file writer, UI, route, model call, repository write, worker,
credential, threshold, expression band, canonical belief store, graph mutation,
promotion, retrieval/compose behavior, deployment, or cohort activation in
this unit.
