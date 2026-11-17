# Bound a refused source-protocol head without dropping its result

The 2026-11-16/17 incident let a protocol-2 sync result without a source marker
block every later result for its owner. #25597 teaches the current reader to
inherit the immutable job marker. This change adds a bounded failure path if a
reader still refuses that specific shape.

A canonical (not alias) protocol-2 source-reuse job with a source key,
source_reuse_version absent or 1, and neither source marker on its result gets a typed refusal only
after every immutable binding comparison passes. Other versions, explicit bad
markers, alias rows, binding corruption and privacy refusals keep their existing
stop/alert behavior. This includes the still-refused pre-marker residual (neither
job nor result has a marker); #25597 already admits the original incident shape.
There is no generic binding-mismatch bypass.

The first qualifying refusal stamps the existing projection_blocked_since and
projection_block_type fields. A later refusal at least 900 seconds after that
stamp takes the existing quarantine_held disposition. There is no attempt
counter: parallel replicas or multiple serving roles cannot consume an attempt
budget prematurely. Both serving and pump ticks default to 20 seconds (pump
clamps to 2–60 seconds; serving uses its discovery read budget). Fifteen minutes
provides about 45 normal retry opportunities, 15 at a 60-second tick. The bound
is evaluated on the next eligible walk/sweep; scheduling/discovery delay can add
time. It is measured from an observed refusal, not capture or commit age.

The hold transaction rereads the result, job, owner, ledger, source ownership
and privacy fences and checks the predecessor and age again. It cannot assign
text, claim source reuse, mark usage or acknowledge delivery. It writes an empty
quarantined receipt, marks job recovery_state=held, advances the owner watermark
and retains the immutable result and audio under existing held recovery policy.
It adds no TTL. The successful hold emits
omi_batch_projection_protocol_held_total{reason="missing_source_marker"}, one
structured protocol_head_bound log with reason/age and no identifiers, and the
shared degraded fallback event. Transaction retries/no-op replays do not count.
A held result remains delivery debt; ordering progress is not completion.

## Conversation order and recovery

Later segments may become visible first, leaving a temporary gap in transcript
coverage and temporarily incomplete derived notes. This is acceptable only for
this known canonical source shape. It changes visibility time, not capture order.
The held unit does not reserve a conversation ID. On recovery, ordinary sync
assignment resolves its current target (including redirects), applies normal
lineage, privacy and dedupe checks, rebases to the conversation timeline and
sorts merged segments by absolute capture timestamp. If the normal assignment
policy creates a separate conversation (for example a distant recording), that
policy still owns placement; recovery does not force unrelated rows together.

The existing held-release scan recognizes the hold reason. It waits until the
reader accepts the original source protocol; administrative quarantine/release
version fields alone cannot trigger release. Once readable, it uses the
existing pending reset and projection_redriven_at fence. The ordinary pending
sweep projects the retained result and follow-ups refresh derived content. Late
assignment never moves the owner's watermark backward. Existing release attempt,
operator-intent and privacy fences remain in force. The pre-marker residual
(no marker on either job or result) requires a later reader fix before either
automatic release or an operator redrive can succeed. This PR does not teach
the current reader to assign that unproven format. Once a compatible reader
understands the retained result, existing release/redrive tooling applies;
operator=True and administrative version stamps alone do not confer support.
No result bytes are edited to recover it.

A duplicate canonical upload may claim the same source range while the original
is held. Release checks that source owner in the reset transaction and keeps a
conflicting row held, including when the claim's expiry timestamp is past. It
does not manufacture ownership or reset the row to an endlessly refused pending
assignment. A compatible reader and the ordinary source/identity/privacy fences
must all permit recovery; a source conflict needs reviewed resolution. The
owner's later chain and the retained result/audio remain intact meanwhile.
Assignment still rechecks ownership: a new competing claim after the reset can
refuse late assignment and require reviewed resolution. This change never
relaxes that fence or promises delivery through a later privacy/ownership block.

## Control and verification

BATCH_PIPELINE_PROJECTION_PROTOCOL_HEAD_BOUND_ENABLED defaults on. Set false to
restore indefinite blocking for newly refused heads; unset restores the bound.
Turning it off does not undo committed holds or move watermarks backward.
No production setting, data, index or deployment is changed by this PR.

The regression restores the pre-#25597 reader policy on real prepare/assignment
transactions, with a missing-marker head and two successors. It verifies the
900-second boundary, successor progress, retained debt/audio, no source claim,
exactly one metric/log, refusal to release before reader support, then recovery
into capture order with an unchanged tail watermark. Negative cases cover the
kill switch, other protocol/binding failures, changed fences at disposition and
a stale reader-fix race. StrictFirestore enforces transaction read-before-write;
this is hermetic source behavior, not deployed/runtime acceptance.

PR #25617 owns blocked-head/outcome alerting. Its projection_drain.py,
projection_walk_stop.py and metrics.py lines are untouched; this PR adds only the
disposition metric and retains the existing blocked stop token. No alert is
added or duplicated.
