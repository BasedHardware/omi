# C10: released-client replay

App core owns capture/decoders; CI and release owns admission/wiring. First builder
PR: two most recent **confirmed distributed build identities**, four GETs:
/v1/conversations, /v3/memories, /v2/messages, /v1/action-items. A marketing version
alone is insufficient (543+992 and 543+990 differ). Local mobile-cm tags are build
inputs, not store-distribution evidence; candidate-source.json records them
honestly. Replace candidates with store/Codemagic distribution receipts before
adoption. The spine ships no invented released fixture; the completion test stays
strict pending until two release rows and all eight endpoint cases exist.

Anchor each fixture to the tag's resolved commit and hashes of request code,
handwritten wrapper/decoder, generated DTO and originating OpenAPI slice. Current
DTOs come from backend/scripts/generate_dart_models.py and
docs/api-reference/app-client-openapi.json, exported from real FastAPI routes.
That source is useful provenance, not the oracle: these releases' conversation
list calls ServerConversation.fromJson, while memories/messages/action items use
generated wrappers. Freeze the actual called decoder closure and parser, including
enum/date/default coercion helpers. If isolating a handwritten decoder requires
extraction glue, prove its boundary vectors against the original released decoder
once during capture; preserve that receipt. Never regenerate it from head.

A release row references an immutable fixture directory: source-files with
commit/path/SHA256, consumer OpenAPI projection, synthetic request vectors,
expected observations and a standalone Dart decoder entrypoint. Requests retain
method, path, repeated/empty query values, header names and body encoding; replace
auth values with harness-only credentials. Responses distinguish missing from
null, required from optional, arrays from objects, number coercion, enum policy,
status/content-type and pagination. Keep only fields the released client reads,
not every server model property. Additive unknown fields and missing truly
optional fields pass; required removal, incompatible response types and tighter request acceptance fail. Fixtures
contain synthetic text only, no copied accounts, credentials or production traffic.

Capture has two proofs: source extraction from immutable release blobs, plus
hermetic request/response observations exercising those decoders. Journey
fixture_backend.dart helps enumerate request vectors but is not backend truth.
Replay requests through real routers in backend/testing/e2e/conftest.py's existing
fake-Firestore/Redis/storage app. Use its network guard and synthetic auth dependency;
never load the app through default production wiring. Capture returned HTTP bytes,
then run the frozen decoder, asserting nonempty sentinel ids and semantic values.
A fake server returning fixtures is not acceptance. The protected integration
contract wraps the real route callable and proves replay traverses it. Shared
fixtures do not prove live-session sign-in: backend principal, anonymous app and
signed-in app remain distinct; C10 tests authenticated and rejected requests
without designing token delivery.

Later small batches add users/profile, auth (headers/401/refresh contract, not
Firebase internals), POST chat and listen. For SSE freeze actual line parsing:
these clients recognize data:/think: with __CRLF__, and base64 done:/message:
records, plus legacy error forms; this is not generic JSON SSE. Split UTF-8 and
frame delimiters at every byte boundary, retain terminal ordering and require a
terminal outcome. WebSocket fixtures cover path/query/headers, auth rejection,
accepted handshake and first typed messages/close code, not live STT/BLE/audio.
Do not mark these families protected before their decoder/replay cases land.

Server-owned support-policy.json defaults to no minimum. Retain every adopted
build until both platforms' explicit minimum build passes it; no rolling N-window
or calendar expiry. Bootstrap coverage is only two builds, not a claim that older
clients are unsupported. The existing dismissible MyUpgrader store prompt is not
a server minimum; firmware minimum_app_version is unrelated. Retirement needs a
server enforcement rollout receipt (policy revision, platform minima, rejection
proof for the old client), reviewed by backend/release owners. Keep immutable
fixtures archived after retirement; stop executing them only when that receipt
validates. Raising the minimum is a product/server change, never a compatibility
check's automatic escape hatch.

The active stdlib catalog check is in repo-checks.yml's manifest local/ci lane.
It compares adopted consumer projections using the existing directional OpenAPI
checker and rejects mutated fixtures. It does not constrain unadopted backend
files/endpoints. OpenAPI Contract already re-exports real head routes and checks
committed spec freshness; retain it. Builder replay runs in the existing Backend
Hermetic E2E job, reusing its environment and adding a manifest-owned command,
not a new workflow/job or second backend install. CI/release wires the same
run_registered_replay entrypoint and pinned standalone Dart decoder once release
fixtures are admitted; admission fails if replay is absent. Keep one Dart process
per unique decoder hash, share identical shapes across builds, target <30 seconds
incremental warm time for eight cases; measure before widening coverage.

Failure names release/platform, method/path, request or response JSON pointer (or
stream frame), old required shape, observed value/type and exact replay command.
Backend authors preserve the used shape/add an optional field, version a genuinely
incompatible endpoint, or use the separately reviewed server support policy.
Never edit an old fixture to agree with head. New unused endpoints and legacy
uncaptured shapes remain unrestricted. Schema comparison cannot prove semantic
meaning; sentinel observations and real-router replay complement it. This is not
a full historical client VM, store rollout verifier or production traffic recorder.
