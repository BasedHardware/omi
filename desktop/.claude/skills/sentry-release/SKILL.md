---
name: sentry-release
description: Check Sentry errors for the latest release. Shows only NEW issues (regressions), not carryover from old versions. Use when user asks about errors, crashes, Sentry, or release health.
allowed-tools: Bash, Read
---

# Sentry Release Health

Check what errors exist in the latest (or a specific) release. **By default, only shows NEW issues first seen in that release** — never carryover from older versions.

## Quick Start

```bash
# New issues in the latest release (DEFAULT — use this)
./scripts/sentry-release.sh

# New issues in a specific version
./scripts/sentry-release.sh --version 0.8.9

# Also show carryover issues (all issues active in the release)
./scripts/sentry-release.sh --all

# Check quota/billing status
./scripts/sentry-release.sh --quota
```

## IMPORTANT: Default Behavior

- **ALWAYS default to `firstRelease` queries** — these show only issues introduced in the release
- **NEVER show carryover issues by default** — old issues from v0.8.3 firing in v0.8.9 are noise
- Only show carryover (`--all`) if the user explicitly asks for "all issues" or "everything"

## How It Works

- `firstRelease:com.omi.computer-macos@VERSION+BUILD` — issues first seen in this exact release (true regressions)
- `release:com.omi.computer-macos@VERSION*` — any issue that had events in this release (includes carryover)
- The script auto-detects the latest version from `CHANGELOG.json`
- Build number format: `major*10000 + minor*1000 + patch` (e.g., 0.8.9 → 8009)

## Sentry API Reference

```bash
# Load credentials
source .env  # SENTRY_AUTH_TOKEN, SENTRY_ORG=mediar-n5, SENTRY_PROJECT=omi-computer

# Release identifier format
# com.omi.computer-macos@{VERSION}+{BUILD}
# Example: com.omi.computer-macos@0.8.9+8009

# New issues only (DEFAULT)
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/projects/$SENTRY_ORG/$SENTRY_PROJECT/issues/?query=firstRelease:com.omi.computer-macos%40{VERSION}%2B{BUILD}&sort=freq&limit=25"

# All issues in a release (carryover included, only when asked)
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/projects/$SENTRY_ORG/$SENTRY_PROJECT/issues/?query=release:com.omi.computer-macos%40{VERSION}*&sort=freq&limit=25"

# Release metadata (creation date, first/last event, new groups count)
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/projects/$SENTRY_ORG/$SENTRY_PROJECT/releases/com.omi.computer-macos%40{VERSION}%2B{BUILD}/"

# Event volume (hourly, last 48h)
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/projects/$SENTRY_ORG/$SENTRY_PROJECT/stats/?stat=received&resolution=1h&since=$(python3 -c 'import time; print(int(time.time()) - 2*86400)')"

# Quota check (received vs rejected vs blacklisted)
for stat in received rejected blacklisted; do
  curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
    "https://sentry.io/api/0/projects/$SENTRY_ORG/$SENTRY_PROJECT/stats/?stat=$stat&resolution=1d&since=$(python3 -c 'import time; print(int(time.time()) - 7*86400)')"
done

# Org-level outcomes (accepted, rate_limited, filtered, client_discard)
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/organizations/$SENTRY_ORG/stats_v2/?field=sum(quantity)&groupBy=outcome&groupBy=category&interval=1d&start=YYYY-MM-DDT00:00:00&end=YYYY-MM-DDT23:59:59"

# Get latest event for an issue (with breadcrumbs and stack trace)
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/issues/{ISSUE_ID}/events/latest/"

# Get user breakdown for an issue
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/issues/{ISSUE_ID}/tags/user/"

# Get environment breakdown for an issue
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/issues/{ISSUE_ID}/tags/environment/"
```

## Sentry Web UI

- Dashboard: https://mediar-n5.sentry.io/issues/
- Billing: https://mediar-n5.sentry.io/settings/billing/overview/
- Logged in as: matt@mediar.ai

## Key Facts

- Sentry plan: Business ($89/mo) + Pay-as-you-go (currently $600 limit)
- Included errors: 50,000/cycle
- Error price: $0.0011125/error beyond included
- Billing cycle: resets ~7th of each month
- Spike protection is enabled
