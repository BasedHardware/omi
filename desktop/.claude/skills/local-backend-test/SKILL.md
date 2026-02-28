---
name: local-backend-test
description: Test the local Rust backend API with authenticated requests. Gets a Firebase ID token and calls endpoints on localhost:8080.
allowed-tools: Bash, Read
disable-model-invocation: false
argument-hint: "[endpoint] e.g. GET /v1/action-items?deleted=true"
---

# Local Backend Test Skill

Test the local Rust backend at `http://localhost:8080` with a real Firebase ID token.

## How It Works

The backend requires a valid Firebase ID token. This skill:
1. Creates a Firebase custom token via Admin SDK
2. Exchanges it for an ID token via Firebase Auth REST API
3. Calls the local backend with the ID token

## Default User

- **UID**: `bdYYRztuRfheEcjSxMdYnDyDeF13` (Matthew, i@m13v.com)

## Get a Firebase ID Token

```bash
cd /Users/matthewdi/omi/backend && source venv/bin/activate && python3 -u -c "
import firebase_admin, requests, json
from firebase_admin import credentials, auth

cred = credentials.Certificate('google-credentials.json')
try: firebase_admin.initialize_app(cred)
except ValueError: pass

uid = 'bdYYRztuRfheEcjSxMdYnDyDeF13'
custom_token = auth.create_custom_token(uid)
token_str = custom_token.decode() if isinstance(custom_token, bytes) else custom_token

# Exchange for ID token
resp = requests.post(
    'https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8',
    json={'token': token_str, 'returnSecureToken': True}
)
if resp.status_code == 200:
    print(resp.json()['idToken'])
else:
    print(f'ERROR: {resp.status_code} {resp.text}', file=__import__('sys').stderr)
    exit(1)
"
```

## One-Liner: Get Token + Call Endpoint

Replace `ENDPOINT` with the desired path (e.g., `/v1/action-items?deleted=true`):

```bash
cd /Users/matthewdi/omi/backend && source venv/bin/activate && TOKEN=$(python3 -u -c "
import firebase_admin, requests
from firebase_admin import credentials, auth
cred = credentials.Certificate('google-credentials.json')
try: firebase_admin.initialize_app(cred)
except ValueError: pass
ct = auth.create_custom_token('bdYYRztuRfheEcjSxMdYnDyDeF13')
ts = ct.decode() if isinstance(ct, bytes) else ct
r = requests.post('https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8', json={'token': ts, 'returnSecureToken': True})
print(r.json()['idToken'])
" 2>/dev/null) && curl -s "http://localhost:8080/ENDPOINT" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

## Common Test Calls

### Health Check (no auth)
```bash
curl -s http://localhost:8080/health
```

### GET Action Items
```bash
curl -s "http://localhost:8080/v1/action-items?limit=5" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### GET Deleted Action Items
```bash
curl -s "http://localhost:8080/v1/action-items?deleted=true" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### GET Conversations
```bash
curl -s "http://localhost:8080/v1/conversations?limit=5" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### GET Memories
```bash
curl -s "http://localhost:8080/v3/memories?limit=5" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

## Configuration

- **Backend URL**: `http://localhost:8080` (started via `Backend-Rust/run.sh`)
- **Tunnel URL**: `https://omi-dev.m13v.com` (Cloudflare tunnel, also started by run.sh)
- **Firebase Project**: `based-hardware`
- **API Key**: `AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8`
- **Credentials**: `/Users/matthewdi/omi/backend/google-credentials.json`
- **Backend .env**: `/Users/matthewdi/omi-desktop/Backend-Rust/.env`

## Troubleshooting

- **"Failed to decode token header"**: Token is a custom token, not an ID token. Must exchange via REST API first.
- **401 Unauthorized**: Token expired (1 hour lifetime). Generate a new one.
- **Connection refused**: Backend not running. Start with `cd Backend-Rust && ./run.sh`.
