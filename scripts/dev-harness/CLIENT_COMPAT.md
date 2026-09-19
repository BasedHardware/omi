# C10: released-client replay

App core owns capture/decoders; CI/release owns admission/wiring. PR1 implements
the replay engine with synthetic fixtures, preserving an empty released catalog.
Retire engine markers only; the real-capture bootstrap remains pending. PR2 needs
owner-supplied distribution evidence for two builds and four GETs: conversations,
memories, messages and action-items. Tags are build inputs, not distribution proof;
candidate-source.json is explicitly unverified. An arbitrary HTTPS URL is not
admission: require a hash-pinned distribution attestation binding commit, build,
platforms, provider artifact URL and a release owner's PR review. CI checks that
binding, not store authenticity; the owner supplies/reviews the actual receipt.

Anchor each fixture to the tag's resolved commit and hashes of request code,
handwritten wrapper/decoder, generated DTO and originating OpenAPI slice. Current
DTOs come from backend/scripts/generate_dart_models.py and
docs/api-reference/app-client-openapi.json, exported from real FastAPI routes.
That source is useful provenance, not the oracle: these releases' conversation
list calls ServerConversation.fromJson, while memories/messages/action items use
generated wrappers. Freeze the actual called decoder closure and parser, including
enum/date/default coercion helpers. ServerConversation imports Flutter: do not run that file with standalone Dart.
Extract only its pure decoding closure, preserving defaults/coercions. Admission
requires a pinned equivalence receipt: the original decoder in a hermetic Flutter
test at the release SDK and the extraction consume identical missing/null/type/
enum/date/default vectors and produce identical observations or failures. Record
source/vector/decoder hashes and SDK version. The row's decoder_equivalence points
to a pinned JSON receipt: source_files, decoder_sha256, flutter_sdk, command and
vectors[{case,input,original,extracted}]; each outcome is {ok,value}, with bounded
error classification in value on failure. The protected admission oracle checks
all seven vector classes and both outcomes. No proof means no admission.

Each row is an immutable capture bundle; widen a build’s coverage by appending
a new bundle for that commit/build, never rewriting one. Its inputs are: source-files with
commit/path/SHA256, consumer OpenAPI projection, synthetic request vectors,
expected observations and a standalone Dart decoder entrypoint. Requests retain method, path, repeated/empty query values, header names and body
encoding; replace auth with harness-only credentials. Pin captured default vectors
and compare cases to them, not just endpoint names. Candidates 990/992 messages
send app_id='' and dropdown_selected=false, with no limit/offset. Hash handwritten
conversation/memory/message wrappers and transitive decoder helpers too. Responses distinguish missing from
null, required from optional, arrays from objects, number coercion, enum policy,
status/content-type and pagination. Keep only fields the released client reads,
not every server model property. Additive unknown fields and missing truly
optional fields pass; required removal, incompatible response types and tighter request acceptance fail. Fixtures
contain synthetic text only, no copied accounts, credentials or production traffic.

Capture needs immutable-source provenance and hermetic decoder observations;
journey fixtures enumerate vectors but do not prove backend compatibility.
Replay requests through real routers in backend/testing/e2e/conftest.py's existing
fake-Firestore/Redis/storage app. Use its network guard and synthetic auth dependency;
never load the app through default production wiring. Capture returned HTTP bytes,
then run the frozen decoder, asserting nonempty sentinel ids and semantic values.
A fake server returning fixtures is not acceptance. The protected integration
contract checks active cases traverse real routes and decodes their exact bytes.
The bootstrap stays pending until admitted captures exist. Synthetic success is
engine evidence only; neither it nor backend auth proves live-session sign-in.

Later batches cover users/profile, auth, POST chat and listen. SSE freezes the
client's data:/think:/base64 done:/message: parser, split UTF-8/frame boundaries
and terminal ordering. Socket cases cover handshake/auth/first messages/close,
not live STT. These families remain unprotected until replay cases land.

Server-owned support-policy.json defaults to no minimum. Retain every adopted
build until both platforms' explicit minimum build passes it; no rolling N-window
or calendar expiry. Dismissible MyUpgrader is not server enforcement. Retirement needs a
server enforcement rollout receipt (policy revision, platform minima, rejection
proof for the old client), reviewed by backend/release owners. Keep immutable
fixtures archived after retirement; stop executing them only when that receipt
validates; zero supported cases reports out-of-scope, not compatibility. Raising
the minimum is a product/server decision, never an automatic escape hatch.

The active stdlib catalog check is in repo-checks.yml's manifest local/ci lane.
Projections include the transitive local $ref closure. Missing/external refs fail
with their pointer and recapture instruction, never a traceback. The directional
OpenAPI checker compares only adopted consumer projections. It does not constrain unadopted backend
files/endpoints. OpenAPI Contract already re-exports real head routes and checks
committed spec freshness; retain it. Builder replay runs in the existing Backend
Hermetic E2E job, reusing its environment and adding a manifest-owned command,
not a new workflow/job or second backend install. CI/release wires the same
run_registered_replay entrypoint and pinned standalone Dart decoder once release
fixtures are admitted; admission fails if replay is absent. Use the real pinned Dart process in decoder acceptance; an execute stub proves
only IPC. Share identical decoder shapes; measure runtime before widening.

Failures name release/platform, endpoint and offending pointer. Preserve the used
shape, version the endpoint, or obtain separately reviewed server retirement;
never edit old fixtures to match head. Uncaptured shapes remain unrestricted.
