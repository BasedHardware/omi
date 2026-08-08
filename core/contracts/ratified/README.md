# `@omi-core/ratified-contracts`

Provisional naming markers for the terms used immediately below:

`// domain-pending(DIV-DOMCORE-001)`
`// domain-pending(DIV-DOMCORE-008)`
`// domain-pending(DIV-DOMCORE-003)`
`// domain-pending(DIV-DOMCORE-005)`

This is the narrow shared-package boundary approved by the ADR-004 Track 1 mechanism
review. Version `0.1.0` has no package-root export and exposes only three explicit
subpaths:

- `./pagination/cursor`, opaque HMAC-keyset cursor carriage; and
- `./projections/synthesized`, a synthesized-memory read projection distinct from
  the legacy editable `Memory` record; and
- `./recall/trace`, a content-safe operational trace kept separate from frontend items.

The read projection exposes only ready renders with a validated, non-empty opaque id and
exactly one non-empty synthesized `text` field. Optional opaque citation references and
synthesis-version/input/output-digest provenance remain non-presentational.
It never reuses `RecordId` and never exposes account or projection generations, commit ids,
owner/app/key coordinates, policy labels, raw evidence, editable content,
lock/visibility/category/review fields, transcript/tags/tier/layer/cohort, explicit display
ordering, store, model prompt, or provider details. Array order is the deterministic server order.
The page carries a versioned completeness envelope with opaque aggregate frontiers plus an
explicit query-gap absence union; the strict runtime validator rejects extra fields and false
completeness. Terminal and continuation windows are distinct TypeScript variants, and query-gap
absence is valid only on an honest terminal page. Item ids, per-item citation refs, and
completeness reasons are unique. Empty, stale, or failed renders never serialize as items.

The trace carries only opaque stage refs, typed outcome/freshness, bounded counts, and strategy
version. Its type and runtime laws enforce the six-stage subset chain, reference uniqueness, and
the stage implied by every outcome, while keeping trace fields out of the frontend item.

Rulings of record: ADR-004, charter WS-006/M-001, DIV-MEM-004, FEAT-MEM-001,
FEAT-MEM-002, FC-AUTH-003, and FEAT-AUTH-011. `DIV-DOMCORE-001` and
`DIV-DOMCORE-008` remain open;
their code-level spellings carry mechanical rename markers.

`PROVENANCE.json` binds reviewed inputs. `ARTIFACT.json` is deliberately outside the
tarball so it can bind the tarball digest without a self-reference. The tarball includes
versioned JSON conformance fixtures but excludes test/source scripts. `pnpm verify` checks both,
asserts the exact export/file allowlists, installs the tarball into an empty consumer, type-checks
it, and runs the packed fixtures.
