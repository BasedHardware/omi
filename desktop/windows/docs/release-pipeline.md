# Windows release pipeline

The Windows desktop app ships through `.github/workflows/desktop_windows_release.yml`.
It mirrors the macOS auto-release shape (`.github/workflows/desktop_auto_release.yml`):
a merge to `main` cuts a version, tags it, and publishes a beta build — the
difference is Windows has no external CI (no Codemagic), so the same workflow also
builds the installer on a `windows-latest` runner with electron-builder (NSIS).

## What it does

On every push to `main` that touches `desktop/windows/**` (or a manual
`workflow_dispatch`):

1. **plan-and-tag** (Ubuntu)
   - Finds the latest `v*-windows` tag (the version source of truth).
   - Skips if there is no releasable `desktop/windows` change since that tag
     (unless `release_mode: force_release`).
   - Computes the next **patch** version (from the latest tag, or the checked-in
     `package.json` version for the very first release).
   - Stamps `desktop/windows/package.json` to that version, commits it, tags the
     commit `v<version>-windows`, and pushes **the tag** (carrying the bump
     commit to origin — `main` itself is untouched here).
   - Opens a best-effort PR to sync the version bump back to `main`. If `main`
     is protected and the PR cannot auto-merge, the release still succeeded (the
     tag is authoritative) and the PR waits for a manual merge.
2. **build-and-publish** (Windows)
   - Checks out the `v<version>-windows` tag (so `package.json` already has the
     right version).
   - Provisions `.env` from `.env.example` (public Firebase/PostHog config), then
     `pnpm install --frozen-lockfile` (rebuilds `better-sqlite3`, builds the .NET
     OCR/automation helpers).
   - Requires the complete Azure Trusted Signing configuration, builds a signed
     NSIS installer, and verifies both installer and app Authenticode signatures.
     Missing signing configuration fails the release before anything is published.
   - Publishes the installer `.exe`, its `.exe.blockmap` (differential updates),
     and `latest.yml` (the electron-updater feed) to a **prerelease** GitHub
     Release named `Omi for Windows <version> (beta)`, using `gh`.

### electron-builder config (`--config electron-builder.config.mjs`)

The build is configured by `desktop/windows/electron-builder.config.mjs`, a JS
config that computes the pi-mono (`@earendil-works/pi-coding-agent`) `asarUnpack`
closure at pack time — the coding agent is spawned as a plain-Node child and every
package in its runtime closure must be unpacked to disk.

electron-builder only **auto-detects** a config named `electron-builder.<ext>`
(yml/json/js/cjs/mjs/ts); it does **not** auto-detect the `electron-builder.config.*`
name. So every build must pass `--config electron-builder.config.mjs` explicitly —
the signed release path passes it explicitly. Dropping the `--config` flag would silently
drop this whole config (and the pi-mono closure), shipping an installer that breaks
the coding agent. There is intentionally **no** `electron-builder.yml` — the
`.config.mjs` file is the single source of truth.

Every build command must also pass `--publish never` (`build:win` carries it; the
signed path passes it by hand). The config's `publish` block is only the
electron-updater feed pointer, but electron-builder treats it as an upload target
too and auto-publishes whenever it sees CI plus a checked-out git tag — exactly the
release job's situation — then fails on the missing `GH_TOKEN`. Publishing is done
explicitly with `gh release` in the workflow's final step instead.

The NSIS `artifactName` is `Omi-for-Windows-Setup-<version>.exe` (no spaces):
electron-updater downloads the installer by the exact url recorded in `latest.yml`,
and a spaced name url-encodes to a path that no longer matches the uploaded asset —
every auto-update would 404.

### Version & tags

- Tag format: `v<version>-windows` (e.g. `v1.0.1-windows`). The `-windows` suffix
  keeps Windows tags from colliding with the macOS `v*+<build>-macos` tags.
- The git tag is the source of truth. `package.json` is stamped from it at build
  time and synced back to `main` for humans; even if that sync PR never merges,
  the next release still computes correctly from the tag.

### Loop prevention

The bump must not re-trigger the workflow. Three independent guards:

1. Every git write uses `GITHUB_TOKEN`; GitHub does not start new workflow runs
   for pushes made with `GITHUB_TOKEN`.
2. The plan job skips any commit whose message starts with
   `chore(windows): release v`.
3. The plan job skips when there is no releasable `desktop/windows` change since
   the latest tag.

### Auto-update

`electron-updater` (see `src/main/updater.ts`) reads the feed configured in
`electron-builder.config.mjs` (`publish:` → GitHub `BasedHardware/omi`, `releaseType:
release`). Because the workflow marks builds **prerelease**, they are _not_
auto-pushed to installed apps — users download betas manually. Promoting a build
to stable (flipping its GitHub release from prerelease to release) is what makes
`electron-updater` serve it. This matches the macOS beta/stable split.

> The workflow publishes to the repository it runs in (`${{ github.repository }}`),
> so on `BasedHardware/omi` the release lands exactly where the feed points. On a
> fork, betas land on the fork; installed apps still look at `BasedHardware/omi`
> per the committed feed.

## One-time signing setup (owner)

Until these secrets exist the release job fails closed and publishes nothing.
Local development installers may still be unsigned, but every GitHub release
requires Azure Trusted Signing.

### 1. Create an Azure Trusted Signing account

1. In the [Azure Portal](https://portal.azure.com), create a **Trusted Signing
   account** (search "Trusted Signing"). Note the **region** — it determines the
   signing endpoint, e.g. `https://eus.codesigning.azure.net/` (East US).
2. Inside the account, create a **Certificate Profile** (type: _Public Trust_ for
   publicly distributed apps). Complete the identity validation Microsoft
   requires. Note the **profile name**.
3. Note the **account name** (the Trusted Signing account's name).
4. The **publisher name** must match the validated identity on the certificate
   profile (e.g. `Based Hardware`).

### 2. Create an Entra ID (Azure AD) app registration for CI auth

1. Entra ID → **App registrations** → **New registration**. Note the
   **Application (client) ID** and your **Directory (tenant) ID**.
2. **Certificates & secrets** → **New client secret**. Copy the secret **value**.
3. Grant that app the **Trusted Signing Certificate Profile Signer** role on the
   Trusted Signing account (account → Access control (IAM) → Add role assignment).

### 3. Add the GitHub repository secrets

Create these under the repo's **Settings → Secrets and variables → Actions**. The
names must match exactly (the workflow reads these):

| Secret                        | Value                                            | Purpose         |
| ----------------------------- | ------------------------------------------------ | --------------- |
| `AZURE_TENANT_ID`             | Directory (tenant) ID                            | auth            |
| `AZURE_CLIENT_ID`             | Application (client) ID                          | auth            |
| `AZURE_CLIENT_SECRET`         | client secret value                              | auth            |
| `AZURE_CODE_SIGNING_ENDPOINT` | e.g. `https://eus.codesigning.azure.net/`        | signing profile |
| `AZURE_CODE_SIGNING_ACCOUNT`  | Trusted Signing account name                     | signing profile |
| `AZURE_CERT_PROFILE_NAME`     | certificate profile name                         | signing profile |
| `AZURE_PUBLISHER_NAME`        | validated publisher name (e.g. `Based Hardware`) | signing profile |

The release requires **all seven** secrets (the three auth values plus the four
signing-profile values). Add all seven together; a missing or partial set fails
the release before the build or upload.

Once the secrets exist, the next release is signed automatically — no workflow or
`electron-builder.config.mjs` change needed.

## Manual / local

- **Trigger a release by hand:** Actions → _Auto Release Desktop (Windows) on
  Main_ → **Run workflow**. `release_mode: force_release` releases even with no
  new changes; `next_version` pins an explicit version.
- **Build the installer locally** (unsigned): from `desktop/windows/`,
  `pnpm build:win`. Output lands in `dist/` (`Omi-for-Windows-Setup-<version>.exe`,
  its `.blockmap`, and `latest.yml`).
- **If the build job fails after the tag was created:** re-run the **failed jobs
  only** (Actions → the run → "Re-run failed jobs") — that reuses the plan job's
  tag/version outputs and re-publishes to the existing tag. Do _not_ "Re-run all
  jobs": the plan job would see no new change since the just-created tag and skip,
  stranding the tag with no assets. Alternatively, `workflow_dispatch` with
  `release_mode: force_release` cuts a fresh version.

## Public download link (backend-served)

Every release also uploads a canonical `omi-setup.exe` asset (exact lowercase
name — the Windows analog of macOS's `omi.dmg`). The backend resolves it:

- `https://api.omi.me/v2/desktop/download/windows` — latest **stable** Windows
  release (or beta when no stable exists — see fallback below), served as an
  auto-download landing page
- `…/v2/desktop/download/windows?channel=beta` — latest beta (or stable when
  the beta slot is empty)
- `…/v2/desktop/download/latest?platform=windows` — same, but strict (404s
  when the exact channel is empty; QA/tooling contract)

Channel mapping is GitHub's own release state (`backend/routers/updates.py`):
the auto-cut **prerelease is the beta channel**; clearing the prerelease flag
(`gh release edit v<version>-windows --prerelease=false`) **promotes it to
stable** — no KEY_VALUE block needed. Releases marked draft are never served.

Because promotion empties the beta slot until the next cut (and before the
first promotion there is no stable at all), the `/v2/desktop/download/windows`
public-link route falls back to the other channel instead of 404ing, records
it via `record_fallback`, and the landing page shows the channel actually
served. `/v2/desktop/download/latest` keeps strict channel semantics.

### windows.omi.me (live infra)

Both `macos.omi.me` and `windows.omi.me` are Namecheap A records
(`registrar-servers.com` DNS) pointing at the GCP global load balancer
(`34.54.223.100`, project `based-hardware`), covered by its managed
certificate. URL map `custom-domains-49a4` holds one `routeRules` matcher per
host issuing 301 `urlRedirect`s (`pathRedirect` **can** carry a query string):

- `windows.omi.me/` → `api.omi.me/v2/desktop/download/windows`
- `windows.omi.me/beta` → `api.omi.me/v2/desktop/download/windows?channel=beta`
- (`macos.omi.me` mirrors this shape onto `/v2/desktop/download/latest`)

Emergency pin: to serve a known-good installer while the backend or a release
is broken, edit the matcher to redirect to the immutable GitHub asset
(`hostRedirect: github.com`, `pathRedirect:
/BasedHardware/omi/releases/download/v<version>-windows/omi-setup.exe`) — the
shape the links launched with. `gcloud compute url-maps export/import
custom-domains-49a4 --global` is the edit loop; export a backup first.
