# Verification

## Regression and behavior

The initial four transport-parametrized regressions failed against unmodified code: renewed refresh credentials were absent from storage after ordinary tool calls, including when the post-refresh tool retry failed. They now pass.

The implementation routes normal HTTP/SSE calls and the owner-only refresh-tools endpoint through one coordinator. A Firestore transaction claims a bounded lease; the owner saves renewed credentials transactionally before returning the access token for a tool retry. Completion checks the current credential fingerprint and lease owner, so a reconnect, deletion or successor lease fences a delayed response. Waiting callers reload the saved token. All I/O is async HTTP or the existing database executor. Cancellation leaves the in-flight owner fenced until its lease expires.

Discovery previously swallowed an unauthorized response and fell through to other transports, so explicit refresh never reached its recovery branch. Discovery and SSE POST now preserve that signal for the refresh owner.

## Completed checks

- Six hermetic unit files: **91 tests passed**, including 59 additional cases in the test expansion. Covers reconstructed and sibling tools, HTTP/SSE refresh and failed retry, persistence/provider failure, cancellation, bounded waiting, expired durable tokens behind stale cache, reconnect/delete/lease fencing, candidate URL carry-forward, redirect behavior, discovery/SSE authorization signals and owner-only endpoint behavior.
- Loopback Firestore emulator plus a real HTTP OAuth/MCP peer: **13 tests passed**, including five additional in-flight race and failure cases. Three subsequent reconstructed tool calls survive issuer-clock expiry beyond rotation grace. Eight concurrent calls produce one refresh and eight tool reads. Eight independent Firestore clients admit one refresh owner. Late writes lose to deletion, reconnection or lease takeover; rejected refresh executes no tool. The actual refresh endpoint discovers and saves tools across two rotations. The fake issuer clock advances deterministically; this is not elapsed production timing.
- Local socket HTTP smoke: a minimal Uvicorn app mounts the real apps router with a fixed synthetic auth dependency and the same disposable peer/emulator. `curl --fail-with-body --max-time 15 -X POST <loopback-refresh-url>` returned `{"tools_count":1,"tool_names":["check"]}`; the smoke verified saved rotated credentials and cleaned up its synthetic document. Production authentication and full backend startup are not claimed by this isolated smoke.
- Documented backend typecheck passed with **0 errors**. Existing unknown-type warnings remain.
- Final implementation preflight passed **34 checks**. The enforced pre-push gate passed, including async/import boundaries, runtime source closure, route/OpenAPI contracts, typechecking and selected new tests. Pure lifecycle contracts live in `models/mcp_client.py`, so database imports stay behind the database executor in async code.

Commands from repository root:

```sh
backend/.venv/bin/python -m pytest backend/tests/unit/test_mcp_client_credentials.py backend/tests/unit/test_mcp_client_token_persistence.py backend/tests/unit/test_mcp_client_refresh_transport.py backend/tests/unit/test_mcp_client_tool_refresh_route.py backend/tests/unit/test_mcp_token_refresh_contract.py backend/tests/unit/test_mcp_client_refresh_wire.py -q
FIRESTORE_EMULATOR_HOST=127.0.0.1:18485 GOOGLE_CLOUD_PROJECT=demo-omi-mcp-refresh PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/integration/test_mcp_client_refresh_firestore.py -q
PYRIGHT_PYTHON="$PWD/backend/.venv/bin/python" bash backend/scripts/typecheck.sh
OMI_PR_BODY_FILE=/path/to/pr-body.md make preflight
scripts/pr-preflight --pr-body-file /path/to/pr-body.md
```

Run the integration file only with a loopback Firestore emulator and synthetic demo project. It skips without one and never falls back to cloud credentials. New unit tests use the repository's strict Firestore fake, including its read-before-write constraint. No fake was extended to pretend to prove contention; that evidence uses the real emulator.

## Full-suite result, remaining gates and limits

- The canonical file-isolated runner completed **2,087 selected backend unit files**. The initial run had one failing file because this Mac lacked native Opus and ffprobe. Task-local Opus 1.6.1 and ffprobe 7.1.1 supplied those prerequisites; rerunning only that file through the canonical runner passed **all 38 tests**. The other 2,086 files passed initially. No product-code change was needed for the prerequisite rerun.
- Upstream GitHub workflow runs are `action_required` pending maintainer approval for the contribution fork. No hosted green result is claimed. Keep draft while checks remain unresolved.
- Existing PR #21991 addresses basic persistence/error handling. This contribution adds shared durable ownership, pre-retry persistence and cross-worker/reconnect fencing, and also covers explicit discovery refresh.
- A provider rotation and a database write cannot form one atomic transaction. A process crash after provider rotation but before durable save can still require reauthorization. The lease prevents an abandoned or delayed owner from overwriting its successor; it does not claim exactly-once execution across those two systems.
- A source PR does not establish deployed support. Production deployment and a subsequent released-client test are still required; no production accounts, credentials, requests or private user content were used by these local checks.

## Expanded adversarial coverage

The additional tests execute the same production client, coordinator, transaction helpers and refresh endpoint. Hermetic tests use pytest fixtures, the repository's strict Firestore transaction fixture, and `httpx.MockTransport` at the external HTTP boundary. They require no sockets or cloud services and are discovered by the existing backend unit selector. The real-emulator file remains supplementary integration evidence, as prescribed by the backend guide.

| Boundary | Additional behavioral proof |
| --- | --- |
| Durable storage | Exact lease expiry/takeover boundary; expired owner without a successor; removed/incomplete authorization; every reconnect binding; authoritative token expiry; detached returned credentials; per-app isolation; concurrent unrelated metadata preservation; fingerprint-safe release. |
| Refresh owner | Finite positive lifetime handling; absent rotation preserves refresh token and bindings; malformed success cannot replace stored credentials; cache invalidation failure preserves committed rotation and lets stale siblings reload; provider/release failure keeps the lease fenced without leaking provider data; waiters adopt saved credentials and cancellation cannot release another owner's lease. |
| HTTP and SSE wire | Actual form-encoded OAuth request and JSON-RPC/SSE exchanges; three rotating generations and preconstructed sibling tools; storage is inspected when the peer receives the tool request; invalid grant and failed save execute no fresh tool; in-band business error preserves rotation; valid-token happy path has no refresh transaction or cache write. |
| Real Firestore + HTTP | Provider response arrives after deletion, reconnection or successor takeover; explicit ASGI refresh/discovery races with a normal tool under one owner; real issuer rotation followed by storage failure does not execute the tool. |

Coverage 7.16.2 was installed only into a task-local tooling directory, without changing repository dependencies. The 91-case unit run measures **100% statements and branches** in the two new lifecycle owners: `database/mcp_client_credentials.py` (74 statements, 18 branch destinations) and `utils/mcp_token_refresh.py` (65 statements, 12 branch destinations). This is scoped module coverage, not whole-backend coverage.

Two deliberate mutations confirm the new assertions detect broken behavior:

- Omit the durable save before returning the new access token: both new HTTP/SSE reconstruction cases fail behaviorally (2 failures).
- Remove the expired-lease completion fence: both new expired-owner/no-successor cases fail behaviorally (2 failures).

Both source files were restored immediately in `finally` blocks; a subsequent source diff is empty, and the test expansion contains no production-source changes. These are mutation checks, not a claim to have run the entire new suite against the pre-implementation repository.

The full selector chose 2,090 backend unit files because changes to supplementary integration tests conservatively request the full unit suite. The canonical runner completed successfully (exit 0), including backend typechecking with 0 errors. All 34 repository preflight checks and all four metadata checks passed. Task-local Opus/ffprobe prerequisites were supplied from the earlier implementation verification. This current full-run evidence supersedes the historical 2,087-file run above; no audio prerequisite rerun was needed this time.

Optional coverage measurement (with `coverage==7.16.2` installed in a separate test-tooling directory/environment):

```sh
python -m coverage run --branch --source=database.mcp_client_credentials,utils.mcp_token_refresh -m pytest backend/tests/unit/test_mcp_client_credentials.py backend/tests/unit/test_mcp_client_token_persistence.py backend/tests/unit/test_mcp_client_refresh_transport.py backend/tests/unit/test_mcp_client_tool_refresh_route.py backend/tests/unit/test_mcp_token_refresh_contract.py backend/tests/unit/test_mcp_client_refresh_wire.py -q
python -m coverage report -m
```

Run from repository root with `PYTHONPATH=backend` and the locked backend environment. Coverage is optional measurement tooling; the tests do not require it. Temporary mutants were each run with the relevant new pytest selection, checked for ordinary assertion failures rather than collection/import errors, and restored before the normal/coverage/full runs.
