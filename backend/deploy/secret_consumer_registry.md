# Secret Consumer Registry

`secret_consumer_registry.yaml` is the checked-in source of truth for high-risk
secret names that appear in backend deploy/runtime surfaces. It stores names,
owners, categories, and value-free rotation instructions only. Do not put secret
values, hashes, fingerprints, or examples that resemble production credentials
in this file.

Run the verifier locally:

```bash
python3 backend/scripts/verify-secret-consumer-registry.py
```

The verifier parses checked-in Helm values, `backend/deploy/runtime_env.yaml`,
GitHub workflows, and `codemagic.yaml`. It reports:

- consuming runtime and service/job
- env var name and source file
- default refresh action after rotation
- unregistered high-risk deploy references

The default path is offline and credential-free. It never reads environment
variables or secret stores, and it prints names and file paths only.

When adding a new high-risk secret reference, add an entry under `secrets` in
the registry in the same PR. Public client IDs, URLs, hosts, price IDs, and
other non-secret values that match generic patterns belong in
`ignored_secret_names` with care.

Entries may set `status: expected_absent` or `status: code_only` only when a
registered name is intentionally not found in checked deploy/runtime bindings.
The verifier still fails on any unregistered name that appears in a
secret-bearing context such as `secretKeyRef`, Cloud Run `secrets:`, GitHub
`${{ secrets.NAME }}`, or Codemagic secure env references, even when the name
does not match the generic high-risk patterns.
