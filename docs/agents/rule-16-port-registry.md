# Rule 16 — the port registry

> **A registered port has exactly ONE composition.** Two modules independently
> constructing the same port type are two implementations, not two adapters.

Status: **PROVISIONAL**, landed 2026-08-08. It runs immediately. Per the swarm
protocol §8, a new fence stays provisional until someone who did not write it has
read the check against this English statement and audited its false positives; if
it fires on another lane, that is a swarm-wide blocker, never something to route
around.

Implementation: `PORT_REGISTRY` in platform/scripts/lint-import-graph.ts, which
runs in `bun test` and in `make l0`.

Paths below that begin `platform/`, `apps/`, `scripts/` or `harness/` are in the
SIBLING `platform` repo, not this one, and are written unquoted on purpose:
`check_agent_doc_references.py` verifies backticked repo paths against this tree
only, and a pointer it cannot check should not be dressed up to look like one it
can.

## The defect that wrote the rule

`ApplicationReadPorts` (defined in platform/core/retrieve/application-read.ts)
was constructed independently in two places:

| | REST door | MCP door |
| --- | --- | --- |
| | apps/service/composition/memory-read.ts | apps/qa/recall-service.ts |
| digest scheme | local `sha256Hex(canonicalJson(…))` | `sha256CanonicalContent(…)` |
| declared frontier | per-reader HMAC subkey | `frontier-v1:qa:<generation>` |
| coverage | caller-declared, default `bypassed` | hardcoded `no_eligible` |
| opaque codecs | `createReaderScopedOpaqueCodecs`, scoped by `principal_digest` | `createQaReferenceCodecs`, scoped by a caller-assembled `owner\|app\|key` string |
| authorization | captured once at prepare | re-resolved live per attempt |

Both were green. Both had been reviewed. Measured over ONE SQLite snapshot and
ONE principal, the two doors returned the **same memory** under **different
public identities**:

```
text                    identical
provenance.outputDigest 217942867fbea63c…   identical   (the same render)
id (MCP)                mem1_eca59618fff27e109ee1f6d36ae47fe4…
id (REST)               mem1_dd73274cc9b1a9ac91563567dd742f75…
citations[0] (MCP)      cit1_bcfcc1fc74e5f10343e6acf144fb85b0…
citations[0] (REST)     cit1_454d7844d6e41e3f058d53adebf82818…
declaredFrontier (MCP)  frontier-v1:qa:a03baf2571e93e82…
declaredFrontier (REST) frontier-v1:d40965f5a1b3d7e8ac81…
```

Every node-level cross-door assertion in the suite passed the whole time. That is
the shape that makes this a fence rather than a convention: the divergence sat one
layer below where the existing assertions looked, and no amount of care in either
module could have surfaced it, because each module was individually correct.

A second, independent defect fell out of the same split. The MCP composition
carried a syntactic cursor pre-check so that every cursor rejection left it in one
error currency; the REST composition did not, because it was a different
composition. Measured on the REST door before the collapse:

```
cursor of 4096 chars   ->  400 bad_request
cursor of 4097 chars   ->  500 internal_server_error
cursor containing \x01 ->  500 internal_server_error
```

Two mutations of one token producing two public outcomes tells an attacker which
half of their guess was wrong.

## What the check does

Matched on **comment-stripped** text, in non-test `.ts`/`.tsx` files:

| form | example |
| --- | --- |
| annotated literal | `const ports: ApplicationReadPorts = {` |
| arrow return type | `): ApplicationReadPorts =>` |
| satisfies | `satisfies ApplicationReadPorts` |

A match outside the row's `composedIn` list fails the lint. A row whose
`composedIn` path contains no construction site also fails — a stale row silently
disables the rule, which is the failure mode the wire-seam registry (rule 15)
calls "the selector is probably stale".

Escape hatch, mirroring `// domain-pending(<ID>)` and
`// storage-provenance-ok(<reason>)`: `// port-composition-ok(<reason>)` on the
binding line or the line above.

## Three deliberate exemptions, and what each gives up

**Casts (`as Port`) are not construction.** A cast is how a hostile, partial or
lookalike value is fed to the port's own defensive checks. Banning it would ban
the tests that prove those checks work.

**Comments are exempt wholesale.** This repo has already shipped a fence that
banned an ordinary English word and fired on prose while catching no real
reference; that fence had to be narrowed after false-positiving four integration
files. Prose cannot construct anything. The one registered composition's own
module header names the port type five times, and a commented-out composition is
exactly what a module looks like the day before someone deletes it. Verified
red: with comment-stripping removed, the fixture in
scripts/lint-import-graph.test.ts fires on three lines, all of them prose.

**Tests are exempt.** A test double is a second implementation on purpose — the
port's own contract test builds hostile and partial port records to prove the core
rejects them, which is the opposite of the defect this rule exists for, and a test
cannot serve a user a divergent id. What the exemption gives up is the question
"do the two doors actually agree?", which is not a fence question at all: it is an
assertion, and it lives in
platform/apps/service/composition/cross-door-identity.test.ts.

## Why the registry is opt-in

A row is added when a port acquires a **second** construction site, not when the
port is declared. This is what stops the rule over-reaching, and the audit below
shows it is not a theoretical concern: `ModelPort` legitimately has two source
constructions in platform/harness/model-select.ts (a fake and a live selector),
which is a strategy choice, not a divergence. Registering every port-shaped type
on sight would fire on that within a day, and a routed-around guardrail is worse
than none.

## False-positive audit

Run across **both** repos — 2402 `.ts`/`.tsx` files, 18 port-shaped types (every
exported `interface`/`type` whose name ends in `Port`/`Ports`, plus the registered
row) — with no registry filter and no test exemption, so that everything the
patterns touch is visible:

| type | site | verdict |
| --- | --- | --- |
| `ApplicationReadPorts` | `platform/apps/service/composition/memory-read.ts:418` | the registered composition |
| `ApplicationReadPorts` | `platform/core/retrieve/application-read.test.ts:249,720` | test doubles (hostile/partial) — exempt, correctly |
| `McpProtocolPorts` | `platform/apps/qa/mcp-ports.ts:83` | single construction; not registered |
| `RenderModelPort` | `platform/apps/qa/synthesizer.ts:129` | single construction; not registered |
| `ListenCaptureStreamPort` | `core-foundation/core/packages/wire-listen/src/listen_capture_stream.ts:423` | single construction; not registered |
| `ModelPort` | `platform/harness/model-select.ts:18,27` | **two legitimate constructions** — see above; must not be registered |
| `RecallModelPort` | `platform/harness/recall.test.ts:46,94,127` | test doubles — exempt, correctly |
| `SnapshottedPorts` | `platform/core/retrieve/application-read.ts:328` | not a port; an internal snapshot type |

**Zero prose hits and zero comment-only hits.** The patterns are syntactic rather
than word-shaped, so the class that burned this repo before does not arise here;
comment-stripping is belt-and-braces rather than the only defence.

Note the near-miss worth knowing about: `application-read.ts:328` reads
`const snapshotPorts = (ports: ApplicationReadPorts): SnapshottedPorts => {` —
`ApplicationReadPorts` appears on a line ending in `=>`, but the arrow-return
pattern is anchored to the **return** type, so it is attributed to
`SnapshottedPorts` and not to the registered row. Confirmed empirically by the
audit, not by reading the regex.

## Known limits — stated so nobody over-trusts it

- **An un-annotated object literal passed inline is not caught.**
  `readApplicationSynthesizedPage(request, { resolveAttempt: … })` type-checks and
  would slip past. No such site exists in either repo today (checked), but this is
  a real gap, not a hypothetical one.
- **It is syntactic.** It proves that only one module constructs the port. It
  cannot prove that module composes it *correctly*; that is what
  `cross-door-identity.test.ts` is for.
- **It does not run over `core-foundation`.** The linter walks the `platform`
  tree only. The audit above was run manually across both. If a port acquires a
  second composition inside `core-foundation`, this fence will not see it.

## Red-proofs (applied and observed failing)

1. **Second composition.** Re-added a parallel `ApplicationReadPorts` construction
   to apps/qa/recall-service.ts. Lint failed, naming both the arrow-return form
   (line 228) and the annotated-literal form (line 229). Restored; green.
2. **Prose guard is not vacuous.** Replaced the comment-stripped scan with the raw
   scan. The "does not fire on prose" fixture then failed, firing on three lines:
   a docblock, and two commented-out compositions. Restored; green.
3. **Stale row.** Pointed `composedIn` at a path that does not construct the port.
   Lint failed with the stale-row message. Restored; green.
4. **Cursor error currency** (the collapse, not the fence). Removed the
   `isSyntacticallyRedeemableCursor` guard from the shared `readMemoryPage`. The
   two new rows in `route-hardening.test.ts` returned 500 while the three
   pre-existing rows still returned 400. Restored; green.
