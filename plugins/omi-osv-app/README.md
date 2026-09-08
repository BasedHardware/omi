# Omi OSV Advisory Lookup

Two read-only Omi chat tools query the [OSV API](https://google.github.io/osv.dev/) for public package advisories. An exact package/version lookup returns affected ranges, reported fixes and source links across **PyPI, npm, Go, Maven, RubyGems, crates.io, NuGet, Packagist and Pub**. It does not install packages, scan a machine or require an API key.

| Tool | Input | Result |
|---|---|---|
| `query_package_vulnerabilities` | `ecosystem`, `package_name`, exact `version`, optional `limit` (1–10, default 5) | Matching OSV advisory records for that package version |
| `get_vulnerability` | `vulnerability_id` | An OSV record, including affected packages, ranges, reported fixes, withdrawal status and references |

Use the ecosystem's package name, such as `@scope/package` for npm or `group:artifact` for Maven. Supply an exact version, not a range like `>=1` or `^2.0`. Use an ID returned by the first tool for details: a CVE alias is not necessarily a separately retrievable OSV record.

## Run locally

Requires Python 3.11 or newer. From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8080 --no-access-log
```

If your Python installation lacks `venv` support, `uv venv .venv` and `uv pip install --python .venv/bin/python -r requirements-test.txt` are equivalent setup commands.

In a second terminal:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/.well-known/omi-tools.json

curl http://127.0.0.1:8080/tools/query_package_vulnerabilities \
  -H 'Content-Type: application/json' \
  -d '{"ecosystem":"PyPI","package_name":"requests","version":"2.31.0","limit":2}'

curl http://127.0.0.1:8080/tools/get_vulnerability \
  -H 'Content-Type: application/json' \
  -d '{"vulnerability_id":"PYSEC-2023-74"}'
```

The two tool calls use the live OSV API. Results change as its advisory database changes.

## Connect to Omi

This is an independently deployed service, following the [Omi Chat Tools protocol](https://docs.omi.me/doc/developer/apps/ChatTools); it does not modify the legacy plugin monolith.

1. Deploy the service on an HTTPS host you operate. The included `Procfile` runs Uvicorn on `PORT`, defaulting to 8080.
2. In Omi **Apps → Create App**, choose **External Integration**. Set **App Home URL** to the service's HTTPS origin.
3. Set **Chat Tools Manifest URL** to `https://YOUR-HOST/.well-known/omi-tools.json`, then save the app. Omi resolves the relative tool endpoints against App Home URL and fetches the manifest when the app is saved.

Both manifest entries explicitly set `auth_required: false`. The endpoints accept Omi's additional `uid`, `app_id`, `tool_name` and optional `geolocation` fields, but ignore them. Only the explicit public package coordinates or advisory ID are sent to OSV. No Omi identity, location, authorization header or unrelated input is forwarded.

The service follows Omi's [error-handling contract](https://docs.omi.me/doc/developer/apps/ChatTools#error-handling-best-practices): a successful tool response is HTTP 200 with `result`; a failure has `error` and a non-2xx status. Invalid input or an OSV-rejected query returns 400, a missing advisory returns 404, rate limiting returns 429, upstream failure/malformed data returns 502, and timeout returns 504. Omi's caller uses these error statuses to distinguish failed invocations from successful results. Invalid inputs are rejected before making an OSV request. Provider error bodies and transport exception details are not returned to callers.

## Interpret results

- **No matches is not a safety verdict.** OSV cannot distinguish an unknown package/version from one with no indexed advisories. The response says this explicitly.
- Counts refer to **advisory records**, not unique vulnerabilities. Different records can share CVE/GHSA aliases; aliases are included for comparison.
- Package queries display fixes only from matching `affected.package` entries. Detail lookups group ranges by package. A `fixed` marker is a version in an `ECOSYSTEM`/`SEMVER` range or a commit in a `GIT` range. Multiple markers can represent different branches; they are not a universal upgrade recommendation. `last_affected` and `limit` are not labeled as fixes. See the [OSV schema](https://ossf.github.io/osv-schema/) for range semantics.
- Withdrawn records are labeled. Missing fix data means OSV supplied no fix marker, not that no fix exists.
- Each invocation makes **one OSV request**, with a 15-second overall deadline, a 2 MB decoded-response limit and a 20,000-character output limit. Package results show at most 10 records. Pagination, omitted records/packages/ranges and output truncation are disclosed. This is a chat summary, not a complete dependency audit.
- OSV errors, timeouts, malformed responses and missing advisory IDs produce `error`, never a successful empty-match response. HTTPS redirects are not followed.

The application has no database or cache and does not log request bodies or OSV responses. The supplied launch command disables access logs. Only use public package coordinates; hosting providers may have their own request logging policies.

## Tests

After installing `requirements-test.txt`, run:

```bash
PATH="$PWD/.venv/bin:$PATH" bash test.sh
```

`test.sh` runs Python `unittest` using already-installed dependencies. It never installs packages, skips the suite or contacts the network. Tests use FastAPI's real `TestClient`, Pydantic validation and `httpx.MockTransport` to exercise manifest-based invocation, package-scoped fix output, empty/unknown semantics, pagination, withdrawal, input validation, provider failures and response bounds. Omi metadata and exception-body canaries must not leak upstream or into tool responses.

### Repository preflight prerequisites

The repository manifest runs this suite in both local and CI lanes. CI installs the app dependencies when the check is selected. For local `make preflight` or pre-push checks, first complete the repository's normal setup and prepare this app's environment. From the repository root:

```bash
python3 -m venv plugins/omi-osv-app/.venv
plugins/omi-osv-app/.venv/bin/python -m pip install -r plugins/omi-osv-app/requirements-test.txt
export PATH="$PWD/plugins/omi-osv-app/.venv/bin:$PATH"
export PYTHON="$PWD/plugins/omi-osv-app/.venv/bin/python"
make preflight
```

The `uv` setup alternative above also applies, using the repository-relative paths. Supply your PR body as described in the repository contribution guide. Keep this environment selected when pushing so `test.sh` finds FastAPI, HTTPX and Pydantic; the check intentionally does not download dependencies during test execution.

Local HTTP/API validation does not establish that this app is deployed, registered, approved or funded by Omi. Those steps remain separate from this service.

API references: [POST /v1/query](https://google.github.io/osv.dev/post-v1-query/), [GET /v1/vulns](https://google.github.io/osv.dev/get-v1-vulns/).
