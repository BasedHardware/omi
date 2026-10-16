# Private Business dashboards on monitor.omi.me

The alerting instance hosts a separate **Omi Business** organization. Grafana OSS
folder permissions do not restrict datasource queries, so the existing monitoring
organization is not a safe home for business-only users/data. Only the
`omi-admin-api` Infinity datasource and `business` folder belong in the Business
org. Keep Prometheus, alert rules and existing CI Editor credentials in their
original org. Organization Admin is the least OSS role that can reconcile folder
ACLs and team membership; runtime and CI have separate Business-scoped accounts.
No server-admin credential reaches either application or CI.

`web/admin/grafana/build_wall_dashboard.py` remains the builder and
`web/admin/grafana/dashboards/omi-tv-v2.json` the single board artifact. The existing
Grafana provisioning workflow reads it directly with a one-file allowlist.
It creates the team/folder, replaces folder permissions with Admin + team View,
removes old explicit dashboard grants, and verifies folder/read-back placement.
Never add Viewer/Editor org grants or publish/anonymous access. The workflow's
prod-only step needs `BUSINESS_GRAFANA_TOKEN` in `monitoring-prod`.

## Keyless datasource

Infinity 4.1.1 and Grafana 13.1.3 are pinned. The board's raw SVG field icons
require 13.x Canvas resource handling; 12.1.7 returns valid query frames but blank
cards ([Canvas resource handling](https://github.com/grafana/grafana/blob/v13.1.3/public/app/features/dimensions/resource.ts)).
Local verification must include visible native cards, not just API200.
The values use `GF_PLUGINS_PREINSTALL_SYNC=id@version`: chart75's legacy
`plugins` key emits `GF_INSTALL_PLUGINS`, ignored by13 unless forced.
The checked-in Python standard-library sidecar binds **127.0.0.1:8899**; it has no
Service or host port. It accepts only GET `/api/omi/stats/wall` (the exact
private-board route; no query strings) and
forwards to the fixed `https://admin.omi.me` origin. It forwards no client headers,
disables redirects/environment proxies, bounds response size/concurrency, and
never logs tokens, URLs or upstream bodies. Successful responses coalesce/cache
for 15 minutes (never across UTC midnight); failures coalesce for five seconds,
release waiting queries and never serve expired success data.
The metadata access token is used only for IAM Credentials `generateIdToken`
on `omi-stats-reader`, audience `https://admin.omi.me/api/omi/stats`, includeEmail.
The ID token stays in memory and refreshes five minutes early, or once on 401.
No service-account key or static bearer is provisioned in Infinity.
Cold wall aggregation includes batched120-second PostHog queries. The isolated
HTTP budgets are360s upstream,420s Infinity,450s for live verification and
480s on the Grafana-only GCE BackendConfig,
matching the existing six-minute web proxy envelope without raising monitoring
datasource/global timeouts. Warm/measure the real wall before enabling the embed;
these deadlines do not prove a cold aggregate finishes within them.

Parent must apply `grafana-stats-proxy` ConfigMap from `stats_proxy.py` and the
bootstrap-generated `grafana-business-runtime` ConfigMap before Helm. Every prod
stack upgrade passes the script's SHA-256 as
`--set-string grafana.podAnnotations.omi-stats-proxy-sha256=<hash>` so a changed
ConfigMap rolls the process. `gcp_cloud_run_metrics_egress.yml` computes that hash
from the checked-out `stats_proxy.py` but never applies the ConfigMap, so apply the
ConfigMap from the same commit before that workflow upgrades prod; otherwise the
annotation names a script the pod is not running. Keep the single Grafana PVC and
current resources/alerts intact.

## Admin embedding

`GET /api/grafana/embed` requires the existing `verifyAdmin` Firebase/adminData
check. Stats-reader machine credentials cannot call it. Server-side Secret
Manager access uses the Cloud Run runtime identity. Fixed signed claims include
issuer/audience/purpose and Business org mapping, with a four-minute lifetime.
Namespaced SHA256 identities and synthetic emails avoid linking to an operator's
Grafana identity. The org-scoped enrollment token adds the JWT-created user to
`business-viewers` before the URL is returned. It verifies org/team/user identity
and never grants Admin via JWT. JWKS publishes only the RSA public key, including while the embed cutover flag
is off, so keys can be staged before Grafana starts.
TV kiosks use the same minting through `POST /api/grafana/tv-embed` after
re-validating a TV share token server-side (`tv:<link>` identity namespace);
flag-off keeps the legacy anonymous board only while it is actually open.

Runtime settings (server only; GitHub `prod` Environment variables):

- `GRAFANA_EMBED_ENABLED=true` enables the cutover. Empty/false preserves the
  existing authenticated native analytics page during prerequisite setup or rollback.
- `GRAFANA_EMBED_SIGNING_SECRET=projects/based-hardware/secrets/omi-grafana-embed-signing/versions/<number>`
  contains JSON `{ "kid": "<rotation-id>", "privateKeyPem": "<RSA PKCS8 PEM>" }`.
- `GRAFANA_BUSINESS_TOKEN_SECRET=projects/based-hardware/secrets/omi-grafana-business-enrollment/versions/<number>`
  contains the bootstrap `runtime.json` (`token`, `orgId`, `teamId`).

Use explicit secret versions, per-secret secretAccessor grants, and RSA >=2048
bits. Never commit keys or paste values in a command. Tokens from bootstrap expire
in 90 days; rotate both CI/runtime bindings before expiry. For signing-key rotation,
disable cutover, wait five minutes for old capabilities to expire, switch both
signing/JWKS to the new version, wait the one-minute Grafana JWKS cache, then enable.
The public JWKS route is not a dashboard/data access path.

Grafana allows embedding, requires secure SameSite=None cookies, and sends CSP
`frame-ancestors https://admin.omi.me` in addition to the pinned Grafana default
nonce/script/object/base/form protections. The iframe suppresses referrers. Token minting fails closed until both legacy Grafana
origins deny anonymous datasource access (401/403). Apply the
Grafana-only BackendConfig before enabling URL login and verify its Compute
backend logging is disabled: query strings contain short-lived bearer tokens.
This does not change project retention, sinks or logging for other backends.

**Renewal:** stock Grafana JWT URL login reuses the original JWT for API calls,
without refresh tokens or a session exchange. Renew sixty seconds before the
returned expiry (about every three minutes), including after tab visibility/focus
resumes. Each renewal reloads the iframe and issues lightweight Infinity queries;
the dashboard's configured interval and upstream stats cache remain 15 minutes.
This prioritizes valid authentication. Continuous interaction without reloads
requires an authenticated reverse proxy instead. Never extend JWTs or enable
anonymous sessions to hide expiry.

Legacy anonymous datasource access must be closed before cutover; deleting the
old board alone is insufficient. The parent has disabled anonymous access on the
legacy service; keep both origins private during rollout and rollback. No new
legacy deployment or compute-identity actAs grant is required. After successful
cutover, `retire_legacy_board.py --apply` can remove only the old v2 board using
the existing legacy token. No data store is deleted.

## Parent-owned production application

`bootstrap_business.py` uses temporary server-admin Basic credentials from the
environment to create/reuse the isolated org/team and its two service accounts.
It writes credentials only to 0600 files in a private output directory and prints
only org/team IDs. Duplicate token receipts fail closed; never retry a partial
bootstrap with a new receipt without inspecting which credentials were created.
`verify_business.py` uses Business Admin and same-org non-member Viewer service-account tokens supplied in
environment variables, exercises Infinity's real wall query, and prints only
status/frame counts. The browser acceptance must use a real signed-in admin and
confirm the native Canvas cards render correctly on Grafana 13.1.3.

Before mutation record the current Helm revision, admin serving image/revision
and baseline windows. Take a cold snapshot of the active Grafana disk with the
workload stopped and disk detached, then restore its recorded replica count.
Save pre-13 release values privately. Restore a failed upgrade from that snapshot
to a new disk/PVC with the recorded 12.x image; retain the migrated original.
Capture rule identity/count/state/health and evaluation timestamps before/after;
any per-rule health change or stalled enabled rule blocks acceptance. Require a
complete observation of at least 15 minutes, extending it for long rule intervals. Review `helm diff upgrade` for chart 75.15.1 with current
values, then upgrade with the same args plus `--wait --timeout 15m`. Parent owns
Helm and privileged Grafana calls. Admin deploys via `gcp_admin.yml` with explicit
`environment=prod`; preserve its candidate/browser acceptance. After applying,
observe at least 15 minutes and compare 5xx/restarts/alert-evaluation health with
the preceding 24–48h. Local tests and HTTP health alone do not establish this.

Rollback the admin via `GRAFANA_EMBED_ENABLED=false` and that same workflow.
Restore the pre-upgrade database snapshot to a new disk/PVC using the recorded
image/values; retain both the original PVC and consistent backup. The 12.1.0 ->13.1.3
upgrade crosses a major version: validate existing alert evaluation, installed
plugins and schema migration, and plan rollback from that backup rather than
assuming an in-place binary downgrade is safe. Disable JWT only after the admin
rollback. Retain secret versions, org and data; do not delete them as rollback.

## Verification

Run focused backend tests through `backend/test.sh` with
`tests/unit/test_grafana_stats_proxy.py` in `BACKEND_UNIT_TEST_FILE_LIST`.
Run `python3 -m unittest discover -s .github/scripts -p test_grafana_business.py`,
`npm --prefix web/admin test -- lib/__tests__/grafana-embed.test.ts`, admin
`typecheck`/`lint`, and `make preflight`. Render chart 75.15.1 and inspect the
loopback sidecar, datasource org substitution, mounts and JWT settings. Live
negative acceptance must deny both folder and dashboard to an ordinary Viewer
outside `business-viewers` in the same Business org; verify the Viewer role and org datasource isolation as well.

References: [JWT URL login](https://grafana.com/docs/grafana/latest/setup-grafana/configure-access/configure-authentication/jwt/),
[datasource access](https://grafana.com/docs/grafana/latest/administration/data-source-management/),
[Team Sync licensing](https://grafana.com/docs/grafana/latest/setup-grafana/configure-access/configure-team-sync/).
