# Labels inferred by the meeting-notes call

`SUMMARY_SPEAKER_LABELS_ENABLED` is a server environment switch, default off.
It belongs to the existing `runtime_env` authority, not PostHog or a user field.
This change neither declares an enabled deployment nor changes a running flag.

With rich notes and the switch enabled, the existing `conv_structure` call uses
`SpeakerLabeledExtraction`: participants and a separate owner supply numeric
speaker keys, high/medium/low confidence, and one or two source segment IDs.
No extra inference call is added. The existing presentation-repair path remains
bounded as before. A subclass keeps the disabled extraction schema unchanged.
Candidates and the roster survive presentation validation in private attributes;
they do not enter the saved note or the participant wire schema.

After the note commits, a separate Firestore transaction reloads the transcript,
manual receipt, and current labels. It refuses stale source text, a replaced
note, deletion, discard, lock, merge, incomplete processing, duplicate claims
on the same scoped key, invalid evidence, conflicting introductions,
AI identities, and every existing assignment or manual positive/negative decision.
All bindings for a participant must pass. High confidence is an extraction
category, not an empirically calibrated probability.

Every cited segment must belong to the bound numeric key and one shared
`speaker_id_scope`. The stage labels that key only within the cited scope,
including its uncited turns; it leaves other scopes reusing the number alone.
Separate independently evidenced bindings can identify different voices that
share a number across scopes. Conflicting introductions are checked throughout
the admitted scope. A complete explicit introduction must match the proposed
name: “My name is David Nguyen” is contrary evidence for “David”, even if the
model cites a different turn. Every explicit lead-in in a segment is checked;
a prior bare “I'm David” or matching explicit introduction cannot hide a later
contradictory one. One-letter apostrophe prefixes are extended across ASCII or
curly apostrophes before length validation. Contiguous surnames and internal
name particles (“Joan of Arc”, “Nguyen To Anh”) cannot be discarded or borrowed
from a later mention. Leading discourse words and ambiguous clause continuations
decline the binding rather than trimming or guessing a name boundary. Greetings
and discourse words anywhere in the span also decline. Once a name contains
two non-particle tokens, another particle may start an affiliation/location
phrase, so the whole span declines: “Eddie Thai of Google” and
“Joan of Arc of France” authorize neither creation nor a label. An ambiguous
span still counts as contrary evidence. This intentionally favors false
negatives over guessing, including complex real names with a later particle.
Latin
name tokens require capitals except internal particles; uncertain lowercase
spans decline. This scanner reuses main's explicit lead-ins and CJK validation
without changing the shared detector's other callers.

The existing `named_speaker_prompts_allowed` gate runs before candidate admission
and person lookup. Free accounts can identify the owner; other humans require
paid eligibility. Manual routes keep their existing permissions. Owner identity
must agree with the authoritative roster, never an untrusted `is_user` value.
Context may identify the owner without a literal introduction, preserving the
product's in-context naming intent. An existing `is_user` or
`speaker_identity_status=user` anywhere reserves owner identity; the stage does
not add another owner claim. Main's `speaker_identity_status=not_user` on the
candidate scope vetoes owner admission. `no_match` is a failed acoustic match,
not a confident non-owner signal; unknown/ambiguous states are not invented
negative evidence. Existing labels and manual decisions still take precedence.

People resolve by a roster person link, normalized name, or retained alias.
An alias must equal the entire proposed full real name;
a short alias such as “Ann” cannot assign “Anne Smith”. Exact equality with the
person's own normalized name remains eligible. Normalization folds straight
and curly apostrophes to the same character. Alias-only CJK matching requires
3–6 characters; a two-character alias such as “太郎” cannot assign “山田太郎”.
Exact equality with a person's full stored name remains eligible even when it
is two characters. Duplicate matches decline.
Contextual evidence can attach an existing exact-name person even when the
cited text never says the name and the roster lacks it. Context alone never
creates a person. Creation needs a verified full-name explicit introduction,
or a full real name from an actual calendar/call participant roster
plus the high-confidence binding. Main's system/macOS/Google/Outlook calendar
sources and corroborated `screen_activity` call rosters supply that authority;
background mentions and unsupported sources do not. A first-name-only explicit
introduction can attach an existing exact person, but cannot create one. The
same `full_real_name` predicate gates introductions, rosters, and aliases: two
or more space-separated tokens or a complete unspaced CJK name. Introductions
and actual participant rosters permit 2–6 characters; aliases use the stricter
minimum of three characters unless the full stored name matches exactly.
Thus a CJK alias can resolve the existing person instead of creating a duplicate.
The bounded catalog reads at most 501 documents once per transaction attempt; a
catalog exceeding 500 people declines named assignments because uniqueness
cannot be established. Owner-only admission does not read this catalog.
People and labels commit atomically; encoding/model validation happens before
any writes. Labels store `speaker_match_source=summary_inferred`, public source
`auto`, and evidence/scope/version metadata. Manual corrections clear inferred metadata.
The existing `person_id`/`is_user` display paths show names without a client change.

Hermetic transaction tests prove current-document admission and read-before-write
ordering. `StrictFirestore` does not model commit retries or transaction
contention; those behaviors are unverified and require the real dev/emulator
qualification below. The free-plan owner-plus-guest regression traps every
catalog read and create while checking that only the owner is labeled.

## Learning boundary

This stage never creates learning jobs, stores audio, or updates embeddings.
An inferred label grants no manual-receipt training authority. It improves the
person directory and this conversation's labels; it does not improve acoustic
recognition in later conversations by itself. A later explicit user confirmation
can use the existing guarded teaching path.

Automatic teaching would require a separately reviewed precision study over
independently labeled, multi-account conversations, sufficient pure voiced
speech, overlap/alignment verification, provenance-aware correction/revocation,
and a confidence threshold calibrated on held-out data. A model saying “high”
does not justify poisoning a reusable voiceprint.

## Offline cost experiment

Run through the normal test runner with an explicit file list:

```sh
printf '%s\n' tests/cost/test_summary_speaker_cost.py > /tmp/omi-summary-cost-files.txt
BACKEND_UNIT_TEST_FILE_LIST=/tmp/omi-summary-cost-files.txt \
  BACKEND_PYTEST_WORKERS=1 PYTEST_ADDOPTS=-s timeout 180 bash backend/test.sh
```

The experiment executes the real prefix and notes builders and parser, replacing
only the model response. It reads existing local `o200k_base` tokenizer data;
network remains blocked by the test harness. It fails if the data is absent;
do not fetch or edit caches to make it pass in an offline lane. It lives outside
the auto-selected unit roots so ordinary CI never depends on a tokenizer cache.
The behavior tests in `tests/unit/test_summary_speaker_notes_call.py` need no
real tokenizer and cover the same call/parser boundary.

2026-10-05 synthetic measurements (one high-confidence binding per human):

| Transcript words (target) | Humans including owner | Added identity prompt | Added fixture completion | Owner-wording prompt |
| ---: | ---: | ---: | ---: | ---: |
| 80 | 2 | 380 | 78 | 103 |
| 1,800 | 2 | 380 | 78 | 103 |
| 16,000 | 5 | 380 | 183 | 103 |

The schema/rules add a constant 380 input tokens; completion grows by roughly
35 tokens per additional participant, plus the owner object. This is several
dozen output tokens per human, rather than merely a few. Two evidence IDs and
multiple keys increase completion. The owner-wording rule is independent of
the flag and adds 103 input tokens to rich notes. Total added input for both
changes is 483 tokens when enabled. Disabled identity adds zero identity tokens.
The Round 1 wording scopes owner names to body prose, retains the title ban,
and explicitly preserves name-or-“they” phrasing for non-owners.

Current `model_config.py` and generated gateway routes name OpenAI `gpt-6-luna`.
The source is `backend/llm_gateway/config/cost_rate_cards.yaml`, card
`openai.gpt-6-luna.2026-09-22`: $0.10 input and $0.60 output per million tokens
(uncached short context). **These are provisional operator-directed rates,
pending official provider publication, not verified official list prices.**
Public pricing was not fetched because this lane is offline. Reprice the
formula against the official model list before rollout; the price-verification
requirement remains unverified.

At those provisional rates, identity alone costs **$0.0848–$0.1478 per 1,000
conversations**. Including wording costs **$0.0951–$0.1581 per 1,000**.
For enabled two-to-five-human conversations, monthly incremental model cost is
`N × (483 × input_price + completion_delta × output_price) / 1,000,000`.
If only some rich calls enable identity, use
`N_rich × 103 × input_price / 1,000,000 +
 N_enabled × (380 × input_price + completion_delta × output_price) / 1,000,000`.

The KB's existing 2026-09-21 free-tier local-processing economics record reports
19,918 macOS conversation events/30 days and explicitly calls that a volume
proxy, not a verified 1:1 stored-conversation count. Its desktop-source share
is 79.3%; free desktop enrichment was 72.5%. No current global eligible volume
or participant-count distribution was established. Assuming all 19,918 proxy
events were eligible enabled rich calls gives **$1.89–$3.15/month** for both
changes. An explicit 100,000 eligible calls/month assumption gives **$9.51–$15.81**.
These are sensitivity examples, not a production bill forecast.

The historical conversation-size record reports median approximately 1,794
transcript tokens and p90 approximately 16,144; long transcripts need no added
second context window here. The three synthetic lengths demonstrate constant
prompt overhead without reading any customer transcript. `o200k_base` counts
are a tokenizer proxy, completion fixtures are authored rather than generated,
and actual provider usage/reasoning, output formatting, cache warm-up, and
precision remain unmeasured. No cache discount is assumed. Above the card's
provisional 272,000-token boundary, use $0.20/$0.90 instead; crossing that
boundary can reprice the entire request. Firestore catalog reads/transaction
retries are additional costs not included in the model estimate.

## Dev qualification before any production enablement

1. Keep production off. In a separately authorized dev change, add the switch
   to the processing hosts in `backend/deploy/runtime_env/_base.yaml` with an
   off baseline and enable only the selected dev overlay. Compose/render and
   validate using the runtime-env guide, then deploy through the existing path.
   Editing the generated flag registry does not enable anything.
2. Use consented dev recordings with independent ground-truth speaker labels:
   self-introductions, calendar/screen-only context, silent attendees, mixed
   remote channels, multiple keys, reconnect scopes, AI notetakers, conflicting
   names, existing manual labels/rejections, and free/paid accounts.
3. Measure person and owner precision separately, assignment coverage, false
   person creation, duplicate creation, refusal reasons, manual correction rate,
   transaction failures, added latency, and actual provider token/cost deltas.
   Inspect actual transcript and participant rendering on released clients.
   Preserve privacy: telemetry must contain counts/categories, not names/text/audio.
4. Require zero manual-authority or entitlement violations and independently
   reviewed precision with confidence intervals. Agree the precision threshold
   before examining results; the tests here do not establish it. Verify real
   Firestore transaction contention/rollback semantics in dev as well.
5. Review the evidence and official price before any separately authorized
   production overlay change. Turning the switch off stops future inference;
   it does not erase labels already stored. Correct existing mistakes through
   manual routes. Voiceprint teaching stays disabled in this implementation.
