# Agent macOS Desktop Prod Promotion Runbook

This runbook is for agents preparing an Omi macOS Desktop beta/dev release for stable/prod promotion. It consolidates the repo-facing process only: release discovery, stable-rollup release-log creation, backend coupling assessment, approval shape, workflow dispatch, and deterministic post-promotion checks.

Do **not** put external promotion readiness here. Fleet health/readiness checks are performed separately before approval.

## Hard rules

- Do not promote, deploy, mutate release metadata, clear caches, edit Firestore, or shift traffic until David explicitly approves the exact current plan.
- Stable promotion is macOS Desktop only. It does not deploy mobile.
- Stable promotion is roll-forward-oriented. Recovery usually means promoting a newer fixed desktop release or performing a separately approved manual infrastructure rollback.
- Do not manually edit a GitHub desktop release to stable. The promotion workflow owns stable release metadata and Firestore promotion.
- Do not use hotfix/cherry-pick branches for normal desktop rollouts. Use the latest eligible mainline `v*-macos` artifact.
- When promoting the release that ships the desktop-agent-platonic branch, record the concrete ship+2 burn version numbers for gap-closure G6 (legacy shims, `legacy_default` grant source, sqlite legacy columns) in the release notes or a maintainer tracking issue.

## 1. Discover release state

Run from the repo root:

```bash
git fetch origin main --tags --prune
gh release list --repo BasedHardware/omi --limit 20
git tag -l 'v*-macos' --sort=-v:refname | head -20
curl -fsS https://api.omi.me/v2/desktop/appcast.xml
```

Identify and report:

- current stable appcast version/build/tag;
- current beta/dev appcast version/build/tag;
- newest `v*-macos` tag;
- newest published GitHub macOS release;
- whether a newer auto-release or Codemagic build is currently in flight.

A tag is eligible only after Codemagic has published the immutable ZIP/DMG candidate and `bless-release.sh` has completed T2 qualification and promoted its explicit beta pointer. If the newest tag is still a candidate, queued, building, or unblessed, hold and report it as not ready.

## 2. Verify release artifact alignment

For the target tag:

```bash
RELEASE_TAG='vX.Y.Z+BUILD-macos'
SHA=$(git rev-list -n1 "$RELEASE_TAG")

gh api "repos/BasedHardware/omi/commits/$SHA/check-runs" \
  --jq '.check_runs[] | select(.name=="Release OMI Desktop (Swift)") | {name,status,conclusion,started_at,completed_at,details_url,html_url}'

gh release view "$RELEASE_TAG" \
  --repo BasedHardware/omi \
  --json tagName,name,publishedAt,isDraft,isPrerelease,url,assets,body
```

Confirm:

- Codemagic `Release OMI Desktop (Swift)` is completed/success;
- Codemagic ran `Smoke signed desktop artifact` before `Create GitHub release`;
- Codemagic uploaded `desktop-smoke-result.json`, and its tag/version/build/artifact digests match the release assets;
- GitHub Release exists and is not draft;
- assets include `Omi.zip` and `omi.dmg`;
- release body has `isLive: true`, `channel: beta`, and an `edSignature`;
- release metadata includes `blessed: true`, `blessedTier: 2`, `blessedSha` matching the tag commit, `blessedAt`, and a published `blessedEvidence` asset;
- live appcast beta/dev item points to the same build.

For high-risk desktop auth/runtime releases, run the live signed-artifact canary
before promotion:

```bash
desktop/macos/scripts/smoke-signed-desktop-artifact.sh \
  --zip /path/to/Omi.zip \
  --dmg /path/to/omi.dmg \
  --tag "$RELEASE_TAG" \
  --expected-channel beta \
  --launch --network --auth --chat --permissions --storage --quarantine \
  --result-json /tmp/desktop-live-smoke-result.json
```

The live canary intentionally requires explicit environment:
`OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH=1` and
`OMI_SIGNED_ARTIFACT_SMOKE_AUTH_PROOF_COMMAND='...'`. The auth proof command
must verify the launched app's real persistence path (Keychain write/read,
restart, and authenticated API), not only curl an API with an injected bearer
token. `OMI_SIGNED_ARTIFACT_SMOKE_AUTH_HEADER='Bearer ...'` is only for the
separate minimal chat endpoint probe.

Beta exposure is gated: Codemagic uploads a non-live candidate, the signed-artifact
smoke runs against that digest, `bless-release.sh` rebuilds the exact tag and runs
the T2 harness, and only the beta promotion workflow can advance visibility.
For stable promotion, add an upgrade-path canary: previous signed release signed
in → update to candidate → restart → auth, helper runtime, and local storage
still work.

## 3. Build the curated stable release log

The per-build changelog is automatic, but stable promotion can span many beta/dev patch builds. Before approval, build a curated stable release log from the current stable appcast build to the target beta/dev build.

Inputs:

- current stable appcast build/tag;
- target beta/dev build/tag;
- `desktop/macos/changelog/releases/*.json` entries between those versions;
- GitHub release bodies only when changelog files are missing or need clarification.

Suggested raw aggregation:

```bash
python3 - <<'PY'
import json
import re
from pathlib import Path

FROM_PATCH = 508   # first patch after current stable, update per rollout
TO_PATCH = 596     # target patch, update per rollout

for path in sorted(Path('desktop/macos/changelog/releases').glob('0.11.*.json')):
    match = re.match(r'0\.11\.(\d+)\.json$', path.name)
    if not match:
        continue
    patch = int(match.group(1))
    if FROM_PATCH <= patch <= TO_PATCH:
        data = json.loads(path.read_text())
        print(f"## {data['version']} ({data['date']})")
        for change in data.get('changes', []):
            print(f"- {change}")
PY
```

Curate the final stable release log into these buckets:

- **Headline**: one sentence naming the release theme.
- **Integrations and connectors**: ChatGPT, Claude, Gmail, Google Calendar, Apple Notes, Hermes, OpenClaw, local MCP, wearable/device status.
- **Memory and data reliability**: memory import, legacy memory decode, memory-bank setup, cache consistency.
- **Voice, recording, and Rewind**: push-to-talk, realtime voice, recording reconciliation, screenshot/rewind fixes.
- **Auth, update, and runtime reliability**: sign-in/OAuth, updater recovery, agent runtime packaging, keychain/device identity.
- **UI polish and usability**: notch/floating bar, menus, labels, guidance cards.
- **Known caveats / operator notes**: backend dependencies, fail-closed behavior, rollout caveats.

Include this curated log in the approval plan. Do not rely on the target release's per-build notes alone when the target spans multiple beta/dev builds since stable.

## 4. Decide shared backend coupling

Desktop promotion always deploys the **Rust `desktop-backend`** from the exact `v*-macos` tag via `desktop_promote_prod.yml`.

The **shared Python backend** is separate (`gcp_backend.yml`). It is not always required, but many desktop capabilities are coupled to shared backend routes, schemas, OAuth clients, feature flags, or response contracts.

Before approval, classify shared backend as:

```text
backend_required: yes | no | optional
reason:
  - desktop feature or PR
  - backend endpoint/schema/env needed
  - whether current prod backend already contains it
phase:
  - before desktop promotion | after desktop promotion | not needed
```

Use concrete evidence:

```bash
# Current prod backend image/revisions, read-only
python3 backend/scripts/deploy_status_report.py \
  --env prod \
  --project based-hardware \
  --region us-central1 \
  --include-cloud-run \
  --include-gke \
  --cloud-run-service backend \
  --cloud-run-service backend-sync \
  --cloud-run-service backend-integration \
  --cloud-run-service desktop-backend \
  --gke-service backend-listen \
  --gke-service pusher

# Compare desktop target against current prod backend source when known.
git log --oneline --first-parent <current-prod-backend-sha>..<target-tag> -- backend pusher parakeet modal llm_gateway agent-proxy
```

Rules of thumb:

- If the desktop app fail-closes against older backend behavior and the new capability is non-critical, backend may be optional.
- If a desktop flow relies on a new endpoint, query parameter echo, response field, OAuth client, runtime env, or server-side policy, backend is required for full capability.
- If backend is required, propose it as a separately approved phase. Do not dispatch `gcp_backend.yml` without explicit approval.

## 5. Present approval plan

Before any mutation, present:

- target release tag/build/version;
- why it is the latest eligible candidate;
- current stable and beta/dev appcast state;
- Codemagic/GitHub/appcast alignment;
- curated stable release log;
- backend coupling decision and proposed phase;
- risks and caveats;
- exact command(s) proposed;
- post-promotion verification commands;
- roll-forward/rollback plan.

End with an explicit confirmation question naming the exact tag and phase(s).

## 6. Execute only approved workflows

Desktop stable promotion:

```bash
RELEASE_TAG='vX.Y.Z+BUILD-macos'

gh workflow run desktop_promote_prod.yml \
  --repo BasedHardware/omi \
  -f release_tag="$RELEASE_TAG" \
  -f confirm='promote-stable'
```

Optional shared backend deploy, only if separately approved:

```bash
gh workflow run gcp_backend.yml \
  --repo BasedHardware/omi \
  -f environment=prod \
  -f branch=main
```

## 7. Monitor and verify deterministic outcomes

Monitor desktop promotion:

```bash
gh run list --repo BasedHardware/omi --workflow desktop_promote_prod.yml --limit 5
gh run watch --repo BasedHardware/omi <run-id> --exit-status
```

After success:

```bash
curl -fsS https://desktop-backend-hhibjajaja-uc.a.run.app/health | python3 -m json.tool
curl -fsS https://api.omi.me/v2/desktop/appcast.xml
gh release view "$RELEASE_TAG" \
  --repo BasedHardware/omi \
  --json tagName,body,isDraft,isPrerelease,url
```

Verify:

- stable appcast item is the promoted build;
- GitHub Release body/channel is stable;
- release is not draft;
- `desktop-backend` health identity matches the promoted tag/SHA when supported;
- any separately approved backend deploy reports expected revisions and traffic.

Then run the external readiness/regression process separately and report results.
