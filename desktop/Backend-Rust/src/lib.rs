// OMI Desktop Backend - Library crate
//
// This module exposes the backend as a reusable library so it can be embedded
// in other Rust applications (e.g., Tauri desktop-v2) without code duplication.

use axum::Router;
use std::sync::Arc;
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;

pub mod auth;
pub mod config;
pub mod encryption;
pub mod llm;
pub mod models;
pub mod routes;
pub mod services;

pub use auth::{firebase_auth_extension, FirebaseAuth};
pub use config::Config;
pub use services::{FirestoreService, IntegrationService, RedisService};

/// Application state shared across handlers.
#[derive(Clone)]
pub struct AppState {
    pub firestore: Arc<FirestoreService>,
    pub integrations: Arc<IntegrationService>,
    pub redis: Option<Arc<RedisService>>,
    pub config: Arc<Config>,
    pub crisp_session_cache: routes::crisp::SessionCache,
    pub gemini_rate_limiter: routes::rate_limit::SharedRateLimiter,
}

/// Initialize all backend services and return the shared `AppState`.
///
/// This performs the same initialization as the standalone `main()`:
/// - Loads config from environment
/// - Fetches Firebase auth keys (with retry)
/// - Connects to Firestore, Redis
/// - Sets up rate limiters
///
/// Returns `(AppState, Arc<FirebaseAuth>)` so the caller can build the router.
pub async fn init_services() -> Result<(AppState, Arc<FirebaseAuth>), Box<dyn std::error::Error + Send + Sync>> {
    // Load environment variables
    dotenvy::dotenv().ok();

    let config = Config::from_env();
    if let Err(e) = config.validate() {
        tracing::error!("Configuration error: {}", e);
    }

    // Initialize Firebase Auth
    let auth_project_id = config
        .firebase_auth_project_id
        .clone()
        .or_else(|| config.firebase_project_id.clone())
        .ok_or("FIREBASE_AUTH_PROJECT_ID or FIREBASE_PROJECT_ID must be set")?;

    let firebase_auth = Arc::new(FirebaseAuth::new(auth_project_id));

    // Refresh Firebase keys with retry
    {
        let max_attempts = 3u32;
        let mut last_err = None;
        for attempt in 1..=max_attempts {
            match firebase_auth.refresh_keys().await {
                Ok(_) => {
                    if attempt > 1 {
                        tracing::info!("Firebase keys fetched on attempt {}", attempt);
                    }
                    last_err = None;
                    break;
                }
                Err(e) => {
                    tracing::warn!(
                        "Firebase key fetch attempt {}/{} failed: {}",
                        attempt,
                        max_attempts,
                        e
                    );
                    last_err = Some(e);
                    if attempt < max_attempts {
                        tokio::time::sleep(std::time::Duration::from_secs(1 << (attempt - 1)))
                            .await;
                    }
                }
            }
        }
        if let Some(e) = last_err {
            tracing::warn!(
                "All {} Firebase key fetch attempts failed: {} - auth may not work",
                max_attempts,
                e
            );
        }
    }

    // Initialize Firestore
    let firestore_project_id = config
        .firebase_project_id
        .clone()
        .ok_or("FIREBASE_PROJECT_ID must be set for Firestore")?;

    let firestore = Arc::new(
        FirestoreService::new(
            firestore_project_id,
            config.encryption_secret.clone(),
            config.service_account_json.as_deref(),
        )
        .await?,
    );

    // Initialize Integration Service
    let integrations = Arc::new(IntegrationService::new());

    // Initialize Redis (optional)
    let redis = if let Some(host) = &config.redis_host {
        match RedisService::new_with_params(host, config.redis_port, config.redis_password.as_deref())
        {
            Ok(rs) => {
                tracing::info!("Redis client created for {}:{}", host, config.redis_port);
                Some(Arc::new(rs))
            }
            Err(e) => {
                tracing::warn!(
                    "Failed to create Redis client: {} - conversation sharing will not work",
                    e
                );
                None
            }
        }
    } else {
        tracing::warn!("Redis not configured - conversation sharing will not work");
        None
    };

    // Create rate limiter
    let gemini_rate_limiter = routes::rate_limit::GeminiRateLimiter::new();

    // Spawn background eviction task
    {
        let limiter = gemini_rate_limiter.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(std::time::Duration::from_secs(3600)).await;
                limiter.evict_stale().await;
            }
        });
    }

    let state = AppState {
        firestore,
        integrations,
        redis,
        config: Arc::new(config),
        crisp_session_cache: routes::crisp::new_session_cache(),
        gemini_rate_limiter,
    };

    Ok((state, firebase_auth))
}

/// Build the complete Axum router with all routes, middleware, and auth.
///
/// Call `init_services()` first to get the `AppState` and `FirebaseAuth`,
/// then pass them here to get a ready-to-serve `Router`.
pub fn build_router(state: AppState, firebase_auth: Arc<FirebaseAuth>) -> Router {
    use routes::*;

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    // Auth router (has its own state)
    let auth_router = auth_routes(state.config.clone());

    // Main router with AppState
    let main_router = Router::new()
        .merge(health_routes())
        .merge(memories_routes())
        .merge(messages_routes())
        .merge(chat_routes())
        .merge(chat_sessions_routes())
        .merge(conversations_routes())
        .merge(action_items_routes())
        .merge(agent_routes())
        .merge(staged_tasks_routes())
        .merge(focus_sessions_routes())
        .merge(apps_routes())
        .merge(users_routes())
        .merge(advice_routes())
        .merge(updates_routes())
        .merge(folder_routes())
        .merge(goals_routes())
        .merge(daily_score_routes())
        .merge(people_routes())
        .merge(personas_routes())
        .merge(knowledge_graph_routes())
        .merge(llm_usage_routes())
        .merge(stats_routes())
        .merge(webhook_routes())
        .merge(crisp_routes())
        .merge(screen_activity_routes())
        .merge(proxy_routes())
        .merge(config_routes())
        .with_state(state);

    main_router
        .merge(auth_router)
        .layer(firebase_auth_extension(firebase_auth))
        .layer(cors)
        .layer(TraceLayer::new_for_http())
}
