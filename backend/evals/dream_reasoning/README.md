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
