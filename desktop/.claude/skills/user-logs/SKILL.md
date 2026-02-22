---
name: user-logs
description: Look up user errors, crashes, and analytics in Sentry and PostHog. Use when debugging issues for a specific user.
allowed-tools: Bash, Read
disable-model-invocation: false
argument-hint: "<email>"
---

# User Logs Lookup Skill

Look up user activity, errors, and analytics across Sentry and PostHog.

**Default email:** `i@m13v.com` (use unless user specifies otherwise)

## Version Filtering (IMPORTANT)

**By default, always filter Sentry queries to the latest released version** unless the user explicitly asks for all versions or a specific older version. This avoids noise from users on old versions with known/fixed issues.

- The latest version is in `CHANGELOG.json` (first entry in `releases` array)
- The Sentry release format is: `com.omi.computer-macos@{VERSION}+{BUILD}` (e.g., `com.omi.computer-macos@0.8.6+8006`)
- Use wildcard to avoid needing the build number: `release:com.omi.computer-macos@0.8.6*`
- The `sentry-logs.sh` script auto-detects the latest version and filters by default

## Prerequisites

Ensure `.env` has these keys:
```bash
SENTRY_AUTH_TOKEN=<token>
SENTRY_ORG=mediar-n5
SENTRY_PROJECT=omi-computer

POSTHOG_PERSONAL_API_KEY=phx_<key>
POSTHOG_PROJECT_ID=302298
```

## Quick Commands

### 1. Sentry Logs (Crashes, Errors, Breadcrumbs)

**Use the existing script:**
```bash
./scripts/sentry-logs.sh <email>                      # defaults to latest version
./scripts/sentry-logs.sh <email> --version 0.8.3      # specific version
./scripts/sentry-logs.sh <email> --all-versions        # no version filter
```

Output saved to: `local/sentry-logs/<email>_<timestamp>.log`

**Direct API query for issues (filtered by version):**
```bash
# Get latest version
VERSION=$(python3 -c "import json; print(json.load(open('CHANGELOG.json'))['releases'][0]['version'])")

# Query issues for the latest version only
source .env && curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/projects/$SENTRY_ORG/$SENTRY_PROJECT/issues/?query=release:com.omi.computer-macos%40${VERSION}*+is:unresolved&sort=freq&limit=25" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for issue in data[:25]:
    print(f\"[{issue.get('shortId')}] {issue.get('count', 'N/A')} events, {issue.get('userCount', 'N/A')} users - {issue.get('title', '')[:60]}\")
"

# Query issues for a specific user on the latest version
source .env && curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/projects/$SENTRY_ORG/$SENTRY_PROJECT/issues/?query=release:com.omi.computer-macos%40${VERSION}*+user.email:<email>&limit=20" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for issue in data[:20]:
    print(f\"[{issue.get('shortId')}] {issue.get('lastSeen', 'N/A')[:16]} - {issue.get('title', '')[:60]}\")
"
```

### 2. PostHog Analytics (Events, Activity)

**Query user events:**
```bash
source .env && curl -s -H "Authorization: Bearer $POSTHOG_PERSONAL_API_KEY" \
  "https://us.posthog.com/api/projects/$POSTHOG_PROJECT_ID/events/?properties=%5B%7B%22key%22%3A%22email%22%2C%22value%22%3A%22<email>%22%2C%22type%22%3A%22person%22%7D%5D&orderBy=%5B%22-timestamp%22%5D&limit=50"
```

**HogQL Query (more powerful):**
```bash
source .env && curl -s -X POST \
  -H "Authorization: Bearer $POSTHOG_PERSONAL_API_KEY" \
  -H "Content-Type: application/json" \
  "https://us.posthog.com/api/projects/$POSTHOG_PROJECT_ID/query/" \
  -d '{
    "query": {
      "kind": "HogQLQuery",
      "query": "SELECT any(person.properties.email) as email, countIf(event = '\''App Launched'\'') as launches, max(timestamp) as last_seen, any(properties.$app_version) as version, groupArray(event) as events FROM events WHERE person.properties.email = '\''<email>'\'' AND timestamp > now() - INTERVAL 7 DAY"
    }
  }'
```

### 3. Node.js Script for Full User Report

Save to `/tmp/user_report.js` and run with `node /tmp/user_report.js <email>`:

```javascript
const email = process.argv[2];
if (!email) { console.error('Usage: node user_report.js <email>'); process.exit(1); }

const POSTHOG_API_KEY = process.env.POSTHOG_PERSONAL_API_KEY;
const POSTHOG_PROJECT_ID = process.env.POSTHOG_PROJECT_ID || '302298';

async function main() {
  const afterDate = new Date();
  afterDate.setDate(afterDate.getDate() - 7);
  const afterDateStr = afterDate.toISOString().split('T')[0];

  const query = `
    SELECT
      any(person.properties.email) as email,
      countIf(event = 'App Launched' OR event = 'First Launch') as launch_count,
      countIf(event = 'Memory Created' OR event = 'Conversation Created') as activity_count,
      max(timestamp) as last_activity,
      any(properties.$app_version) as app_version,
      groupArray(event) as all_events
    FROM events
    WHERE person.properties.email = '${email}'
      AND timestamp > toDateTime('${afterDateStr}')
  `;

  const response = await fetch(`https://us.posthog.com/api/projects/${POSTHOG_PROJECT_ID}/query/`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${POSTHOG_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query: { kind: 'HogQLQuery', query } }),
  });

  if (!response.ok) {
    console.log('Error:', response.status, await response.text());
    return;
  }

  const data = await response.json();
  console.log(`=== User Report for ${email} ===`);
  if (data.results && data.results.length > 0) {
    const [em, launches, activity, lastSeen, version, events] = data.results[0];
    console.log('Email:', em);
    console.log('App Launches:', launches);
    console.log('Activities:', activity);
    console.log('Last Activity:', lastSeen);
    console.log('App Version:', version);

    const eventCounts = {};
    events.forEach(e => { eventCounts[e] = (eventCounts[e] || 0) + 1; });
    console.log('\nEvent breakdown:');
    Object.entries(eventCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 15)
      .forEach(([e, c]) => console.log('  ' + c + 'x ' + e));
  }
}

main().catch(console.error);
```

## What Each Tool Shows

| Tool | What It Shows | Best For |
|------|---------------|----------|
| **Sentry** | Crashes, errors, breadcrumbs, memory warnings | Debugging crashes, finding error patterns |
| **PostHog** | Events, feature usage, app versions, user journey | Understanding behavior, feature adoption |

## Common Queries

### Check if user has launched app recently
```sql
-- HogQL
SELECT max(timestamp), any(properties.$app_version)
FROM events
WHERE person.properties.email = 'user@example.com'
  AND event IN ('App Launched', 'First Launch')
  AND timestamp > now() - INTERVAL 7 DAY
```

### Find users with specific errors (Sentry, latest version)
```bash
VERSION=$(python3 -c "import json; print(json.load(open('CHANGELOG.json'))['releases'][0]['version'])")
source .env && curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/projects/$SENTRY_ORG/$SENTRY_PROJECT/issues/?query=release:com.omi.computer-macos%40${VERSION}*+ScreenCaptureKit&statsPeriod=24h"
```

### Get user's feature status (PostHog)
```sql
-- HogQL
SELECT
  countIf(event = 'Monitoring Started') as monitoring,
  countIf(event = 'Memory Created') as memories,
  countIf(event = 'Phone Mic Recording Started') as transcription
FROM events
WHERE person.properties.email = 'user@example.com'
  AND timestamp > now() - INTERVAL 30 DAY
```

## API Notes

- **Sentry Auth:** Bearer token in Authorization header
- **PostHog Auth:** Bearer token with `phx_` prefix
- **PostHog limitations:** The Personal API Key does NOT have `user:read` scope, so `/users/@me` and similar endpoints will fail. Use HogQL queries instead.
- **PostHog API URL:** `https://us.posthog.com/api/projects/302298/`

## Related Resources

- Omi-analytics project: `/Users/matthewdi/Omi-analytics/src/lib/posthog.ts` has comprehensive PostHog query functions
- Sentry scripts: `./scripts/sentry-logs.sh`, `./scripts/sentry-feedback.sh`
- PostHog script: `./scripts/posthog_query.py`
