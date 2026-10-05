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
and `clients.get_llm` add no reasoning-effort override. The harness likewise sends
no `reasoning_effort`, `reasoning`, or temperature override. Reference/judge default
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
