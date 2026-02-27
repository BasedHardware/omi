---
name: rust-endpoint
description: "Scaffold new Rust backend API endpoints with corresponding Swift client methods. Use when adding a new API route, endpoint, or backend service. Triggers: 'add endpoint', 'new API', 'add route', 'backend endpoint', 'wire up API'."
---

# Rust Endpoint

## Overview

Scaffold a new Rust API endpoint (Axum) with the corresponding Swift client method in the OMI Desktop app. Every new feature follows the same file-by-file pattern.

## Workflow

### Step 1 — Explore existing patterns

Before writing anything, read the nearest existing example to match conventions:

- **Routes**: `Backend-Rust/src/routes/` — one file per resource (e.g., `memories.rs`, `goals.rs`)
- **Models**: `Backend-Rust/src/models/` — request/response structs (e.g., `memory.rs`, `goal.rs`)
- **Services**: `Backend-Rust/src/services/firestore.rs` — Firestore data access methods
- **Route registration**: `Backend-Rust/src/routes/mod.rs` — module declaration + `pub use`
- **Main router**: `Backend-Rust/src/main.rs` — where route sets are `.merge()`'d
- **Swift client**: `Desktop/Sources/APIClient.swift` — all API calls live here as extensions

### Step 2 — Add models (`Backend-Rust/src/models/`)

Create a new file (e.g., `my_feature.rs`) or add to an existing one.

```rust
use serde::{Deserialize, Serialize};

// REQUEST
#[derive(Debug, Clone, Deserialize)]
pub struct CreateThingRequest {
    pub name: String,
    pub value: Option<String>,
}

// RESPONSE
#[derive(Debug, Clone, Serialize)]
pub struct ThingStatusResponse {
    pub status: String,
}

// DB MODEL (if stored in Firestore)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThingDB {
    pub id: String,
    pub uid: String,
    pub name: String,
    pub created_at: chrono::DateTime<chrono::Utc>,
}
```

Then register in `Backend-Rust/src/models/mod.rs`:

```rust
pub mod my_feature;
pub use my_feature::{CreateThingRequest, ThingStatusResponse, ThingDB};
```

### Step 3 — Add service logic (`Backend-Rust/src/services/firestore.rs`)

Add an `impl FirestoreService` method for each data operation. Follow the existing pattern of returning `Result<T, Box<dyn std::error::Error + Send + Sync>>`:

```rust
pub async fn create_thing(&self, uid: &str, name: &str) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let doc_id = uuid::Uuid::new_v4().to_string();
    // ... Firestore REST API calls ...
    Ok(doc_id)
}
```

### Step 4 — Add route handler (`Backend-Rust/src/routes/`)

Create a new file (e.g., `my_feature.rs`). Key conventions:

```rust
use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{delete, get, patch, post},
    Json, Router,
};

use crate::auth::AuthUser;       // <-- extracts Firebase UID from Bearer token
use crate::models::{CreateThingRequest, ThingStatusResponse};
use crate::AppState;

/// POST /v3/things - Create a thing
async fn create_thing(
    State(state): State<AppState>,  // shared app state (firestore, redis, config)
    user: AuthUser,                 // auto-extracts & validates Firebase token
    Json(request): Json<CreateThingRequest>,
) -> Result<Json<ThingStatusResponse>, StatusCode> {
    tracing::info!("Creating thing for user {}", user.uid);

    match state.firestore.create_thing(&user.uid, &request.name).await {
        Ok(_id) => Ok(Json(ThingStatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to create thing: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

// Public function that returns the Router for this resource
pub fn my_feature_routes() -> Router<AppState> {
    Router::new()
        .route("/v3/things", get(list_things).post(create_thing))
        .route("/v3/things/:id", get(get_thing).delete(delete_thing).patch(update_thing))
}
```

### Step 5 — Wire the route

**`Backend-Rust/src/routes/mod.rs`** — add two lines:

```rust
pub mod my_feature;
pub use my_feature::my_feature_routes;
```

**`Backend-Rust/src/main.rs`** — add to the import and router:

```rust
// In the `use routes::{ ... }` import:
use routes::{ ..., my_feature_routes };

// In the main_router builder:
.merge(my_feature_routes())
```

### Step 6 — Add Swift client method

Add an extension on `APIClient` in `Desktop/Sources/APIClient.swift`:

```swift
// MARK: - My Feature API

extension APIClient {

    func createThing(name: String) async throws -> ThingStatusResponse {
        struct CreateThingRequest: Encodable {
            let name: String
        }
        let body = CreateThingRequest(name: name)
        return try await post("v3/things", body: body)
    }

    func getThings() async throws -> [ThingDB] {
        return try await get("v3/things")
    }
}
```

Conventions:
- Use `async throws` for all methods
- Request structs can be inline (private to the method) or top-level if reused
- Response types should be `Codable` structs, usually defined near the call site or in a shared Models file
- The `get`/`post`/`patch`/`delete` helpers handle auth headers, JSON encoding, and 401 retry automatically
- Endpoint paths have NO leading slash (e.g., `"v3/things"`, not `"/v3/things"`)

### Step 7 — Wire up in SwiftUI

Call the new API method from a ViewModel or View as needed. No special wiring required beyond calling `APIClient.shared`.

## Key Conventions

### Authentication

- **Rust**: Add `user: AuthUser` as a handler parameter. The `AuthUser` extractor automatically reads the `Authorization: Bearer <token>` header and verifies against Firebase. The `user.uid` field is the Firebase UID. `user.name` and `user.email` are also available.
- **No auth**: Omit the `AuthUser` parameter (e.g., health check endpoints).
- **Swift**: `buildHeaders(requireAuth: true)` is the default. Set `requireAuth: false` for public endpoints.

### Firestore Access

- Use `state.firestore` (an `Arc<FirestoreService>`) from handler via `State(state): State<AppState>`
- Subcollection path: `users/{uid}/my_collection`
- Collection constants are defined at the top of `services/firestore.rs`

### Error Handling

- Handlers return `Result<Json<T>, StatusCode>` for simple cases
- Use `StatusCode::INTERNAL_SERVER_ERROR` for unexpected failures
- Use `StatusCode::NOT_FOUND` for missing resources
- Always log errors with `tracing::error!()` before returning

### API Versioning

- Current routes use `/v1/` or `/v3/` prefixes
- New endpoints should use `/v3/` unless extending an existing `/v1/` resource

### API Base URL

- Production: `https://api.omi.me`
- Local dev: `http://localhost:8080` (set via `OMI_API_URL` env var in `.env`)

### AppState Fields

```rust
pub struct AppState {
    pub firestore: Arc<FirestoreService>,    // Firestore REST client
    pub integrations: Arc<IntegrationService>, // External service integrations
    pub redis: Option<Arc<RedisService>>,    // Optional Redis for caching
    pub config: Arc<Config>,                 // Environment config
}
```

## Checklist

Use this when adding a new endpoint:

- [ ] Models: request/response structs in `Backend-Rust/src/models/`
- [ ] Models: registered in `Backend-Rust/src/models/mod.rs`
- [ ] Service: data access method in `Backend-Rust/src/services/firestore.rs` (if needed)
- [ ] Route: handler + `*_routes()` function in `Backend-Rust/src/routes/`
- [ ] Route: registered in `Backend-Rust/src/routes/mod.rs`
- [ ] Route: merged in `Backend-Rust/src/main.rs`
- [ ] Swift: client method in `Desktop/Sources/APIClient.swift`
- [ ] Swift: response model (Codable struct) defined
