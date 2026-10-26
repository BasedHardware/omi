# Keyless machine access to aggregate stats

The admin guard (`requireScope` in `lib/auth.ts`) accepts Google-signed OIDC ID tokens only for **GET** requests
under `/api/omi/stats/`, including `/api/omi/stats/wall`. Firebase ID tokens
still require the existing `adminData/{uid}` membership check. Machine tokens
cannot authorize other admin or user-data routes, or any mutation. This
credential does not grant Firebase admin membership or GCP data permissions.

## Deployment configuration

Set these **non-secret GitHub Environment variables** in `prod` (and separately
in `development` only if needed):

| Variable                      | Production value                                          |
| ----------------------------- | --------------------------------------------------------- |
| `ADMIN_STATS_READER_SAS`      | `omi-stats-reader@based-hardware.iam.gserviceaccount.com` |
| `ADMIN_STATS_READER_AUDIENCE` | `https://admin.omi.me/api/omi/stats`                      |

The allowlist accepts comma or whitespace separated service-account emails.
Both variables must be nonempty; otherwise machine access is disabled.
`.github/workflows/gcp_admin.yml` passes them as Cloud Run runtime env vars via
the existing `deploy-public-build` action, using its merge update strategy.
They are server-only variables, never `NEXT_PUBLIC_*`, secrets, or build args.
The unprivileged admin scope gate runs before environment admission; source and
workflow changes remain in scope. Deploy with the existing workflow and explicit
`environment=prod`; its browser-accepted candidate promotion remains intact.

The verifier checks signature, Google issuer (`accounts.google.com` or its HTTPS
form), exact audience, actual expiry (without the SDK's clock-skew grace), verified
email, and exact service-account allowlist membership. A shared OAuth2Client caches
Google certificates according to their Cache-Control lifetime. Untrusted issuer
parsing only selects a verifier; it never grants access. Machine decisions emit one
JSON log with `event=admin_stats_machine_auth`, `decision`, `reason`, and path
without query strings. Tokens, claims and SDK error messages are never logged.

## Consumer identity and token acquisition

Create a dedicated reader service account with **no project roles and no keys**.
Grant each approved consumer runtime identity
`roles/iam.serviceAccountOpenIdTokenCreator` **on that reader account only**.
For GKE, keep Workload Identity enabled and the Kubernetes service account mapped
to its Google runtime service account. For Cloud Run, use the attached runtime
service account through the metadata server. Neither needs a key file.

Observed 2026-10-15: Cloud Run `omi-grafana` uses
`208440318997-compute@developer.gserviceaccount.com`; GKE Grafana maps to
`prod-omi-grafana-gsa@based-hardware.iam.gserviceaccount.com` via its Kubernetes
service account `prod-omi-kube-prometheus-stack-grafana` in
`prod-omi-monitoring`. Recheck these before applying IAM. Moving Cloud Run
Grafana to a dedicated runtime account is a separate consumer deployment.

For an operator test, with permission to mint reader ID tokens:

```bash
gcloud auth print-identity-token \
  --impersonate-service-account=omi-stats-reader@based-hardware.iam.gserviceaccount.com \
  --audiences=https://admin.omi.me/api/omi/stats \
  --include-email
```

Capture the output in memory; send it as `Authorization: Bearer <ID token>`.
Never print it in a terminal transcript or put it into logs. Operator permissions
are separate from the runtime grants.

In the existing Python proxy, use ADC (metadata server / GKE Workload Identity)
to call IAM Credentials `generateIdToken` on the dedicated reader:

```python
import google.auth
from google.auth.transport.requests import AuthorizedSession

credentials, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
session = AuthorizedSession(credentials)
reader = "omi-stats-reader@based-hardware.iam.gserviceaccount.com"
response = session.post(
    "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
    + reader + ":generateIdToken",
    json={"audience": "https://admin.omi.me/api/omi/stats", "includeEmail": True},
    timeout=20,
)
response.raise_for_status()
id_token = response.json()["token"]  # memory only; never log response bodies
```

Cache the short-lived token in memory and refresh before its `exp` (for example
five minutes early); retry once on 401 with a fresh token. When running directly
as the reader SA, the metadata server's `service-accounts/default/identity`
endpoint with `audience=...&format=full` can instead issue its own ID token.
The metadata server cannot choose a different reader account: existing Grafana
runtime identities must use the impersonation call above.

Grafana Infinity may consume the proxy's data or a refreshed bearer header. Its
generic OAuth2/JWT option alone does not establish keyless Google OIDC
impersonation. Do not put a private key into Infinity's JWT configuration; use
an integration that obtains a Google-signed ID token through metadata/IAM and
refreshes it. Audience and `includeEmail=true` must match this contract.

Google references: [ID token acquisition](https://docs.cloud.google.com/docs/authentication/get-id-token),
[IAM Credentials generateIdToken](https://docs.cloud.google.com/iam/docs/reference/credentials/rest/v1/projects.serviceAccounts/generateIdToken).

## Revocation and acceptance

Remove the service-account email from `ADMIN_STATS_READER_SAS` in the appropriate
GitHub Environment, then deploy admin with `environment=prod`. The new revision
rejects even previously issued tokens. Clearing the allowlist disables machine
auth without changing human admins. Removing the consumer's IAM minting grant
stops new tokens; already issued tokens remain valid until expiry or allowlist
removal is deployed. Do not delete accounts or keys as part of this rollout.

After deployment, test an impersonated token against a stats GET (200), a
non-stats GET such as `/api/omi/team-members` (401), and a stats POST (401 or the
framework's 405). Check only status codes, never response user data. Watch admin
5xx and instance starts for at least 15 minutes against the preceding 24–48h,
and record the serving revision and rollback image. Consumer datasource cutover
and retirement of the old Grafana Firebase credential belong to the TV session.
