# Backend Route Policy Manifest

Issue #8959 tracks a route policy manifest and generated inventory for backend routes.

The rollout is metadata-only. It does not change request handling, middleware, authentication, rate limiting, or OpenAPI output.

The full manifest coverage check remains report-only while legacy routes are baselined. CI also runs a strict missing-route baseline check: new backend routes must add a matching policy entry instead of expanding the legacy baseline.

## Scope

The initial manifest covers the primary FastAPI app created in `backend/main.py`:

- Service id: `backend-main`
- Application HTTP routes: included in inventory and manifest coverage checks
- Application WebSocket routes: included in inventory and manifest coverage checks
- FastAPI-generated docs/OpenAPI/Redoc system routes: listed as excluded system routes in generated inventory

Sibling FastAPI services such as `pusher`, `llm_gateway`, `agent-proxy`, `diarizer`, `modal`, and `parakeet` should get their own service ids or manifests later.

## Route Identity

The canonical route identity is:

```text
service:route_type:METHOD:/path/{param}
```

Example:

```text
backend-main:http:GET:/v1/conversations/{conversation_id}
```

Do not use function names or OpenAPI operation ids as the policy identity. They are useful evidence, but they are not the governed route surface.

## Commands

Run the report-only check:

```bash
cd backend
scripts/openapi_runner.sh scripts/route_policy_inventory.py --manifest route_policy_manifest.yaml --check --report-only
```

Run the CI baseline gate:

```bash
cd backend
scripts/openapi_runner.sh scripts/route_policy_inventory.py --manifest route_policy_manifest.yaml --enforce-missing-baseline
```

Print deterministic JSON inventory:

```bash
cd backend
scripts/openapi_runner.sh scripts/route_policy_inventory.py --manifest route_policy_manifest.yaml --print
```

Write deterministic JSON inventory:

```bash
cd backend
scripts/openapi_runner.sh scripts/route_policy_inventory.py --manifest route_policy_manifest.yaml --write-inventory /tmp/backend-route-inventory.json
```

Regenerate the legacy missing-route baseline after reviewed routes are added to the manifest or removed:

```bash
cd backend
scripts/openapi_runner.sh scripts/route_policy_inventory.py --manifest route_policy_manifest.yaml --write-missing-baseline route_policy_legacy_missing_routes.txt
```

Do not add newly introduced routes to `route_policy_legacy_missing_routes.txt`. That file is only for the pre-existing route inventory from the initial rollout.
On pull requests, CI compares this file with the target branch copy and fails if the legacy baseline grows.

## Adding Or Changing A Route

1. Add or update the FastAPI route.
2. Run the route policy inventory command and the CI baseline gate.
3. Add or update the matching manifest entry in `backend/route_policy_manifest.yaml`.
4. Prefer `review_status: reviewed` when the route policy has been checked by the route owner.
5. Use `review_status: legacy_unreviewed` only for baseline migration entries that still need policy review.
6. Use `review_status: exempt` only with an `exempt_reason`.

Keep declared policy separate from observed evidence. Dependency names, OpenAPI tags, timeout override hints, and endpoint modules are generated to help review, but they are not a substitute for owner-reviewed policy.
