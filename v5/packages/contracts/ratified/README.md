# `@omi-core/ratified-contracts`

Provisional naming markers for the terms used immediately below:

`// domain-pending(DIV-DOMCORE-001)`
`// domain-pending(DIV-DOMCORE-008)`
`// domain-pending(DIV-DOMCORE-003)`
`// domain-pending(DIV-DOMCORE-005)`
`// domain-pending(DIV-DOMCORE-006)`

This is the narrow shared-package boundary approved by the ADR-004 Track 1 mechanism
review. Version `0.2.0` has no package-root export and exposes only three explicit
subpaths:

- `./pagination/cursor`, opaque HMAC-keyset cursor carriage; and
- `./projections/synthesized`, a synthesized-memory read projection distinct from
  the legacy editable `Memory` record; and
- `./recall/trace`, a content-safe operational trace kept separate from frontend items.

The read projection exposes only ready renders with a validated, non-empty opaque id and
exactly one non-empty synthesized `text` field. Optional opaque citation references and
synthesis-version/input/output-digest provenance remain non-presentational; both digests are
branded lowercase 64-character SHA-256 hex values.
It never reuses `RecordId` and never exposes account or projection generations, commit ids,
owner/app/key coordinates, policy labels, raw evidence, editable content,
lock/visibility/category/review fields, transcript/tags/tier/layer/cohort, explicit display
ordering, store, model prompt, or provider details. Array order is the deterministic server order.
The page carries a versioned completeness envelope with separate opaque aggregate accepted-work
and short-term-memory search frontiers plus typed null reasons. A complete claim requires honest
coverage of both: the accepted frontier searched must equal the declared frontier (or report that
no accepted work exists), and the short-term frontier must be present (or report that no eligible
short-term candidates exist). An accepted frontier behind the declaration always contributes
`accepted_work_pending`, never a frontier substitute. Under ADR-008, the declared completeness
status is derived from every applicable unique reason using the precedence
`degraded > incomplete > partial > complete`; lower-precedence reasons remain serialized rather
than being discarded. The envelope also carries an
explicit query-gap absence union; the strict runtime validator rejects extra fields and false
completeness. Terminal and continuation windows are distinct TypeScript variants, and query-gap
absence is valid only on an honest terminal page. Item ids, per-item citation refs, and
completeness reasons are unique. Empty, stale, or failed renders never serialize as items.
An `incomplete` window can pair only with incomplete, degraded, or partial recall; complete recall
uses either an ordinary terminal-complete window or an ordinary paginated-more continuation.

Untrusted wire input must enter through the bounded canonical raw-JSON parsers. They reject
malformed, oversized, noncanonical, and duplicate-key payloads before validating the contract.
Canonical verification first copies parsed objects and arrays by descriptor into a null-prototype
graph using null-prototype property-descriptor records, so inherited `toJSON`, `get`/`set`, or
omitted-optional-field getters cannot execute.
The exported object predicates are only for already-parsed trusted JSON data; they reject deep
nonplain graphs and accessors, but JavaScript cannot inspect a hostile `Proxy` without possible
trap execution.

The trace carries only opaque stage refs, typed outcome/freshness, bounded counts, and strategy
version. Its type and runtime laws enforce the six-stage subset chain, reference uniqueness, and
the stage implied by every outcome, while keeping trace fields out of the frontend item.

Rulings of record: ADR-004, ADR-008, charter WS-006/M-001, DIV-MEM-004, FEAT-MEM-001,
FEAT-MEM-002, FC-AUTH-003, FEAT-AUTH-011, and COORD-contract-evolution-policy.
`DIV-DOMCORE-001` and `DIV-DOMCORE-008` and `DIV-DOMCORE-006` remain open;
their code-level spellings carry mechanical rename markers.

## 0.8.0 - ratified task writes use the domain vocabulary (additive)

0.8.0 changes only the serialized task op bags in
fixtures/write-ops-conformance.json: title becomes description in five bags
and done becomes completed in ten. The one memories-domain text bag key is
unchanged because the ruling names only the two task-field renames.
fixtures/write-ops-outcomes.json has no request bags and is unchanged.

Ruling of record:
data/run-2026-08-09b/decisions/FABLE-R26-task-field-vocabulary-signed.md,
amendment A1. A1 orders this source corpus bump before the separately owned
write-door enforcement; this package does not implement or authorize that door.

This bump is additive under COORD-contract-evolution-policy.md: it changes no
export, type, validator, wire outcome, or obligation for a client built against
an older version. The corpus of record now exercises the signed task domain
vocabulary across the existing wire cases. Rollback is a re-vendor of 0.7.0;
these request examples define no persisted data shape.

## 0.7.0 - the account epoch rides on the tasks read (`additive`)

`0.7.0` adds ONE optional field, `TaskRead.Page.accountEpoch`, and one reader,
`readTaskPageAccountEpoch`. No new subpath, no new fixture file, no change to
any existing field, shape or validator.

Ruling of record: `DAVID-tasks-read-epoch-and-ci` **D3**, signed by David in
person - the account epoch rides on the ratified read as an additive field. No
new endpoint, no second auth path, no separate availability signal: *a client
that can read can always write.*

**Why `additive` and not `breaking`, given that it adds a field to an existing
shape.** §1 makes the classification turn on one word, so the word has to be
true of the validator and not only of the type. `isTrustedTaskPageData` accepts
both key sets, so a five-key `0.6.0` page still validates and a client on
`0.7.0` keeps reading a server on `0.6.0`. `TASKS_READ_CONTRACT_VERSION` does
not move - it is compared for equality, so bumping it would refuse every page
any deployed server serves today. Exact-keys is preserved on both branches, so
an unknown sixth key is still refused: optional does not mean anything goes.

**Absent is not zero.** `0` is a claim about a generation; "I was not told" is
the absence of one. Read it through `readTaskPageAccountEpoch`, which returns
`null` for absent - a client that defaults to zero stamps every write envelope
with a generation nobody asserted, and the account-epoch fence then refuses
those as stragglers, turning a missing field into lost edits.

**The migration-progress question was checked, not assumed.** `backend:ADR-012`
§4 forbids a wire that lets a caller probe migration state, and a non-author
answered that in writing before this landed (`AUDIT-adr012-epoch-check.md`).
The answer rests on three properties this field does not itself guarantee: the
read route resolves the account only from the bearer token; the value is
per-account, never a fleet counter; and refusals stay epoch-free and
byte-identical to an unknown route, which is where `COORD-fable-rulings-wave2`
W1's "the active epoch is never returned" is scoped and where it reconciles
with D3.

Rollback is a re-vendor of `0.6.0`.

## 0.6.0 - the ratified tasks READ wire (`additive`)

`0.6.0` adds ONE export subpath, `./projections/tasks`, plus its schema of
record (`fixtures/tasks-read-shape.json`) and conformance corpus
(`fixtures/tasks-read-conformance.json`). No existing export, field, shape or
validator changed, so every client built against `0.5.0` keeps working
unchanged with no new obligation - which is what makes this `additive` under
COORD-contract-evolution-policy.md §1. The precedent is `0.3.0`, which added
`./write/ops` (required fields and all) and was classified the same way: §1's
"adding a required field is breaking" governs a field added to an EXISTING
shape, and a new namespace imposes nothing on a client that never imports it.

Ruling of record: `DAVID-tasks-read-epoch-and-ci`, signed by David in person.
**D1** - the tasks read mirrors the memories read model: reader-scoped opaque
ids, cursor pagination, and a completeness envelope, served through the same
registered composition rule 16 guards. **D2** - full parity with all thirteen
fields `core/contracts/src/domain/tasks.ts` declares, because the point of
parity is flip-ability: the surface renders identically off either generation,
so the factory change is one line and so is its rollback. `id` is the ratified
opaque ref, never the legacy server id, and the local slug/server-id alias
`adapters-legacy` maintains does not cross this wire.

The envelope is `tasks-completeness-v1`, deliberately NOT the memories
`recall-completeness-v1`. Tasks have no short-term overlay and no accepted-work
queue, so reusing that spelling would mean answering `no_eligible_stm` forever
about a subsystem unrelated to tasks; §1 classifies a field whose MEANING
differs as a different field even when the shape matches. Its checkable pair is
`newestAppliedFrontier` against `declaredFrontier` - the transposition of the
accepted-frontier law onto the concept tasks actually has, since
`POST /v1/tasks/ops` applies writes into the projection a read serves from. A
`complete` claim therefore requires the applied frontier to have reached the
declared one, or an explicit `no_applied_writes`.

The account epoch is NOT here. `DAVID-tasks-read-epoch-and-ci` D3 rides it on
this response as an additive field in a SEPARATE bump, gated on a non-author's
written ADR-012 §4 check. The bumps are split (fable, R9) precisely so this one
is never blocked by that gate.

**The `openTasks()` flip is not performed by this bump and is not authorized by
it** (fable, R7). Production has no control-state publisher, so every
platform-generation write denies, and no ratified path puts a real account's
tasks behind the platform generation. Fixture-venue parity is the flip's
precondition, never its trigger.

## 0.2.0 - the client contract version header (`additive`)

`0.2.0` adds `APP_CONTRACT_VERSION_HEADER` (`x-omi-contract-version`),
`APP_CONTRACT_FLOOR_VERSION`, `isWellFormedContractVersion`, and
`resolveDeclaredContractVersion` to `./projections/synthesized` - no existing
export, field, or shape changed. Every client built against `0.1.1` keeps
working unchanged, which is what makes this `additive` under
COORD-contract-evolution-policy.md §1.

MCP's `mcp-protocol-version` header already tells the server which protocol
generation a client speaks; the app-facing REST door had no equivalent, so
N/N-1 coexistence (policy §5) had nothing to key off. An app-facing request
now declares the contract version its client was built against; an absent,
empty, or malformed value resolves to `APP_CONTRACT_FLOOR_VERSION` rather
than being rejected, per policy §4's tolerate-and-count rule.

**`APP_CONTRACT_FLOOR_VERSION` is a PROVISIONAL placeholder, not a ratified
floor.** The policy defines the floor as the oldest version still served,
keyed off `backend:ADR-007`'s account control record (§5) - a record that
does not carry a contract-version floor anywhere in this codebase yet, and no
version older than `0.2.0` has ever shipped. Until that record actually
carries one, this package treats the floor as the current version. Raising a
real floor is, per policy §7, an owner-signed product action - not something
this bump performs or should be read as having performed.

`PROVENANCE.json` binds reviewed inputs. `ARTIFACT.json` is deliberately outside the
tarball so it can bind the tarball digest without a self-reference. The tarball includes
versioned JSON conformance fixtures but excludes test/source scripts. `bun run verify` checks both,
asserts the exact export/file allowlists, installs the tarball into an empty consumer, type-checks
it, and runs the packed fixtures.
