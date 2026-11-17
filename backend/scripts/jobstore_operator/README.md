# Exact post-SQL operator qualification

The current candidate is `general-copy-postsql-v2.c282.schema8`, with runtime source
`c2824362c2a52925def3ef83f13c3b58487a6aa0` and tree
`a5c8acbd193b6b85661c9fe91759b2ec0eb80608`. The source includes nine migrations;
the catalog-only profile deliberately accepts the existing database's exact first
eight migrations. It checks the complete schema, generated/default expressions,
primary-key timing, index validity, effective grants, read-only session and TLS
before reporting readiness. It neither applies migrations nor copies data.

`qualification_profile.py` pins the catalog source, contract, structure, frozen
process guard, retained legacy readiness helper and exact 36-case fixture suite.
The catalog verifies every tracked working blob and the complete file set,
including ignored files, without trusting Git index flags. Its bindings must be
on a read-only filesystem. Missing or incorrect psycopg refuses before ADC.
These source checks are separate from authentication and runtime admission.

The default image entry point remains the frozen guard's `--hold`. Qualification
must bind the loaded image's complete configuration, platform, layers and store
identity to the validated archive, exercise the real general copier CLI import,
run the complete fixed suite with zero skips, and reach an injected credential
refusal after full source verification under the actual resource limit. The
publisher rejects legacy readiness-only receipts and mismatched profiles,
sources, suite identities or proof fields. Earlier image qualification cannot
qualify this full rebuild. `readiness.md` documents the retained legacy metadata
probe; its source and receipt identity remain unchanged.

The candidate contract is closed: archive, immutable image, release assets,
registry evidence and native qualification remain null until measured. The
existing `gcp_backend.yml` qualification/publication workflow is unchanged.
Release must admit the reviewed main control and exact candidate, then complete
native AMD64 qualification and immutable publication before a separately reviewed
execution packet can run. Local tests, an ARM-hosted build or a publication
receipt do not establish production serving or Firestore reads removed.

Registry admission requires reviewed existing allow/trust evidence for the fixed
publication destination. `registry_write_authorization` remains null until an
actual write and full digest-preserving readback succeed. The fixed-resource
`testIamPermissions` request is diagnostic only; missing, malformed, oversized,
redirect, authentication or transport outcomes stop before registry operations.
Existing private auth-file cleanup and bounded output guards remain in force.
No access expansion, new workflow or deploy is included in this source change.

Portable publication tests use standard-library seams that fail on SDK use.
Discovery never substitutes SDK modules or skips for missing packages. Run the
mandatory control suite from the repository root:

```sh
python -B -m unittest discover -s backend/scripts/jobstore_operator/tests -v
```

The separately hashed catalog fixture suite, real Linux image and workload
identity checks remain additional gates. Firestore authority and cohort ramps
require their own runtime, fleet, privacy, budget, metrics and rollback evidence.
