# Episode-notes offline evaluation

All 16 cases are synthetic; names, text, dates and situations are invented.
`EvidenceBundle` / `EpisodeFixture` in `eval.py` are the fixture schema. Each
observation records an ID, nullable time/actor, content, sensitivity and source
reference. Visible chat messages are written evidence observed on screen.
Expected properties cover required content, prohibited claims, provenance, and
private tagging. Categories are eval strata, never runtime situation branches.

11 development cases may guide prompts. Five held-out cases (31%) are sealed:
**never tune a prompt using held-out generated notes or scores**. Run that split
only for a frozen candidate acceptance run. A revision after inspecting results
needs a new held-out cohort. Mechanical unit checks of schema/split integrity
are allowed; do not use their content to customize prompt rules.

Three calls per episode: candidate, independent all-evidence reference, judge.
The candidate uses the production episode static/volatile helpers and extraction
schema, with UTC dates and synthetic text evidence; image pixels and production
repair retries are not exercised by the eval call. Production retries have separate
fake-model unit coverage.
Neither generation call gets expectations. The judge sees evidence, reference,
candidate and expected properties; it must challenge the reference too.
Unsupported or wrong-provenance claims are hard faithfulness failures regardless
of informativeness. Gap is in [0,1]; count metrics include unsupported claims,
wrong provenance, missed sensitive tags, deterministic/judged vacuity and expected
property failures. Reports group by stratum and retain individual reasons.
Each stratum currently has one episode: no statistical-quality claim is possible.

Live invocation (from backend; no production account APIs or Google credentials):

```bash
EPISODE_EVAL_API_KEY=... EPISODE_EVAL_BASE_URL=https://openrouter.ai/api/v1 \
EPISODE_EVAL_MODEL=... .venv/bin/python -m testing.episode_notes.eval \
  --split dev --output /tmp/episode-notes-dev.json
```

No key/endpoint/model means an error before network use. Provider requests use
zero temperature, bounded output, a 60-second timeout and no retries. Reports
record model, split and prompt hashes. Each note has `candidate_cost` with provider
`prompt_tokens` / `completion_tokens` as input/output counts and request latency
in seconds (through response body read; excludes reference/judge calls). Missing
provider usage is null, never zero. Fake callbacks can return `LLMResult` with
fixed measurements. Compare matched model/split reports and prompt hashes for
episode versus baseline candidate runs; token counts include the additive claims.
The harness does not estimate production retrieval or retry costs. Keep generated outputs outside git.
Unit tests inject a fake LLM through `evaluate`; they verify mechanics, not
model quality. Run tests only through `backend/test.sh` with an explicit list.
Later acceptance should add independent judges, multiple cases per stratum,
model/version receipts and repeated runs to quantify judge variability.
