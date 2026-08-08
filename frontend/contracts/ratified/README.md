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
versioned JSON conformance fixtures but excludes test/source scripts. `pnpm verify` checks both,
asserts the exact export/file allowlists, installs the tarball into an empty consumer, type-checks
it, and runs the packed fixtures.
