# Dream reasoning item validation eval

The fixture contains an invented robot spelling defect and two invented duplicate
contacts. The script uses the production Plan schema, prompt projection, Mount
framing and `dream_transport.model_turn` on `omi:auto:dream-reasoning`.
It supplies known synthetic clusters so all five calls reach reasoning. No
customer data, database reads or product effects are involved.

Validate locally:

```sh
backend/.venv/bin/python backend/scripts/dream_reasoning_eval.py --check-fixture
```

For live runs, follow `../dream_triage/README.md` to select `dev-operator`, create
a dedicated kubeconfig for `based-hardware-dev/dev-omi-gke`, verify the gateway's
ADC and accounting project, inspect the effective reasoning route, and tunnel
`dev-omi-backend/svc/dev-omi-llm-gateway` to loopback. Supply its existing service
authentication token through `OMI_LLM_GATEWAY_SERVICE_TOKEN` without printing it.
Then run:

```sh
OMI_ENV_STAGE=dev OMI_LLM_GATEWAY_URL=http://127.0.0.1:19083 \
  backend/.venv/bin/python backend/scripts/dream_reasoning_eval.py --live \
  --output backend/evals/dream_reasoning/results.json
```

Only dev with an explicit loopback tunnel is accepted. A loopback URL alone does
not prove the destination; the operator must verify it separately. No prod
endpoint or `api.omi.me` participates. Results checkpoint after each run and
contain hashes, numeric counts and sanitized validation locations only. A failure
stops the run; acceptance requires five successful runs, each retaining an edit.

The 2026-10-11 evaluation used gateway image
`gcr.io/based-hardware-dev/llm-gateway:b91fd34`, ADC/accounting project
`based-hardware-dev`, configured primary `gemini-2.5-flash` with reserved-only
capacity and configured fallback `gpt-6-luna`. These are route configuration
observations; the report does not attest which provider served each request.
All five runs retained two edits: 10 kept, 0 dropped, 0 validation errors by
any type, 0 failed runs, and 10,485 observed tokens. All other Plan lists were
empty. This small fixture confirms live transport compatibility; the invalid
item recovery contract is proved by deterministic mixed-item regressions.

## Conversation quality fixtures

`quality-fixtures.json` adds four invented cases: untitled English and Vietnamese
conversations, clean bilingual speech, and an explicit invented brand misspelling
inside Vietnamese speech. Each runs separately five times so the clean case
cannot inherit another case's defect. Use the same dev tunnel procedure above:

```sh
backend/.venv/bin/python backend/scripts/dream_reasoning_eval.py --check-fixture \
  --fixture backend/evals/dream_reasoning/quality-fixtures.json
# With the verified dev tunnel and existing service token:
backend/.venv/bin/python backend/scripts/dream_reasoning_eval.py --live \
  --fixture backend/evals/dream_reasoning/quality-fixtures.json \
  --output backend/evals/dream_reasoning/quality-results.json
```

The 2026-10-11 final five-repeat run used dev gateway image `efb0e31` with
verified dev ADC/accounting. Configured routes were reserved-only Gemini
`gemini-2.5-flash` with Luna fallback for reasoning, and `gpt-6-luna` with
`reasoning_effort: none` for triage. These are configuration observations;
provider identity per request was not attested.

| Case | Expected edit hits | Title proposals | Language feedback | Privacy rejects |
| --- | --- | --- | --- | --- |
| Untitled English | 5/5 | 5 | 0 | 0 |
| Untitled Vietnamese | 5/5 | 5 | 0 | 0 |
| Clean bilingual | clean 5/5 | 0 | 0 | 0 |
| Vietnamese brand misspelling | 5/5 | 0 | 0 | 0 |

There were no feedback items at all, no invalid items, and no transport errors;
observed usage was 42,503 tokens. The privacy metric conservatively counts all
privacy-gate rejections, including names and record IDs as well as quotes.
An initial prompt produced two unnecessary success reports (one privacy reject).
A follow-up prompt suppressed them but missed two Vietnamese titles and one
spelling edit. The final prompt explicitly requests supported empty-title and
spelling repairs. These earlier failures remain diagnostic evidence, not passing
runs. Five repeats of four small invented cases do not estimate production quality
or prove that arbitrary paraphrases can be detected by a lexical privacy gate.

## Deterministic guard regression fixtures

`guard-fixtures.json` adds independent near-empty untitled, good Markdown overview,
clean bilingual and sufficiently long empty-title cases. Five repeats exercise
post-model filtering with the same `utils/dream_guards.py` and feedback privacy
validation used before shadow persistence. Overview edits remain enabled for
empty fields only and require `## heading`, a blank line and `- ` bullets, matching
`render_sections_markdown` and the notes generator's body contract.

```sh
backend/.venv/bin/python backend/scripts/dream_reasoning_eval.py --check-fixture \
  --fixture backend/evals/dream_reasoning/guard-fixtures.json
# With the verified dev tunnel and existing service token:
backend/.venv/bin/python backend/scripts/dream_reasoning_eval.py --live \
  --fixture backend/evals/dream_reasoning/guard-fixtures.json \
  --output backend/evals/dream_reasoning/guard-results.json
```

Rows and totals include `raw_edits_by_kind`, post-guard `edits_by_kind`, fixed-reason
`rejected` counts, and existing `dropped_invalid`/`validation_errors`. The first
three cases require no edits; the bilingual case also requires no feedback. The
fourth requires a grounded title to verify useful output can still survive.
Schema item drops and policy rejections are counted separately. These invented
fixtures supplement deterministic regression tests; they do not estimate quality
on real conversations. Earlier receipts above predate the deterministic policy.
