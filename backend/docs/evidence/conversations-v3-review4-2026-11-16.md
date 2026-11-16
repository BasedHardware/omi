# Conversations v3 — round 4 personal context

Repository BasedHardware/omi, branch lane/conversations-v3, parent 60ecfe76fbd.
Local synthetic work only. No GCP tier, production access, private data, push,
PR, merge, deployment or external runtime flag/config change.

## Decisions and implementation

- R4-1: Every v3 summary reaching the notes seam gathers the existing
  `composer_context.gather` account pack. Its existing eight-second deadline,
  read budgets, relevance/quality filters and fail-empty behavior remain the
  authority. Profile, active goals, transcript-bound people and ranked memories
  render through `meeting_context_render`'s BACKGROUND CONTEXT block. Owner
  corrections survive. Short/hidden/already-covered rows do not gather a pack.
  The one-shot notes writer, streaming, gateway/metering, Flex-first background
  and Standard foreground paths are unchanged; no notes agent loop is restored.
  `meeting_context_override` previously accepted calendar metadata only; it now
  also accepts a pre-rendered text override, without treating it as calendar data.
- R4-2: One optional context gather per reconciliation, at most one second and
  53 documents (one profile, twenty already-bound people, thirty-two title
  candidates). Shared context executor has no queue; caller timeout discards late
  results. Bound speaker names are filtered again per stretch. Earlier titles
  use the owner's local calendar day (UTC fallback), exclude future/current
  rows and product-hidden/deleted/locked/private/merged/capture rows. The
  title-only query uses the existing single-field started_at index. No new
  composite index: the manifest remains 304 composites.
  `CONVERSATIONS_V3_OUTLINE_CONTEXT=off` is a default-on, code-local kill switch
  for the extra reads; it requires no config change to ship. No stage is moved.
- R4-3: Cache and paid-attempt identity hash the context version, transcript
  fingerprint and complete effective messages, including SYSTEM_PROMPT and
  preceding-conversation evidence. Identical effective input reuses the outline;
  a prompt, context or context-version change does not reuse a stale paid result.
- R4-4 (optional, omitted): `models/structured.py:Structured.Participant` has no
  person_id field. Adding it changes the shared notes output schema and generated
  clients for legacy/non-v3 writers too; storing an extra raw key alone loses it
  at typed reads. That exceeds the cheap planner-only linking scope. Existing
  authoritative person IDs remain on copied transcript segments; no speculative
  name-to-identity binding is introduced.

## Cost boundary

Actual o200k_base measurement on one deterministic synthetic greenhouse example:
**108 added summary input tokens**, **46 added outline input tokens**. These are
an example, not production averages, model quality results or latency estimates.
Hard caps including the added block's headings: **2,000 tokens per summary**
(profile/goals/people allocation 600; memory/background allocation 1,200 before
rendering) and **320 tokens per outline**. UTF-8 byte fallback is conservative.
There are zero added writer model turns. Existing composer retrieval/embedding
work is reused; this is not a claim of zero retrieval/vendor cost.

Context alone never schedules another summary. The existing late-audio rule
stays once-only, new nonduplicate speech >=100 words or 10%, within a day.
Keep the rollout churn spending criterion <=5%; existing first-write/rewrite
counters and metered gateway usage must verify it before expansion. No production
churn ratio or cost saving was measured here. The one-second outline read
allowance is why its separate reversible kill switch is provided.

## Explicit follow-ups outside this PR

- V3-MOMENT-MARKERS: generalized recording cut input plus third double-tap action.
- V3-SECTION-START-TIMES: per-section start times.
- REVIEW-BACKGROUND-FREE-TEXT: free-text background question kind in Review.
- Participant person-ID schema/linking can be considered separately with the
  shared notes schema owner; it is optional in this round.
- V3-BACKFILL-30D-PARTITIONS remains required before enabling the off backfill.

## Verification

Final commands, results and head receipt will be appended after completion.
Test inventory: conversations-v3-review4-tests.txt. Initial development run
caught fixture omissions (required structured/is_user and a UTC-day assumption);
these are corrected and not counted as passing evidence.

The required scope panel scope-20261116t133550-57fa returned no terminal answers
before its deadline. All three lanes were stopped. agentctl cancellation returned
cancel_owner_stale repeatedly; kernel-verified exact owned native process groups
and orphaned owner PIDs were terminated, then agentctl terminal state was collected.
No scope finding or independent SHIP review is claimed. Its disposable checkout
was removed by the panel collector; no unrelated checkout was touched.
