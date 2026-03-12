---
name: firebase
description: Connect to OMI Firebase backend to query user data, analytics, and authentication
allowed-tools: Bash, Read
disable-model-invocation: false
argument-hint: "[query-type]"
---

# Firebase Connection Skill

Connect to the OMI Firebase backend to query user data, analytics, and authentication info.

## Credentials

- **Service Account**: `/Users/matthewdi/omi/backend/google-credentials.json`
- **Project ID**: `based-hardware`
- **Backend venv**: `/Users/matthewdi/omi/backend/venv`

## Quick Connect

```bash
cd /Users/matthewdi/omi/backend && source venv/bin/activate && python3 -u -c "
import firebase_admin
from firebase_admin import credentials, firestore, auth

cred = credentials.Certificate('google-credentials.json')
try:
    firebase_admin.initialize_app(cred)
except ValueError:
    pass

db = firestore.client()
print('Connected to Firebase: based-hardware')

# YOUR QUERY HERE
"
```

## Common Queries

### Count Total Users
```python
total = sum(1 for _ in db.collection('users').select([]).stream())
print(f'Total users: {total:,}')
```

### Get User by UID
```python
user = auth.get_user('USER_UID_HERE')
print(f'Email: {user.email}')
print(f'Providers: {[p.provider_id for p in user.provider_data]}')
```

### List Firestore Collections
```python
for coll in db.collections():
    print(f'- {coll.id}')
```

### Auth Provider Stats
```python
from collections import defaultdict
provider_counts = defaultdict(int)
for user in auth.list_users(max_results=1000).users:
    for p in (user.provider_data or []):
        provider_counts[p.provider_id] += 1
for provider, count in sorted(provider_counts.items(), key=lambda x: -x[1]):
    print(f'{provider}: {count}')
```

## Firestore Structure

### Top-Level Collections
- `users` - User profiles
- `plugins` - App plugins
- `analytics` - Usage analytics
- `adminData` - Admin users

### User Subcollections (`users/{uid}/...`)
| Collection | Key Fields | Notes |
|------------|------------|-------|
| `conversations` | `source`, `created_at`, `structured` | `source` = platform (omi, desktop, phone) |
| `action_items` | `description`, `completed`, `due_at` | No platform tracking |
| `fcm_tokens` | `token`, `created_at` | Doc ID prefix = platform (ios_, android_, macos_) |
| `memories` | `content`, `category` | Extracted memories |
| `daily_summaries` | `overview`, `highlights` | Daily summaries |
| `folders` | `name`, `color` | Conversation folders |

## Platform Detection

### From FCM Tokens (fastest)
```python
from collections import defaultdict
platform_users = defaultdict(set)
for user in db.collection('users').limit(2000).stream():
    for tok in user.reference.collection('fcm_tokens').stream():
        platform = tok.id.split('_')[0] if '_' in tok.id else 'unknown'
        platform_users[platform].add(user.id)
for p, users in sorted(platform_users.items(), key=lambda x: -len(x[1])):
    print(f'{p}: {len(users)} users')
```

### From Conversation Source
```python
# Note: Slow - requires scanning users
for user in db.collection('users').limit(100).stream():
    convos = list(user.reference.collection('conversations').where('source', '==', 'desktop').limit(1).stream())
    if convos:
        print(f'Desktop user: {user.id}')
```

## Redis Connection
```python
import redis
r = redis.Redis(
    host='redis-13151.c1.us-central1-2.gce.redns.redis-cloud.com',
    port=13151,
    password=os.environ['REDIS_PASSWORD'],  # set in .env
    decode_responses=True
)
print(f'Redis connected: {r.ping()}')
```

## Known Limitations
- Firestore subcollection queries are SLOW (1 API call per user)
- No collection group index on `conversations.source`
- Use `limit()` when sampling large datasets
- For analytics, recommend BigQuery export
