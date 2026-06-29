# Legacy Plugin Monolith

`plugins/main.py`, `plugins/_mem0`, and `plugins/_multion` are kept for #8559.

Deletion is blocked because `.github/workflows/gcp_plugins.yml` still builds `plugins/Dockerfile`, and that Dockerfile starts `uvicorn main:app` from the root `plugins/` package.

Rules until the deploy target is retired:

- Do not add new plugin business logic to the monolith.
- Keep root `plugins/models.py` as a compatibility layer over `omi_plugin_sdk.models`.
- Do not delete `_mem0` or `_multion` without first replacing or removing the GCP plugins deploy target.
- Keep `plugins/Dockerfile` and `plugins/Dockerfile.datadog` aligned with the monolith decision.
