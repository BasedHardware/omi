# Jobstore operator qualification and publication

The existing `gcp_backend.yml` workflow has a manually selected `operator-qualify-publish` mode. It qualifies the exact reviewed OCI archive on the existing native AMD64 runner, then preserves its digest during publication and reads every blob back. It does not build a new image, install a runtime, run migrations, access account data or enable the pilot.

`artifact-contract.json` pins the runtime source and exact input bytes. The approved inputs are staged as an unpublished same-repository draft; numeric release/asset IDs must match its metadata and downloaded bytes. Keep this release unpublished. The ephemeral job `contents:write` permission supports draft visibility; no PAT or new permanent credential is used. The source contract intentionally refuses execution while its status is closed or `registry_write_authorization` is null. A direct writer role binding alone has not established effective registry permission or WIF provider conditions.

Before a separately approved Release-only dispatch, review the actual draft identities and existing exact-resource registry/WIF authorization, commit the complete contract, and obtain successful exact main Release Eligibility proofs for both the fixed runtime source and workflow control source. The existing prod environment and shared prod train remain the execution gates. No skip-proof, break-glass or deployment-image override is accepted.

Qualification validates native host/local Docker identity, the complete OCI and loaded config/manifest identity, unique runtime dependency catalog, all 49 image fixtures without skips, offline smoke and hold/SIGTERM. Containers have no network or credentials/state mounts. An owned loaded tag is cleaned up even on load failure; uncertain cleanup is recorded and qualification fails closed. Publication begins only after successful qualification and uses the existing WIF deployer with digest preservation and complete registry readback. An uncertain push remains an uncertain write until readback settles it.

Run the portable source checks from the repository root:

```sh
backend/.venv/bin/python -m unittest discover -s backend/scripts/jobstore_operator/tests -v
```

These offline source checks do not establish draft API access, native image qualification, registry access, or production behavior. Exact image native fixtures run only inside the separately guarded workflow. Existing Release remains the sole production executor; Firestore remains authoritative until all independent runtime, fleet, privacy, cohort and budget admission gates are satisfied.
