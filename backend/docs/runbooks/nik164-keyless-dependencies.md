# nik-164 keyless dependency decisions

Source review for retiring the production Owner key. Production rollout and
acceptance belong to the orchestrator; these decisions grant no new IAM roles.

## X connector and Workspace

Follow [the X sync runbook](x-connector-sync-job.md). Its Firebase initialization
uses ADC and the job manifest supplies the runtime identity and customer project.
The X job has no Sheets/Drive client, file IDs or Google Workspace scopes. Do not
attribute Workspace service-account totals to it without independent evidence.
No sheet/folder ACL change is required by this source. The actual Workspace
consumer and its document IDs remain a separate retirement prerequisite.

If a separate Cloud Run Workspace consumer is established, use
`google.auth.default(scopes=[...])` with the exact API scopes its operations need,
then share each identified spreadsheet/folder with its runtime SA at the previous
consumer's role. Cloud Run's metadata credentials honor requested scopes; a
cloud-platform-only token does not authorize Sheets/Drive. A signed JWT or
service-account key is unnecessary for ordinary shared-file access. Workspace
ACLs and OAuth scopes are separate requirements; do not add domain-wide
delegation or Drive access to the X job speculatively.

References: [google-auth metadata credentials](https://google-auth.readthedocs.io/en/latest/_modules/google/auth/compute_engine/credentials.html),
[ADC selection](https://google-auth.readthedocs.io/en/latest/reference/google.auth.html).

## Direct Vertex candidates in the listen image

The listen image runs `main.py`, which includes the desktop and Dream routes.
Standalone pusher registers only the pusher/metrics routes. A Python HTTPX user
agent and the generic Vertex audit resource do not identify a particular Python
call site or pod.

| Path | Role and keyless decision |
| --- | --- |
| `routers/desktop_proxy.py::_refresh_reservations` → `utils/llm/vertex_reservation_probe.py::probe_reservation` | Optional, globally leased reservation discovery. It sends only the fixed synthetic `Reply OK.` prompt with dedicated capacity. It precedes the company-paid gateway dispatch for legacy Gemini model aliases. Let its direct Vertex attempt fail closed under the unprivileged listen identity. |
| `utils/dream_agent.py` / `utils/dream_harness_transport.py` → `utils/dream_capacity.py::available_model` / `_probe` | Optional capacity evidence, using the same synthetic probe. Model inference still goes through reserved-only gateway lanes. Let this direct attempt fail closed too. Missing evidence admits to gateway policy with existing degraded telemetry; it never authorizes a direct/shared model call. |
| `routers/desktop_proxy.py::_upstream` | The company-paid direct Vertex branch is unreachable: Omi-paid requests raise `routing_gateway_required`, and BYOK returns an AI Studio route before the Vertex block. No direct Vertex fallback is available after a gateway fault. |
| `utils/llm/providers.py::get_or_create_gemini_llm` | Legacy factory can construct a Vertex SDK client when `USE_VERTEX_AI=true` and `GOOGLE_CLOUD_PROJECT` is set. Managed `get_llm()` routes always use the gateway; Gemini BYOK has its own keyed AI Studio client. Do not turn the factory into a runtime IAM requirement. |
| `scripts/probe_gemini_thinking_contract.py` | Manual synthetic Vertex probe; not a listen/pusher entrypoint. Do not run it under either runtime SA or use it as a keyless acceptance gate. |

`VertexAccessTokenSupplier` explicitly requests cloud-platform-scoped ADC and
refreshes it off-loop. It does not parse `SERVICE_ACCOUNT_JSON`; ADC can select
the key file named by `GOOGLE_APPLICATION_CREDENTIALS` on a keyed listen pod.
Firebase's JSON parsing and customer-data credential selection are separate.
The SDK factory also relies on ambient Google credentials.

A Vertex HTTP 403 is `inconclusive`, never proof of reservation inactivity or
success. Token acquisition failures are also reduced to `inconclusive` by the
bounded background probe; Dream additionally records its failed-probe interval.
Neither probe retries with the retiring key, an API key, a different SA, or an
unrestricted model. Keep `pusher-runtime@` and `backend-listen-runtime@` without
Vertex roles. A future requirement for authoritative discovery belongs on the
gateway identity, with its shared-state deployment reviewed separately.

## Dormant repair job

`untitled-repair` is a manually provisioned Cloud Run wrapper around
`scripts/repair_recovery_dead_letter_untitled.py`, not a declared recurring job.
The script provides bounded dry-run/apply/resume/rollback and encrypted durable
repair artifacts; removing a stale job must preserve those artifacts and source.
There is no deployment workflow for this named job in the current tree.
Delete the dormant job after its owner verifies there is no active execution or
trigger. If retaining the template for audit is necessary, remove its credential
binding and label it retired; do not execute its old cohort after key retirement.
