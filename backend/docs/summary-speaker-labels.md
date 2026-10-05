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
note, deletion, discard, lock, merge, incomplete processing, reused speaker keys
across scopes, duplicate claims, invalid evidence, conflicting introductions,
AI identities, and every existing assignment or manual positive/negative decision.
All bindings for a participant must pass. High confidence is an extraction
category, not an empirically calibrated probability.

The existing `named_speaker_prompts_allowed` gate runs before candidate admission
and person lookup. Free accounts can identify the owner; other humans require
paid eligibility. Manual routes keep their existing permissions. Owner identity
must agree with the authoritative roster, never an untrusted `is_user` value.

People resolve by a roster person link, normalized name, or retained alias.
Duplicate matches decline. Creation requires a roster-backed real name plus
high-confidence binding evidence, or a verified explicit introduction. The
bounded catalog reads at most 501 documents once per transaction attempt; a
catalog exceeding 500 people declines named assignments because uniqueness
cannot be established. Owner-only admission does not read this catalog.
People and labels commit atomically; encoding/model validation happens before
any writes. Labels store `speaker_match_source=summary_inferred`, public source
`auto`, and evidence/version metadata. Manual corrections clear inferred metadata.
The existing `person_id`/`is_user` display paths show names without a client change.

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
| 80 | 2 | 380 | 78 | 71 |
| 1,800 | 2 | 380 | 78 | 71 |
| 16,000 | 5 | 380 | 183 | 71 |

The schema/rules add a constant 380 input tokens; completion grows by roughly
35 tokens per additional participant, plus the owner object. This is several
dozen output tokens per human, rather than merely a few. Two evidence IDs and
multiple keys increase completion. The owner-wording rule is independent of
the flag and adds 71 input tokens to rich notes. Total added input for both
changes is 451 tokens when enabled. Disabled identity adds zero identity tokens.

Current `model_config.py` and generated gateway routes name OpenAI `gpt-6-luna`.
The source is `backend/llm_gateway/config/cost_rate_cards.yaml`, card
`openai.gpt-6-luna.2026-09-22`: $0.10 input and $0.60 output per million tokens
(uncached short context). **These are provisional operator-directed rates,
pending official provider publication, not verified official list prices.**
Public pricing was not fetched because this lane is offline. Reprice the
formula against the official model list before rollout; the price-verification
requirement remains unverified.

At those provisional rates, identity alone costs **$0.0848–$0.1478 per 1,000
conversations**. Including wording costs **$0.0919–$0.1549 per 1,000**.
For enabled two-to-five-human conversations, monthly incremental model cost is
`N × (451 × input_price + completion_delta × output_price) / 1,000,000`.
If only some rich calls enable identity, use
`N_rich × 71 × input_price / 1,000,000 +
 N_enabled × (380 × input_price + completion_delta × output_price) / 1,000,000`.

The KB's existing 2026-09-21 free-tier local-processing economics record reports
19,918 macOS conversation events/30 days and explicitly calls that a volume
proxy, not a verified 1:1 stored-conversation count. Its desktop-source share
is 79.3%; free desktop enrichment was 72.5%. No current global eligible volume
or participant-count distribution was established. Assuming all 19,918 proxy
events were eligible enabled rich calls gives **$1.83–$3.09/month** for both
changes. An explicit 100,000 eligible calls/month assumption gives **$9.19–$15.49**.
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
