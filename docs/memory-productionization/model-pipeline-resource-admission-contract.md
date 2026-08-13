# Production model-pipeline resource admission

Status: implemented as a route-free production composition boundary. It does
not start a worker, select a provider, read a credential, or activate traffic.

## Contract

1. The PostgreSQL exclusivity adapter accepts only a receipt minted by
   `parseProductionQualificationManifest` in the current process. A structural
   copy or caller-authored receipt fails before PostgreSQL is touched.
2. The manifest owns the complete sorted set of opaque provider-resource
   digests and fixes `max_concurrency` to exactly one for every entry.
3. The adapter returns an admitted exclusivity capability. Formation,
   predicate, query-evaluation, and Listen-attribution PostgreSQL runtimes
   reject an ordinary generic exclusivity port at construction.
4. An undeclared resource returns `unavailable` before an advisory-lock pool
   call or provider callback. Raw credentials, provider names, and model output
   never enter this boundary.
5. Import-graph tripwires make raw admission construction and generic
   PostgreSQL lock construction test-only/private. Production composition must
   flow through the parser-verified adapter.
6. Advisory locking remains one session-owned lock for the whole cache-miss
   model pipeline. Connection loss aborts and drains the provider call before
   a contender can reacquire the same resource.

## Deliberate non-claims

- This boundary does not prove that a deployment's credential owner maps a
  particular provider/model to a particular opaque digest. That mapping must
  be supplied and checked by the future production process composition.
- No production worker entrypoint exists in this slice. No route, polling
  cadence, provider default, capacity default, secret read, push, or deployment
  is introduced.
- Real PostgreSQL qualification proves the adapter's lock, contention, and
  connection-loss behavior. It does not claim that production traffic is
  currently using it.

## Acceptance evidence

- Parser-minted receipt succeeds; structural receipt copies fail pre-pool.
- Sorted unique digest rows with capacity one succeed; raw keys, duplicates,
  ordering drift, accessors, proxies, and capacity two fail closed.
- All four PostgreSQL model runtimes reject generic ports and accept only a
  minted admitted capability.
- Same-resource independent pools exclude; distinct resources overlap;
  backend termination aborts the pending provider before reacquisition.
- Contract QA, import lint, focused tests, diff check, Bun runtime parity, and
  Node runtime parity are required before landing.
