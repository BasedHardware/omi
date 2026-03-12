## CI/CD Auto-Deploy (push to main)

### Python Backend (dev)
- **Trigger**: push to `main` with `backend/**` changes
- **Workflow**: GitHub Actions `gcp_backend_auto_dev.yml`
- **Deploys to**: Cloud Run + GKE (dev environment)
- **Check**: `gh run list --workflow=gcp_backend_auto_dev.yml --limit=3`

### Python Backend (prod) — manual only
- **Never auto-deploys.** Must trigger manually:
  ```bash
  gh workflow run gcp_backend.yml -f environment=prod -f branch=main
  ```

### Mobile App (iOS TestFlight + Android) — Codemagic
- **Trigger**: push to `main` with `app/**` changes
- **Workflow**: `ios-internal-auto` / `android-internal-auto` in `codemagic.yaml`
- **IMPORTANT**: Codemagic **skips** if the build number in `app/pubspec.yaml` is already on TestFlight. After merging `app/**` changes, you **must bump the build number** or no new build will be uploaded:
  ```bash
  # In app/pubspec.yaml, increment the +N build number:
  # version: 1.0.525+760  ->  version: 1.0.525+761
  ```
- **Check**: `curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" "https://api.codemagic.io/builds?appId=66c95e6ec76853c447b8bcbb&limit=5"`

### Desktop App (macOS) — GitHub Actions + Codemagic
- **Trigger**: push to `main` with `desktop/**` changes
- **Step 1**: GitHub Actions `desktop_auto_release.yml` auto-increments version, pushes `v*-macos` tag
- **Step 2**: Codemagic `omi-desktop-swift-release` builds, signs, notarizes, publishes
