# JIT matched cost and quality evidence

This runbook defines a bounded, matched comparison between the released
desktop director and the JIT nano/full path. It does not enable a feature flag,
reset quota, or make a provider call. The fixture and driver remain a
prompt-only proxy until a parent-approved development run has trusted receipts.

## Zero-call preflight

Run from a clean checkout of the exact source that will serve the comparison.
The built agent runtime is the source of truth for the service/coordinator MCP
manifest and kernel policy; do not hand-copy a tool list or system prompt.

```sh
RUN_DIR="$(mktemp -d)"
npm --prefix desktop/macos/agent run build --silent

RUN_DIR="$RUN_DIR" node --input-type=module <<'JS'
import { writeFileSync } from "node:fs";
import {
  mcpToolDefinitionsForAdapter,
  OMI_TOOL_MANIFEST_DIGEST,
  OMI_TOOL_MANIFEST_VERSION,
} from "./desktop/macos/agent/dist/runtime/omi-tool-manifest.js";
import { kernelSystemPolicy } from "./desktop/macos/agent/dist/runtime/context-snapshot.js";

const context = {
  surfaceKind: "service",
  executionRole: "coordinator",
  onboarding: false,
  screenContext: false,
  jitKnowledgeToolsEnabled: true,
  jitProactivity: true,
};
const tools = mcpToolDefinitionsForAdapter("omi-tools-stdio", context);
const expectedJitTools = [
  "search_knowledge",
  "read_playbook",
  "search_historical_facts",
  "get_entity_timeline_tool",
];
if (JSON.stringify(tools.map((tool) => tool.name)) !== JSON.stringify(expectedJitTools)) {
  throw new Error("JIT proactivity must advertise exactly the four read-only retrieval tools");
}
writeFileSync(process.env.RUN_DIR + "/tool-manifest.json", JSON.stringify({
  adapter_id: "omi-tools-stdio",
  manifest_version: OMI_TOOL_MANIFEST_VERSION,
  manifest_digest: OMI_TOOL_MANIFEST_DIGEST,
  context,
  tools,
}) + "\n");
writeFileSync(process.env.RUN_DIR + "/kernel-system-prompt.txt", kernelSystemPolicy("service", "coordinator"));
JS

backend/.venv/bin/python backend/scripts/jit_cost_evidence_driver.py \
  --plan > "$RUN_DIR/plan.json"
backend/.venv/bin/python backend/scripts/jit_cost_evidence_driver.py \
  --preflight --plan-file "$RUN_DIR/plan.json" \
  --tool-manifest "$RUN_DIR/tool-manifest.json" \
  --kernel-system-prompt "$RUN_DIR/kernel-system-prompt.txt" \
  > "$RUN_DIR/preflight.json" || test "$?" -eq 2
```

The command is successful as a preflight when it emits valid JSON. A
`ready_for_runtime` result means all serialized route envelopes fit the
gateway's 32,768-byte guard and both source artifacts were supplied. A
`blocked` result is a stop. The current source-owned JIT projection advertises
exactly four read-only retrieval tools, but the actual serialized request may
still exceed the guard once the built kernel policy and tool schemas are
included. The driver must report the measured size rather than silently
dropping tools or claiming that a minimum-only body is the runtime request.

## Matched sample and receipts

The default fixture contains three synthetic cases and remains a prompt-only
proxy. A real producer-derived qualification is a separate, exactly two-case
sample: one already-completed planned JIT full turn and one already-completed
ambient JIT full turn. The pair plan records each turn's actual prompt and
admitted-evidence hashes from the QA agent database. It never launches another
JIT full turn to populate evidence; the unchanged daily budget allows at most
three full turns and three delivered notifications.

For each producer turn, hold its evidence bundle, evaluation time, timezone,
owner, and source SHA constant across any later replay observations. The JIT
gateway receipt has a separate `run_id` from `budget.executionID`; record that
as the JIT sidecar's `gateway_run_id` and never substitute it for a comparison
ID. The source projection contract below is the only accepted bridge to the
legacy/nano replays. Do not substitute the static fixture hashes.

`evidence_sha256` is produced by the Node agent runtime as the canonical JSON
hash of its persisted `admittedContextSnapshot` object. It is not a digest of
the Swift context bucket or its complete payload. The Swift
`JITProactivitySourceProjection` supplies exact prompt bytes and the
evaluation-time/timezone/context-ID tuple; Node binds that projection to its
own admitted snapshot and adds this hash. Keep the snapshot hash and Swift
bucket/context identifiers as separate provenance fields.

The serving desktop source must emit the dedicated run-input field
`jitCostEvidenceProjection` beside the same admitted snapshot; the JIT budget
remains in `metadata.jitBudget` for each qualified turn. The projection is
`omi.jit.proactivity.source_projection.v1` and contains the fixed QA owner,
budget execution ID, producer lane (`planned` or `ambient`), the admitted
evidence hash, evaluation time, timezone, context ID, and the exact evaluated
legacy `prompt` plus `uncached_prompt`, nano `prompt`, and full-turn `prompt`.
The legacy stage also identifies `projection_mode=director_baseline_v1`, the
two `ContextProactivityPromptBuilder` source builders, and the four disabled
baseline flags; nano and full identify their exact `JITProactivityPromptBuilder`
source builders. The consumer checks that full-turn bytes equal the admitted
producer prompt and keeps the source metadata in the content-free plan while
keeping all prompt bytes private. If the serving source does not emit this
object, the pair plan must remain blocked rather than reconstructing prompts
from a fixture.

Records from the pre-migration producer may contain the projection under
`metadata.jitCostEvidenceProjection`. The driver rejects that form by default;
an operator may use `--allow-legacy-private-metadata-projection` only with the
owner-only historical QA directory and database (`0700` and `0600`). The
dedicated run-input field always wins when both forms exist, and metadata is
never accepted as new source proof.

If those projections are available in the served build, export the private
prompt inputs before executing the matched legacy and nano endpoint operations
once per selected case. The executable export command is in the
“Executable capture from the approved QA run” section below, where
`QA_STATE_DIR`, `PLANNED_AGENT_RUN_ID`, and `AMBIENT_AGENT_RUN_ID` are resolved.
Run that canonical command only after resolving those variables.

The export writes owner-only `planned/` and `ambient/` directories containing
`legacy.prompt`, `legacy.uncached_prompt`, `nano.prompt`, and the canonical
`evidence.json`. Standard output contains only paths, IDs, and hashes. Use the
exact files from each lane for the endpoint request and capture the response's
`X-Omi-Request-ID`; never copy prompt text into a receipt or sidecar.

1. Exercise the released legacy reasoning operation once through
   `POST /v1/desktop/proactivity/completions`.
2. Exercise the nano triage operation once through the same endpoint. Nano is
   an admission stage, not evidence of a saved notification.
3. Use the corresponding already-completed planned or ambient JIT full turn
   recorded by the producer-derived pair plan. Do not launch another full turn
   solely for this comparison. The shipped `AgentClient`/Pi path records the
   actual provider attempt IDs and durable gateway accounting.

The matched qualification may contain a separately replayed nano request plus
one already-observed JIT full turn. When the producer-derived plan contains its
content-free `nano_billing.request_id`, capture the original nano response with
the `--capture-agent-run` mode, which emits an actual producer observation from
the validated private run input; no synthetic headers are needed. The driver
stores this accounting under `actual_jit_nano_provider_receipts` and
excludes any separately replayed nano from the actual architecture-cost field
for that case. If the
producer nano was observed but its durable accounting is absent, the comparison
blocks rather than treating replay nano as total JIT spend. When nano was
observed, a total JIT architecture cost requires its trusted actual receipt and
the observed full-turn gateway receipt, with every attempt joined to its run
ID. A source-owned `not_dispatched` nano requires no nano receipt and leaves
the full-turn receipt as the actual JIT nano contribution of zero.
The summary's `cost_micro_usd` includes every unique paid attempt in the
experiment, including diagnostic replay nano calls, for the USD 5 cap;
`actual_jit_architecture_cost_micro_usd` excludes replay nano and covers the
observed producer nano plus JIT full turns. A source-owned `not_dispatched`
nano proves zero actual nano calls for that case; any replay is optional
diagnostic evidence and is still included only in total experiment spend.

The endpoint response for steps 1 and 2 is insufficient for billing. The
released `ProactiveLaneClient` envelope contains `operation`, `lane`,
`provider_model`, `usage.cached_tokens`, `usage.cache_write_tokens`,
`cache_write`, and `fallback_class`; it does not contain an attempt ID,
invocation ID, served model version, rate-card ID, cost status, or cost. The
desktop route returns the backend-generated `X-Omi-Request-ID` response header;
record it as a content-free request observation. Export the matching durable
`llm_gateway_attempts` `AccountingEvent` rows and join by that exact
`request_id`, retaining every `invocation_id`/`attempt_id`. Timestamp/user
correlation is not an acceptable substitute. If an error response has no
request-ID header, stop: its accounting cannot be joined safely and must remain
unknown until the error response carries the same correlation header.

For the JIT full turn, the immutable `llm_gateway_attempts` rows are the
receipt source. The gateway's response header or terminal SSE frame is useful
for transport diagnostics, but Pi's temporary receipt side channel is removed
when the adapter turn ends. Rebuild `jit-gateway-receipt-v1` from the durable
rows by exact `jit_run_id` before capture. Its attempt entries are the authority
for provider, configured and actual model, rate card, normalized uncached
input, cached input, cache writes, output, reasoning tokens, usage status, cost
status, and estimated cost. Keep the content-free sidecar that joins every
attempt ID to the case, route, evidence hash, prompt hash, run ID, and lane.
Count every provider attempt; one full turn may contain retries and failed
attempts, so `attempt_ids` and `provider_attempts_exact` cannot be collapsed to
one completion. The local SQLite tool ledger is one row per tool invocation;
the capture reports that as `tool_invocations` and does not infer model rounds.

First join the endpoint observations to the durable rows. The raw file must
contain `request_observations` (one object per legacy or nano operation) and a
prompt-free `llm_gateway_attempts` export. Each observation carries `case_id`,
`architecture`, `stage`, `request_id`, `run_id`, `evidence_sha256`,
`prompt_sha256`, `gateway_lane`, `tool_rounds`, and `receipt_origin` (`replay`
by default, or `actual` for the producer nano); the request ID is copied
verbatim from `X-Omi-Request-ID`.

```sh
backend/.venv/bin/python backend/scripts/jit_cost_evidence_driver.py \
  --join-receipts "$RUN_DIR/raw-receipts.json" \
  --plan-file "$RUN_DIR/plan.json" > "$RUN_DIR/receipts.json"
backend/.venv/bin/python backend/scripts/jit_cost_evidence_driver.py \
  --validate-receipts "$RUN_DIR/receipts.json" \
  --plan-file "$RUN_DIR/plan.json" > "$RUN_DIR/summary.json"
```

For a JIT full sidecar, also carry `gateway_run_id` from the budget execution
that appears in `jit-gateway-receipt-v1`. This keeps one stable comparison ID
for the matched case while validating the exact gateway execution identity.
The join selects only exact request IDs, retains all durable retry attempts,
and emits no unapproved ledger fields. It fails closed when an observation is
missing, duplicated, has no exact durable event, or attempts to use a full-turn
route. Feed only the resulting sanitized receipt envelope and sidecars to
`--validate-receipts`. The validator blocks on missing route coverage, an
unknown/aggregate-only/zero-placeholder cost, missing attempt attribution,
hash mismatch, or a total above USD 5.00. Do not claim nano savings when its
durable accounting event is absent: the endpoint's cached/model fields are
observability hints, not a cost receipt.

## Interpretation

The fixture hashes and serialized sizes prove source materialization and
request-bound feasibility only. They do not prove model quality, notification
precision, architecture savings, or retention impact. Parent review must
adjudicate output grounding and silence decisions after receipts are complete.
Keep the unchanged caps at 3 notifications/day, 8 nano triage calls/day, 3
full turns/day, and 1 full turn per candidate. Stop before the next call when
the next reservation could exceed the USD 5.00 run cap or when any receipt is
unknown. No production flags, quota resets, or response injection are part of
this experiment.

## Executable capture from the approved QA run

The capture modes below consume artifacts from an already completed,
parent-approved QA run. They make no provider calls. Every output envelope is
written with mode `0600` and contains hashes and opaque IDs only; keep the raw
prompt/evidence files private and outside Git.

Resolve the agent state directory from the exact QA bundle/runtime
configuration used to launch the run. Do not use another bundle's default
agent state. `AgentRuntimeProcess.defaultStateDirectory()` for the shipped QA
bundle resolves to
`~/Library/Application Support/Omi/AgentRuntime/com.omi.omi-jit-qa/omi-agentd.sqlite3`;
the driver accepts only that bundle-scoped database name, opens it with
SQLite `mode=ro`, and starts one read-only snapshot transaction for the run and
tool-ledger reads. The Firestore database used by the separate exporter is
named `jit-qa`.
This preserves WAL-backed rows without using SQLite `immutable=1`, which can
miss a live WAL. For example:

```sh
umask 077
QA_STATE_DIR="<resolved QA bundle state directory ending in /com.omi.omi-jit-qa>"
test "$(basename "$QA_STATE_DIR")" = com.omi.omi-jit-qa
test -f "$QA_STATE_DIR/omi-agentd.sqlite3"

# Derive one plan from these exact two producer turns. The lane labels are
# explicit because the current SQLite schema has no first-class proactivity
# lane column; when a future producer persists one, the driver checks that it
# agrees with this join.
backend/.venv/bin/python backend/scripts/jit_cost_evidence_driver.py \
  --producer-derived-plan \
  --producer-run "planned=$PLANNED_AGENT_RUN_ID" \
  --producer-run "ambient=$AMBIENT_AGENT_RUN_ID" \
  --agent-db "$QA_STATE_DIR/omi-agentd.sqlite3" \
  > "$RUN_DIR/producer-plan.json"

PLANNED_GATEWAY_EXECUTION_ID="$(jq -er '.producer_runs[] | select(.producer_lane == "planned") | .gateway_run_id' "$RUN_DIR/producer-plan.json")"
AMBIENT_GATEWAY_EXECUTION_ID="$(jq -er '.producer_runs[] | select(.producer_lane == "ambient") | .gateway_run_id' "$RUN_DIR/producer-plan.json")"
QA_OWNER_UID="vi7SA9ckQCe4ccobWNxlbdcNdC23"

# Export each exact budget execution from durable Firestore accounting before
# capture. These are reads only; the execution IDs come from producer-plan.json.
for lane in planned ambient; do
  case "$lane" in
    planned) execution_id="$PLANNED_GATEWAY_EXECUTION_ID"; agent_run_id="$PLANNED_AGENT_RUN_ID" ;;
    ambient) execution_id="$AMBIENT_GATEWAY_EXECUTION_ID"; agent_run_id="$AMBIENT_AGENT_RUN_ID" ;;
  esac
  FIRESTORE_DATABASE_ID=jit-qa OMI_JIT_QA_AUTH_ONLY=true OMI_ENV_STAGE=dev \
  GOOGLE_CLOUD_PROJECT=based-hardware-dev OMI_FIRESTORE_DATA_PLANE_PROJECT=based-hardware-dev \
  backend/.venv/bin/python backend/scripts/jit_cost_evidence_driver.py \
    --export-jit-receipt --execution-id "$execution_id" --owner-id "$QA_OWNER_UID" \
    > "$RUN_DIR/$lane-jit-gateway-receipt.json"
  backend/.venv/bin/python backend/scripts/jit_cost_evidence_driver.py \
    --capture-agent-run --plan-file "$RUN_DIR/producer-plan.json" \
    --case-id "$lane" --agent-db "$QA_STATE_DIR/omi-agentd.sqlite3" \
    --agent-run-id "$agent_run_id" --comparison-run-id "$COMPARISON_RUN_ID" \
    --gateway-receipt "$RUN_DIR/$lane-jit-gateway-receipt.json" \
    --output "$RUN_DIR/raw-receipts.json"
done
```

The producer-derived plan derives each prompt hash from `runs.input_json`, each
evidence hash from its admitted context snapshot, each budget execution ID from
`metadata.jitBudget.executionID`, and each provider-attempt count from the
producer's distinct receipt attempt IDs. When the source projection is present,
it validates the projection's evidence/time/context tuple against that run and
marks legacy/nano inputs `source_owned`; otherwise it reports baseline replay
unavailable and remains comparison-blocked. It reports the SQLite tool ledger
as `tool_invocations`; it does not invent model-round counts. It records runtime
context and system-prompt identity from run metadata without copying content.
The static fixture remains a separate prompt-only proxy.

Pi's `${contextFilePath}.receipts` side channel is removed when the adapter
turn ends and is not a receipt source. The export loop above reads
`llm_gateway_attempts` by exact `jit_run_id`, checks the fixed QA owner and
`jit-cloud-qa-v1` contract, preserves every retry attempt, and rebuilds the
aggregate without converting unknown usage or cost to zero. The subsequent
producer capture checks each receipt's run ID, contract, and attempt IDs
against the corresponding producer result.

For a legacy or nano endpoint, save the response headers with `curl -D`, and
save the exact source-owned evidence JSON and prompt used for that request in
private files. The request ID must come from the response itself:

```sh
backend/.venv/bin/python backend/scripts/jit_cost_evidence_driver.py \
  --capture-endpoint --plan-file "$RUN_DIR/plan.json" \
  --case-id "$CASE_ID" --comparison-run-id "$COMPARISON_RUN_ID" \
  --architecture legacy --stage full \
  --headers-file "$RUN_DIR/legacy.headers" \
  --evidence-file "$RUN_DIR/legacy.evidence.json" \
  --prompt-file "$RUN_DIR/legacy.prompt.txt" \
  --output "$RUN_DIR/raw-receipts.json"
```

Repeat with `--architecture jit --stage nano` for the nano operation. A
missing or duplicated `X-Omi-Request-ID` blocks the observation. Endpoint
captures are replay observations and keep the default
`--receipt-origin replay`; the actual producer nano observation comes from
`--capture-agent-run` as described above. Export its
durable accounting rows only from the named QA Firestore database, with the
fixed QA owner and explicit development project fence:

```sh
FIRESTORE_DATABASE_ID=jit-qa \
OMI_JIT_QA_AUTH_ONLY=true OMI_ENV_STAGE=dev \
GOOGLE_CLOUD_PROJECT=based-hardware-dev \
OMI_FIRESTORE_DATA_PLANE_PROJECT=based-hardware-dev \
backend/.venv/bin/python backend/scripts/jit_cost_evidence_driver.py \
  --export-attempts --owner-id "$QA_OWNER_UID" \
  --request-id "$LEGACY_REQUEST_ID" --request-id "$NANO_REQUEST_ID" \
  --output "$RUN_DIR/raw-receipts.json"
```

The exporter queries exact request IDs, checks the fixed owner, and strips
account content before appending rows. Join and validate the merged envelope
with the commands above. Missing durable attempts, unknown costs, mismatched
run IDs, or untrusted sidecars remain a hard stop; they are never represented
as zero.
