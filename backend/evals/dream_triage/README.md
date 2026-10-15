# Dream triage recall eval

`fixtures.json` contains 25 invented cases: 15 with one known defect (three per
schema class), including the exact canary content and Vietnamese speech with a
misspelled invented English brand; ten clean cases include Vietnamese speech,
distinct people/memories/tasks, a complete entity summary and a completed task.
Multi-record cases carry the evidence needed to establish the single defect.
No customer records, database reads or product mutations are involved.

`backend/scripts/dream_triage_eval.py` uses the production evidence projection,
Mount framing, Triage schema, `dream_transport.model_turn` and
`omi:auto:dream-triage`. It snapshots the previous prompt and compares it with the
current prompt. Cases run five times each, with four calls in flight by default.
The canary uses the real canary limits: a 16,000-token pass cap, 8,000-token
triage budget and 256 completion tokens. Other cases use the normal 24,000-token
pass cap, 12,000-token triage budget and 768 completion tokens.

A defect hit requires a cluster with the expected class containing every
expected target reference. Duplicate cases require both records in one cluster.
Unknown references are errors. Any cluster on a clean case is a false positive.
Errors are reported and stop the run; they cannot certify the targets. Success
requires all 125 trials, canary 5/5, at least 64/75 defect hits and at most 15/50
clean false positives. This eval measures screening, not downstream edits.

From the repository root, validate without model calls:

```sh
backend/.venv/bin/python backend/scripts/dream_triage_eval.py --check-fixtures
```

For live evaluation, select `dev-operator` with
`source ~/.local/bin/gcp-agent-env.sh dev-operator`. Use a dedicated kubeconfig
and explicitly select the `dev-omi-gke` cluster in `based-hardware-dev`; verify
the gateway's project/accounting identity and effective triage route before
opening a loopback tunnel:

```sh
kubectl -n dev-omi-backend port-forward svc/dev-omi-llm-gateway 19083:8080 --address 127.0.0.1
```

In a second terminal using the same dev identity, provide the existing dev
service token through `OMI_LLM_GATEWAY_SERVICE_TOKEN` without printing it. Then:

```sh
OMI_ENV_STAGE=dev OMI_LLM_GATEWAY_URL=http://127.0.0.1:19083 \
  backend/.venv/bin/python backend/scripts/dream_triage_eval.py --live \
  --output .agent-brief/eval-before-after.json
```

The script requires the dev project, dev stage, explicit loopback URL and service
authentication. The operator must verify the tunnel's destination; a loopback URL
alone does not establish that a gateway belongs to dev. Neither prod nor
`api.omi.me` is part of this procedure. The script writes numeric attempt results
and hashes, never evidence or provider error bodies. Output is checkpointed after
each repeat. A candidate that misses a target exits nonzero. Do not substitute
partial rounds or transport failures for a completed comparison.

## Recorded comparison

`results.json` records the 2026-10-10 dev comparison on gateway image
`gcr.io/based-hardware-dev/llm-gateway:15c8d64`, OpenAI `gpt-6-luna`,
`reasoning_effort: none`, no fallback. Both arms used the same fixture and route.

| Arm | Defect hits | Clean false positives | Canary hits | Errors |
| --- | --- | --- | --- | --- |
| Before | 62/75 | 3/50 | 4/5 | 0 |
| After | 70/75 | 1/50 | 5/5 | 0 |

The prompt alone meets the targets, so no lane change or low-effort experiment is
needed. The remaining five misses are all `entity_fact`: the model did not flag a
summary that omitted a fact elsewhere in the same entity record. This is a small
synthetic comparison, not an estimate of production recall; repeated trials of
one fixture are not independent examples. An initial tunnel outage produced only
connection failures and zero observed model usage; that incomplete run is excluded.

## Conversation quality extension

The current fixture has 29 cases (18 defects, 11 clean), adding empty English and
Vietnamese titles, clean bilingual speech, and another invented Vietnamese brand
misspelling. Five repeats now require 90 defect trials and 55 clean trials, with
the same recall/false-positive thresholds and five canary hits. Run `--arm after`
to evaluate the current prompt alone. `quality-results.json` records the
2026-10-11 dev run on image `efb0e31`: 84/90 defect hits, 12/55 clean false
positives, 5/5 canary hits, and zero errors. Both untitled cases and the Vietnamese
brand case hit 5/5; the new clean bilingual case had zero clusters in 5/5.
The other clean false positives are screening candidates, not applied edits.
