---
name: user-issue-triage
description: "End-to-end user issue investigation and resolution. Orchestrates: Sentry crash lookup, PostHog analytics, Firebase user data, codebase investigation, and user email response. Use when a user reports a bug, crash, or issue — whether via Sentry feedback, email, or direct report. Triggers: user email with issue, 'investigate user', 'user complaint', 'user reported', Sentry feedback tasks."
allowed-tools: Bash, Read, Grep, Glob, Task
---

# User Issue Triage

End-to-end workflow for investigating and resolving user-reported issues. Takes a user report (email, Sentry feedback, or direct message) through to root cause analysis, fix, and user notification.

## Workflow

### Step 1: Parse the Issue

Extract from the report:
- **User email** (required for lookups)
- **Issue description** (what the user is experiencing)
- **Sentry issue ID** (if linked from Sentry feedback, e.g., `OMI-COMPUTER-XXXX`)
- **App version** (if mentioned)
- **Timestamp** (when it happened)

If no email is provided, ask for it before proceeding.

### Step 2: Investigate (Run in PARALLEL)

Launch Sentry and PostHog lookups simultaneously using Task agents. Do not run them sequentially.

#### 2a. Sentry Lookup

```bash
./scripts/sentry-logs.sh <email>
```

This auto-filters to the latest version (from `CHANGELOG.json`). Output saved to `local/sentry-logs/`.

For a specific version or all versions:
```bash
./scripts/sentry-logs.sh <email> --version 0.9.9
./scripts/sentry-logs.sh <email> --all-versions
```

If you have a Sentry issue ID, get the latest event directly:
```bash
source .env && curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/issues/<ISSUE_ID>/events/latest/" | python3 -m json.tool
```

- **Sentry org**: `mediar-n5`
- **Sentry project**: `omi-computer`
- **Release format**: `com.omi.computer-macos@{VERSION}+{BUILD}`

#### 2b. PostHog Lookup

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

- **PostHog project**: `302298`
- Check: app version, last activity, event patterns, error events

### Step 3: Firebase User Data (if needed)

Only query Firebase if Sentry/PostHog don't explain the issue (e.g., missing conversations, data sync problems, auth issues).

```bash
cd /Users/matthewdi/omi/backend && source venv/bin/activate && python3 -u -c "
import firebase_admin
from firebase_admin import credentials, firestore, auth

cred = credentials.Certificate('google-credentials.json')
try: firebase_admin.initialize_app(cred)
except ValueError: pass
db = firestore.client()

# Look up user by email
user = auth.get_user_by_email('<email>')
uid = user.uid
print(f'UID: {uid}, Providers: {[p.provider_id for p in user.provider_data]}')

# Check recent conversations
convos = list(db.collection('users').document(uid).collection('conversations').order_by('created_at', direction='DESCENDING').limit(5).stream())
for c in convos:
    d = c.to_dict()
    print(f'  {d.get(\"created_at\", \"?\")} source={d.get(\"source\", \"?\")}')
"
```

### Step 4: Cross-Reference with Codebase

Use the findings from Steps 2-3 to search the codebase for the root cause:
- Match Sentry stack traces to source files
- Search for error messages or relevant code paths
- Check recent commits that may have introduced the bug

### Step 5: Implement Fix or Create Plan

- If the fix is straightforward, implement it
- If it requires more investigation, document findings and propose a plan
- Do NOT run build commands or the app after making changes

### Step 6: Email the User

After resolving (or meaningfully investigating), email the user with results:

```bash
node /Users/matthewdi/omi-analytics/scripts/send-email.js \
  --to "<user-email>" \
  --subject "<brief result summary>" \
  --body "<what was done, what they should expect, any next steps>"
```

**Email tone rules:**
- Write as Matt (first person "I", not "we")
- Casual continuation of conversation — the user already has context
- Concise and direct — share what was done and next steps (e.g., "update the app")
- Only email when there are meaningful results to share

## Environment

All API tokens are in `.env` at the project root:
```
SENTRY_AUTH_TOKEN=...
SENTRY_ORG=mediar-n5
SENTRY_PROJECT=omi-computer
POSTHOG_PERSONAL_API_KEY=phx_...
POSTHOG_PROJECT_ID=302298
```

Default email: `i@m13v.com`

## Related Skills

- **user-logs** — Sentry/PostHog lookup details and API reference
- **sentry-release** — Release health, new vs carryover issues
- **firebase** — Firebase connection and Firestore queries
- **omi-email** — Email sending via Resend API
