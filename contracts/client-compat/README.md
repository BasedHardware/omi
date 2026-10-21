# Released client fixtures

Design: [CLIENT_COMPAT.md](../../scripts/dev-harness/CLIENT_COMPAT.md).
`catalog.json` currently has no captured release. Strict pending C10 tests expose
that absence; candidate-source.json is provenance research, not coverage. The
engine/synthetic PR may land first; owner-gated capture is a separate PR.

App core adds immutable `releases/<capture-id>/` bundles with these catalog fields:

- id, build (integer), platforms (`ios`, `android`), resolved 40-character commit;
- distribution: kind=`distributed`, receipt_url and a hash-pinned attestation path;
  its JSON binds version=1, commit/build/platforms, provider (app-store-connect,
  google-play or codemagic), artifact_id, provider receipt_url, reviewer and exact
  `https://github.com/BasedHardware/omi/pull/<n>#pullrequestreview-<n>` review_url;
- source_files: repository path → SHA256 of exact released Git blob;
- files: catalog-relative repository path → SHA256 of every frozen input;
- projection, cases, decoder, decoder_equivalence: paths present in files. Projection is OpenAPI 3.1
  reduced to the requests/fields actually used. Cases use the schema below.

An id names a capture bundle, not just a build. Widen coverage by appending a new
bundle for the same commit/build; preserve earlier bundles and case attribution.
Reuse the Dart process for identical decoder hashes. Bootstrap rows name two distinct build identities.

Keep copied decoder sources, their runner, observations and minimal dependency
closure in files. The replay job must fetch admitted commit objects (its test-job
checkout is shallow today); repo-checks already has full history. CI validates
hashes and Git provenance; backend replay invokes pinned Dart with
the absolute frozen entrypoint path. Stdin JSON has status, headers, body_base64;
stdout is the observation object. Nonzero exit, malformed output or a 10-second
deadline is a failed replay, never empty data. The pinned attestation records owner-reviewed evidence, not automated proof
that the store distributed a build. Decoder equivalence receipt fields and vector
classes are specified in CLIENT_COMPAT.md. Do not claim otherwise.

Case JSON entries have id, platform, request `{method,path,query,headers,body}`,
decoder, observations, status. Query and headers are ordered lists of string
pairs (duplicate values preserved); body is UTF-8 text for the initial GET batch.
Observations are a nonempty map of semantic sentinel names to decoded values,
not full-response equality. Required/optional and null/type rules belong to the
frozen decoder and its consumer projection. Future streaming cases must version
the case schema before binary bodies/chunks or WebSocket frames are admitted.

`support-policy.json` is backend/release-owned and does not itself enforce a
runtime minimum. Null means no expiry. Non-null platform minima require the
server rollout receipt and rejection-test reference, reviewed separately. The
catalog checker checks structure/immutability, not deployment truth. Archived
fixtures remain pinned; only the replay selection changes.
