# Episode-notes offline evaluation

The bundled default has 16 synthetic episodes (11 dev, five held_out). Private
sets with `synthetic: false` require an explicit `--fixtures PATH`; their report
and cache paths must be outside **every git worktree**, including through
symlinks. No real evidence belongs in git, tests, commit messages or reports in
this repository. Output/cache files are atomic and mode 0600. The loader schema
is in `schema.py`: typed observations, capture window, stratum, split and expected
properties. Retired source-tag metadata in older external fixtures is ignored and
never forwarded to prompts or reports. Optional diarization/invocation metadata must be server authored.

Held-out cases are sealed: never tune prompts using held-out generated notes or
scores. The CLI and runner require `--split held_out --frozen` acknowledgement.
A revision after inspecting acceptance results needs a fresh held-out cohort.
Mechanical fake tests use invented stand-ins, never the private fixture set.

Select `--arms episode baseline stored` (default: episode). All arms use identical
full evidence and expected properties, one independent reference per episode,
and the same judge. Expectations are never sent to generation or reference.
The judge must challenge the reference against the evidence. `stored` skips
candidate generation and maps the exact `fixture_id` field in each stored JSON
file to the bundle ID; filenames are conversation IDs, not fixture prefixes.
Retrieval/mapping metadata is stripped before scoring. Stored `sections_note`
markdown is preserved as a section body; `action_items_note` is also visible to
the judge. Original stored generation cost is unknown (null), not invented zero.

Candidate model is fixed to `openai/gpt-6-luna`. Production `conv_structure`
uses `LUNA_MODEL` with provider openai in `utils/llm/model_config.py`; route options
and `clients.get_llm` add no reasoning-effort override unless episode writer
configuration explicitly requests one. The gateway route still supplies its own
effort: the harness reads `conv_structure` in
`llm_gateway/config/generated_route_overrides.yaml` and applies it to candidate
Luna requests lacking an explicit override (currently low), including baseline
and C7. Explicit helper low and C6 xhigh are preserved. `--provider-default-effort`
opts out for historical non-parity experiments. Reference/judge receive no effort
or temperature override. Effective effort is stored per call, in report rows and
fresh-call receipts; it enters the candidate cache key before lookup. References
and explicit-effort candidates keep their shared identities. Reference/judge default
to `openai/gpt-6-sol`, configurable with `--reference-model` / `--judge-model` or
`EPISODE_EVAL_REFERENCE_MODEL` / `EPISODE_EVAL_JUDGE_MODEL`. Live use requires an
explicit key and HTTPS base URL. Requests default to a configurable 32000-token output cap (`--max-tokens`) and
300-second timeout (`--timeout`), with no transport retries. Each call records
`finish_reason`. Truncation, transport, JSON and judge-schema failures become
per-case/per-arm error rows; another case or arm continues. Reports separate
scored counts from attempted/error counts; paired scores include only successful
pairs. Failed calls are not cached, and resuming retries them while reusing
successful references/candidates/judges. Invalid old judge receipts are refreshed. CLI concurrency defaults to four (maximum eight).

The reference is cached next to the output (`OUTPUT.cache/`). Candidate and judge
responses are cached separately. Keys include model, exact prompt and payload;
reference keys exclude expected properties. Resume with the same command to reuse
completed requests, even after a later arm fails. Prompt/model/evidence changes
invalidate the applicable cache. Measurements on resumed rows are the original
request's usage/latency, not incremental spend for the resume. Keep this cache
private; it contains reference narratives and generated/scored notes derived from sensitive evidence.

Reports include every note and per-arm/per-stratum gap, unsupported claims, wrong
provenance, unrelated content claims, deterministic/judged vacuity, property
failures, token counts and latency. Provider usage absent from the response is
null. Cost aggregates include measured counts. Paired `episode_vs_baseline` and
`episode_vs_stored` compare the same episode IDs, overall and per stratum;
negative gap/error/vacuity/property deltas favor episode, while positive
faithfulness deltas favor episode. Judge variability and small strata still
require repeated acceptance runs before a quality claim.

Episode notes center the owner's episode and require an evidenced connection for
screen/background facts. The judge counts claims from evidence without an evidenced
connection to the episode across all visible fields, including source-supported
incidental content. `unrelated_content_claims` is reported per arm/stratum and in
paired comparisons; unsupported/wrong-provenance faithfulness metrics stay intact.
Sharing applies to the whole note; claims carry provenance without private markers. Names read on a
screen are shown/written; conclusions about absent evidence are inferred. Rich
person/pronoun/AI-agent rules also apply. Claims bind factual sentences/bullets
with short unique exact anchors; headings need no claims. The generation schema
omits server-authored source metadata; the backend fills it. Compact evidence
JSON preserves metadata and content while omitting unknown optional values.
Short prompt-local evidence aliases are restored before production validation
and offline judging. Reports retain original IDs; generation costs retain actual
provider usage. Optional candidate reasoning-token counts are recorded when supplied
by the provider; billed output counts always remain the provider completion total.

Both generation arms reuse production static/volatile helpers and schemas.
Baseline uses rich notes v2: `build_conversation_prompt_prefix`, normalized roster,
`rich_static_instructions`, `rich_volatile_instructions`,
`render_meeting_context_pack` and `digest_screen_rows`. Pure context construction
is separated from retrieval/cache-route imports; no Firestore/client module is
imported by the eval. Prompt text is not rewritten in the harness. The baseline
helpers retain the main/base prompt bytes, pinned by existing flag-off tests.

Approximations (recorded in every report):

- No image pixels, retrieval, repairs, task extraction, relevance gating or
  persistence. This measures one generation per arm, not production retry cost.
- English output, UTC dates; capture end stands in for generation time. Task
  intelligence capture is disabled. Open tasks remain contextual evidence.
- Flattened observations do not preserve raw calendar/roster fields. Explicit
  actors are normalized as roster names; raw calendar/roster descriptions go into
  meeting notes without inferring emails, organizations, title or attendance.
  Owner identity/catalog and desktop mixed-channel bindings cannot be recovered.
- Known actor labels define clusters; unnamed turns remain separately unresolved
  unless an explicit diarization key is supplied. Baseline emits compact source
  headers using source references/observation IDs. Wake-word metadata is used by
  episode mode; legacy baseline invocation markers are not reconstructed.
- Only supplied prior conversations are used: at most three, input order,
  300-character gists. Open tasks lack prior-conversation linkage. People facts,
  goals and memories absent from the bundle are not retrieved or invented.
- OCR uses the production 80-row/2500-character digest. Unstructured OCR lacks
  app/window metadata, so app-specific messaging exclusion cannot be reconstructed
  exactly. Typed `messages` become Messages rows; the production digest excludes
  their bodies. Screen moments retain supplied text (seven moments / 900 chars),
  without reconstructing missing frame offsets/roles. The production overall
  background cap remains 6000 characters.
- Flattened evidence may omit production admission/retrieval boundaries. Baseline
  treats supplied screen/prior context as already admitted; it does not simulate
  consent or calendar/roster matching against data outside the bundle.

From `backend/`, real dev comparison (David runs this; the agent does not):

```bash
EPISODE_EVAL_API_KEY="$(cat ~/.local/share/hostctl/secrets/david-experimental-openrouter-key)" \
EPISODE_EVAL_BASE_URL=https://openrouter.ai/api/v1 \
.venv/bin/python -m testing.episode_notes.eval \
  --fixtures "$HOME/.local/share/omi-meeting-notes-eval/episode/real-episodes.json" \
  --stored-notes "$HOME/.local/share/omi-meeting-notes-eval/episode/prod-notes" \
  --arms episode baseline stored --split dev --concurrency 4 \
  --output "$HOME/.local/share/omi-meeting-notes-eval/episode/round4-dev-report.json"
```

For a frozen acceptance run, change to `--split held_out --frozen` and a distinct
outside-worktree output filename. Never inspect that report to tune this prompt.
A single synthetic dev smoke can use `--episode-id launch-review --concurrency 1`.
Tests run only through `backend/test.sh` with an explicit file list; fake scores
prove harness mechanics, not note quality. No production account APIs or Google
credentials are needed or permitted by this harness.

Round-8 scale measurements add provider cached-token counts and an estimate of
claim-array tokens (o200k tokenizer, compact JSON). Output-token totals still
include billed reasoning; claim share is an estimate of visible metadata, not
its share of reasoning. Missing provider cache counts remain unknown.
Production uses a stable system-message cache breakpoint; this OpenRouter eval
uses ordinary system/user messages and measures provider automatic cache reads,
so cache behavior does not reproduce the internal explicit-cache route.
Episode compaction and extraction aliases are the production helpers; returned
claim aliases expand before judging. List/search omit claims; detail retains them.

For judge variance, copy reference and generated candidate receipts (not judge
receipts) into a second outside-worktree cache and run the same DEV comparison.
This fixes evidence/reference/candidates and resamples only the judge; it does
not measure generation variance. Never include held-out inputs in an iteration.

Round-9 configurations use `--selection compact|deterministic|model`,
`--no-claims`, and `--candidate-effort default|high|xhigh`. Only the writer's
Luna request receives the selected thinking effort; default inherits the gateway
policy in eval, while production sends no request override.
The optional Luna selector uses low effort, a 30-second deadline and the same
production large-input guard/fallback. It returns exact source IDs and short
connection reasons; the writer sees selected original evidence, not the reasons.
`--judge-samples 2` generates one candidate per arm then obtains two separately
cached judgments against the same reference. Effort/selection/claim mode enter
candidate cache identities; the selector's effort/deadline enter its own cache.
Reference/judge rules are unchanged, so their receipts can be shared across configs.

`candidate_cost` includes selection plus writing, while `writer_cost` and
`selection_cost` retain individual receipts. Reports include reasoning tokens
(a SUBSET of billed output, never add them twice) and USD `provider_cost` when
reported by the endpoint; unknown usage/cost stays null. A reused selector receipt
is charged to each configuration's hypothetical production note cost; it does not
claim a second actual API bill. Eval reference/judge spend is separate. Repeated
payload caching and OpenRouter routing do not predict production bills/latency.
The harness still omits production presentation/vacuity repairs; long-input and
remaining-time repair guards are tested with fakes, not a live production route.

The CLI retains historical `compact` + claims-on defaults for reproducible before
comparisons. To test the current tiered production defaults, pass
`--selection deterministic --no-claims --candidate-effort default --tiered --thinking-max-input-bytes 0`
explicitly. Eval otherwise permits 300s per writer call; use
`--apply-deadlines --writer-timeout 120 --c6-timeout 115` for the
durable tier comparison. Synchronous production paths retain C7/60s. A socket
timeout is not a hard total wall-clock limit. Record deadline exceedances
separately from eval errors before interpreting ramp readiness.

`--thinking-max-input-bytes` defaults to 0; positive values reuse the production byte
measurement and baseline routing before generation for high/xhigh inputs.
`0` disables this optional byte guard; it is also the current production default.
The existing long-transcript baseline guard remains independent. Baseline fallback
reuses baseline generation/judge cache keys when their exact inputs match, keeping
both samples comparable. Reports record `writer_arm` and `thinking_fallback`;
no unseen candidate is synthesized from scores. A cache-only replay must reject
every cache miss and must not be described as a new live generation or resampling.

Round 10 selector experiments use `--selection deterministic|jev|luna`
(`compact` remains the historical offline control), `--jev-threshold`, and
`--tiered`. Jev sends the production shared-state/typed-question shape to
`/systemone`, using the pinned `typesafe/jev-1.13` instead of the internal gateway
lane alias. Scores are cached independently of threshold/writer effort so a sweep
reuses decisions. Unknown SystemOne usage is reported as unknown, not zero; writer
and selector receipts remain separately available. Consecutive screen captures
are grouped only with observed app/window/time metadata. Flattened external
fixtures lacking that metadata cannot reproduce production segmentation.

The tier route uses admitted speech words/source kinds, never fixture strata or
IDs. `--tiered` composes fixed C6/C7 candidate/judge caches when requests match;
that is a policy replay, not evidence that a slow cached call completes under a
production deadline. Live deadline/fallback evaluation must record timeout cost
as indeterminate when the provider does not return usage. Outer serving limits,
legacy synchronous requests and inherited gateway effort defaults are audited in
`utils/conversations/EPISODE_DEADLINES.md`. Never run held-out inputs for calibration.

Round-11 DEV ablations are explicit `--experiment` modes, never production
settings: `verify`, `fact_check`, `facts_first`, `best_two`, `jev_veto`,
`jev_per_source`, `jev_per_source_pool`, `jev_rank`, `jev_discussed`, `jev_choice`,
and `jev_rank_verify` (rank followed by the same bounded verifier).
Use `--experiment-cutoff` for a selector/fact-check threshold (rank uses a
fraction of the existing deterministic pool). Every selector is removal-only;
the pool variant asks Jev only about already-admitted candidates. Existing
writer/reference/judge contracts remain unchanged. Experiments reject held-out,
even with `--frozen`; this is separate from the normal frozen acceptance CLI.

`--tier-min-words` / `--tier-min-source-kinds` parameterize offline routing.
`--candidate-max-tokens` caps C6 only, includes the cap in its request/cache key,
and preserves the one C7 fallback on truncation/timeout. It never caps baseline,
C7, reference or judge. This is a token budget, not a hard wall-clock deadline.
`--spend-log` appends content-free receipts only for **fresh endpoint calls**;
cache hits retain original cost for policy comparison but are not new spend.
Private spend-log/output/cache paths must all be outside git worktrees.

`policy_replay.py` produces routing summaries from cached C6/C7 and both judges;
no models are called. Keep a complete C6 candidate map: a previously unrouted
C7 row must not masquerade as a C6 candidate. Real fixtures expose capture times
and segment start timestamps, but not segment ends: timestamp span/capture span
are duration proxies, not measured active speech time. Selection-only sweeps
measure removals/input volume, not note quality. Best-of-two receipts report
summed call latency plus a separately marked **modeled parallel critical path**;
reusing an already cached first draft does not demonstrate production parallel
serving latency. Failed exact-quote extraction is a per-case error, not a valid
low-cost note; include errors rather than comparing only successful cases.
