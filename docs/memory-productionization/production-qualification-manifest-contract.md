# Production qualification manifest contract

Status: production-neutral manifest and validator implemented; no values,
image, load result, runtime selection, infrastructure, or traffic activated.

`scripts/production-qualification-manifest.ts` is the single strict coordinate
contract for later P8 image and load qualification. It prevents a builder or
runner from choosing operational targets implicitly.

The manifest binds exact committed source, a frozen dependency-artifact receipt
digest and OCI runtime coordinates, PostgreSQL 18.4, Postgres.js 3.4.9, the complete current
migration history, workload rates/concurrency, resource ceilings, connection
allocations, recovery objectives, and opaque model-pipeline resources. Every
model resource has maximum concurrency one.

`parseProductionQualificationManifest` first detaches an exact plain JSON tree,
then validates every closed field and returns a deeply frozen manifest plus its
canonical SHA-256 digest. The named Cloud SQL allocations are summed and must
fit the declared total; the receipt reports both allocated and unallocated
connections. Migration changes invalidate an earlier manifest until it is
reviewed and regenerated.

`bun run qa:production-qualification -- --input <file>` emits only the version
and manifest digest on success. Errors use closed codes and never include the
input path or bytes.

No repository-owned manifest with chosen numeric values exists yet. The first
real manifest is a decision artifact: it must be created only after workload,
recovery, connection-budget, and provider-resource coordinates are ratified.
This contract is not a release manifest, authority token, credential, image,
deployment configuration, or evidence that any objective has passed.
