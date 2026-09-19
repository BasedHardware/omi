# Omi Integration API SDKs

OpenAPI-generated clients for the **Omi Integration API**.

- Spec: [`docs/api-reference/integration-public-openapi.json`](../../docs/api-reference/integration-public-openapi.json)
- Base URL: `https://api.omi.me`
- Auth: `Authorization: Bearer <integration_api_key>`
- Client config always includes your `app_id`

## Languages

| Lang | Path | Package |
|------|------|---------|
| TypeScript | [`typescript/`](typescript/) | `@basedhardware/omi-integration` |
| Go | [`go/`](go/) | `github.com/BasedHardware/omi/sdks/integration/go` |
| Python | [`python/`](python/) | `omi-integration` |
| Rust | [`rust/`](rust/) | `omi-integration` |
| C++ | [`cpp/`](cpp/) | CMake target `omi_integration` |
| Dart / Flutter | [`dart/`](dart/) | `omi_integration` |
| React Native | use [`typescript/`](typescript/) | same package — `fetch` works in RN |

## Regenerate

```bash
python backend/scripts/generate_integration_sdks.py
python backend/scripts/generate_integration_sdks.py --check   # CI
# or
sdks/integration/scripts/generate.sh
```

## Methods

| Method | HTTP | Path | Summary |
|--------|------|------|---------|
| `send_notification_v1` | `POST` | `/v1/integrations/notification` | Send App Notification To User |
| `list_conversations` | `GET` | `/v2/integrations/{app_id}/conversations` | Get Conversations Via Integration |
| `list_memories` | `GET` | `/v2/integrations/{app_id}/memories` | Get Memories Via Integration |
| `send_notification` | `POST` | `/v2/integrations/{app_id}/notification` | Send Notification Via Integration |
| `search_conversations` | `POST` | `/v2/integrations/{app_id}/search/conversations` | Search Conversations Via Integration |
| `list_tasks` | `GET` | `/v2/integrations/{app_id}/tasks` | Get Tasks Via Integration |
| `create_conversation` | `POST` | `/v2/integrations/{app_id}/user/conversations` | Create Conversation Via Integration |
| `create_memories` | `POST` | `/v2/integrations/{app_id}/user/memories` | Create Memories Via Integration |

## Use the OpenAPI spec yourself

Any OpenAPI generator can target the same spec:

```bash
# examples
openapi-generator-cli generate -i docs/api-reference/integration-public-openapi.json -g typescript-fetch -o /tmp/omi-ts
oapi-codegen -package omiintegration docs/api-reference/integration-public-openapi.json
```

## Quickstarts

### TypeScript

```ts
import { OmiIntegrationClient } from '@basedhardware/omi-integration';

const client = new OmiIntegrationClient({
  apiKey: process.env.OMI_INTEGRATION_API_KEY!,
  appId: process.env.OMI_APP_ID!,
});

const memories = await client.listMemories(uid);
```

### Go

```go
client := omiintegration.New(os.Getenv("OMI_INTEGRATION_API_KEY"), os.Getenv("OMI_APP_ID"))
raw, err := client.ListMemories(ctx, uid, nil)
```

### Python

```python
from omi_integration import OmiIntegrationClient

with OmiIntegrationClient(api_key, app_id) as client:
    memories = client.list_memories(uid)
```

### Rust

```rust
let client = omi_integration::OmiIntegrationClient::new(api_key, app_id)?;
let memories = client.list_memories(uid, None, None)?;
```

### C++

```cpp
omi::integration::Client client(api_key, app_id);
auto memories = client.list_memories(uid);
```

### Dart / Flutter

```dart
final client = OmiIntegrationClient(apiKey: apiKey, appId: appId);
final memories = await client.listMemories(uid: uid);
```

### React Native

Use the TypeScript client (`@basedhardware/omi-integration`). No separate RN package —
global `fetch` is enough.
