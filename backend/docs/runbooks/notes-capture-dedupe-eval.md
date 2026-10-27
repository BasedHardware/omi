# Notes capture dedupe: qualification before promotion

**Draft; not qualified to serve.** The rollout lead's 2026-10-27 ruling
(`4f6613`) separated this change from the L1/embedding release. The independent
`CONVERSATION_NOTES_CAPTURE_DEDUPE_ENABLED` flag defaults **off**. Only explicit
true/on/1/yes enables it; unset, unknown and false values retain the exact old
serialization. No production setting changes in this PR.

The candidate omits only the packet's top-level `capture_evidence` when it is
exactly equal to the full separately appended CAPTURE, before stripping or
normalizing either value. It copies the packet and preserves every other key,
the whole CAPTURE block, source IDs, speaker authority, tool schemas, output
language and task policy. Differing evidence remains independent. One-shot
notes is unchanged.

## Already demonstrated locally

`test_notes_capture_dedupe.py` reconstructs the complete old packet from the
retained evidence, including Unicode and nested/distinct fields, and verifies
the old bytes on default/off/unknown values. The invented weekly-sync tool
replay in `test_notes_agent.py` exercises the real notes writer with the switch
off and on. All content/policy output is compared; only the writer's per-run
task creation timestamp is excluded.

Those fixed-response tests do **not** establish generation parity. Repetition
can affect salience, attribution and which evidence the model selects even when
no information is removed. The following real-model gate is required.

## Synthetic dev-gateway evaluation

Owner: **rollout lead**; llmtrim supplies code, fixtures and the comparison
packet. Review the result by **2026-10-28 10:00Z**. The flag stays off and the
PR stays draft until this gate is accepted.

1. Pin the candidate Git SHA and the dev gateway's running artifact, resolved
   `omi:auto:conv-structure` route/model and all effective generation settings.
   Verify they match the intended production lane. Use an authorized dev-only
   service identity and invented owner IDs; no production account, user
   content, production lookup or signed-in `api.omi.me` request.
2. Use `tests/unit/fixtures/notes_agent/capture_dedupe_eval.json` plus the
   existing `weekly_sync_replay.json`. Every input and lookup answer is
   invented. Force packet-v2 serving locally for both arms, use the exact same
   packet, owner message, instructions, tools, model, limits and tool answers,
   and verify that the baseline seed actually contains two capture copies.
   Expand repeated lines with unique deterministic segment IDs. Supply only
   synthetic meeting-roster context and the fixture's explicit voice bindings;
   attendees must not resolve an unknown voice. Assert `plan_notes_agent.run`
   is true for every case in both arms, so an ineligible one-shot result cannot
   count as proof about this agent-seed change.
3. Arm A sets the switch false; arm B sets it true. Run each corpus case three
   times in interleaved A/B order through the actual model and production notes
   loop. Keep lookups on fixture-only adapters, including empty results for
   unlisted people/memories; screenshots are absent. Reject any attempt to call
   a production data tool. Do not replace generation with recorded responses.
4. Apply the existing notes output/identity/source/task validators, then score
   against the fixed expected facts and forbidden claims. Compare wording
   blind to arm where possible. Equivalent wording is allowed; decisions vs
   proposals, tense, numbers, dates, owner/unknown speaker distinctions,
   open-task suppression and segment provenance must remain correct. A
   missing required fact, invented commitment, false named-speaker binding or
   ungrounded source claim fails the candidate. The baseline must pass too;
   a baseline failure makes that case inconclusive rather than a candidate win.
5. Save synthetic prompts/outputs separately from an aggregate receipt with
   fixture digest, source/release/route identity, arm, sample, tool trace,
   validator results, expected-fact checks, adjudication, token/cache usage,
   finish reason, latency and actual vendor cost when reported. No provider
   result or price should be invented. Stop on truncation, budget overflow or
   a new correctness regression; keep this draft off.

The fixed corpus covers proposals vs decisions, unresolved voices, multilingual
evidence, existing tasks and explicit owner commitments, past-vs-future tense,
and long multi-topic capture. `repeat` changes length only; do not summarize or
truncate the capture. Add uncovered failures to the corpus before rerunning.
The lead owns the bounded dev-call spend and identity for this run; this lane
has neither an injected LLM API credential nor a grant to read secret payloads.

## Ramp and rollback after acceptance

The rollout lead records the accepted comparison, then enables the dev release
probe, followed by production 1%, 5%, 25% and 100% by **2026-10-29** using the
existing serving-cohort mechanism. Keep a complete matched observation window
at each state. No rise in notes/extraction errors, attribution failures or
gateway request p95 is allowed; inspect the fixture correctness readback too.
If the gate or ramp cannot finish by that date, report the blocker and renew
the dated promise; the switch remains off.

Set the flag false for exact old seed bytes, or roll back the image. No stored
data or successful notes are deleted or rewritten. The feature registry carries
the same default-off gate and dated ramp; a registry row does not enable it.

Content-free runtime counters:

- `omi_notes_agent_capture_seeds_total{outcome="removed|retained|no_duplicate"}`
  distinguishes removal, a disabled exact duplicate, and no duplicate.
- `omi_notes_agent_capture_characters_removed_total` counts raw characters
  removed once per seed, not every repeated agent turn or provider tokens.

Compare aggregate gateway tokens per eligible request before/after a qualified
train and reconcile with vendor usage. No dollar saving is booked for this
draft, and fixed-response replay is not a reason to skip the model gate.
