# LLM Gateway Route Configuration

`lanes.yaml`, `route_artifacts.yaml`, and `feature_bundles.yaml` define explicit gateway routes.

`generated_route_overrides.yaml` changes only the gateway routes that are otherwise generated from
`backend/utils/llm/model_config.py`. It must not be used to change legacy product routing: edits here
are applied after the legacy profile is read and affect only `omi:auto:*` gateway lanes.

Each override names one configured feature, selects its gateway provider/model, and may set
provider request options such as `reasoning_effort` or Anthropic `effort`.
