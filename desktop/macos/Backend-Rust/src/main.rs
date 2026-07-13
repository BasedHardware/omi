// OMI Desktop Backend - Rust
// Port from Python backend (main.py)

#![allow(clippy::derivable_impls)]
#![allow(clippy::doc_overindented_list_items)]
#![allow(clippy::doc_lazy_continuation)]
#![allow(clippy::double_ended_iterator_last)]
#![allow(clippy::enum_variant_names)]
#![allow(clippy::filter_next)]
#![allow(clippy::if_same_then_else)]
#![allow(clippy::collapsible_match)]
#![allow(clippy::uninlined_format_args)]
#![allow(clippy::unnecessary_cast)]
#![allow(clippy::unnecessary_map_or)]
#![allow(clippy::too_many_arguments)]
#![allow(clippy::useless_conversion)]
#![allow(clippy::useless_vec)]
#![allow(clippy::wrong_self_convention)]

use axum::Router;
use std::fs::OpenOptions;
use std::io::LineWriter;
use std::sync::Arc;
use tower_http::catch_panic::CatchPanicLayer;
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;
use tracing_subscriber::fmt::format::Writer;
use tracing_subscriber::fmt::time::FormatTime;
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt};

/// Custom time formatter: [HH:mm:ss] [backend]
#[derive(Clone)]
struct BackendTimer;

impl FormatTime for BackendTimer {
    fn format_time(&self, w: &mut Writer<'_>) -> std::fmt::Result {
        let now = chrono::Utc::now();
        write!(w, "[{}] [backend]", now.format("%H:%M:%S"))
    }
}

mod auth;
mod byok;
mod config;
mod fallback;
mod llm;
mod models;
mod paywall;
mod quota;
mod routes;
mod services;
mod vertex;

use auth::{
    byok_cache_extension, chat_quota_checker_extension, firebase_auth_extension,
    paywall_checker_extension, FirebaseAuth,
};
use byok::ByokStateCache;
use config::Config;
use paywall::PaywallChecker;
use routes::{
    // Active (real traffic from current app)
    agent_routes,
    auth_routes,
    chat_completions_routes,
    config_routes,
    crisp_routes,
    // Deprecated stubs (return 410 Gone — current app uses Python for all data CRUD)
    deprecated_routes,
    health_routes,
    proxy_routes,
    realtime_routes,
    screen_activity_routes,
    tts_routes,
    updates_routes,
    webhook_routes,
};
use services::{FirestoreService, RedisService};

/// Application state shared across handlers
#[derive(Clone)]
pub(crate) struct AppState {
    pub firestore: Arc<FirestoreService>,
    pub redis: Option<Arc<RedisService>>,
    pub config: Arc<Config>,
    pub crisp_session_cache: routes::crisp::SessionCache,
    pub gemini_rate_limiter: routes::rate_limit::SharedRateLimiter,
    /// Separate limiter for chat so a burst of Gemini proxy calls can never
    /// rate-limit a user's chat (high burst cap, no daily cap, isolated keys).
    pub chat_rate_limiter: routes::rate_limit::SharedRateLimiter,
    /// Vertex AI auth provider (present when USE_VERTEX_AI=true)
    pub vertex_auth: Option<vertex::VertexAuth>,
    /// Gemini proxy client for full-response calls; owns the upstream deadline.
    pub gemini_client: reqwest::Client,
    /// Gemini proxy client for streaming calls; only bounds connection setup.
    pub gemini_stream_client: reqwest::Client,
}

#[tokio::main]
async fn main() {
    // Open log file (same as Swift dev app: /tmp/omi-dev.log)
    // Wrap in LineWriter to flush after each line (ensures logs appear immediately)
    let log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open("/tmp/omi-dev.log")
        .expect("Failed to open log file");
    let line_writer = LineWriter::new(log_file);

    // Use non_blocking for proper async file writing
    let (non_blocking, _guard) = tracing_appender::non_blocking(line_writer);

    // Initialize tracing with both stdout and file output
    // Format: [HH:mm:ss] [backend] message
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "omi_desktop_backend=info,tower_http=info".into()),
        )
        // Stdout layer
        .with(
            fmt::layer()
                .with_timer(BackendTimer)
                .with_target(false)
                .with_level(false)
                .with_ansi(true),
        )
        // File layer (same format, no ANSI colors)
        .with(
            fmt::layer()
                .with_timer(BackendTimer)
                .with_target(false)
                .with_level(false)
                .with_ansi(false)
                .with_writer(non_blocking),
        )
        .init();

    // Load environment variables
    dotenvy::dotenv().ok();

    // Log active QoS tier
    tracing::info!(
        "Model QoS tier: {} | rate limits: soft={}, hard={}",
        llm::model_qos::tier_description(),
        llm::model_qos::daily_soft_limit(),
        llm::model_qos::daily_hard_limit(),
    );

    // Load and validate config
    let config = Config::from_env();
    if let Err(e) = config.validate() {
        tracing::error!("Configuration error: {}", e);
    }

    // Initialize Firebase Auth
    // Auth token validation may use a different project than Firestore.
    // Cloud Run OAuth issues tokens for "based-hardware" (prod), so local dev
    // needs FIREBASE_AUTH_PROJECT_ID=based-hardware while keeping Firestore on dev.
    let auth_project_id = config
        .firebase_auth_project_id
        .clone()
        .or_else(|| config.firebase_project_id.clone())
        .expect("FIREBASE_AUTH_PROJECT_ID or FIREBASE_PROJECT_ID must be set");
    let firebase_auth = Arc::new(FirebaseAuth::new(auth_project_id.clone()));

    // Refresh Firebase keys with retry (transient network failures at startup)
    if FirebaseAuth::auth_emulator_active() {
        tracing::info!(
            "Firebase Auth emulator active — skipping Google public key fetch (project={})",
            auth_project_id
        );
    } else {
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
        .expect("FIREBASE_PROJECT_ID must be set for Firestore");
    let firestore = match FirestoreService::new(firestore_project_id.clone()).await {
        Ok(fs) => Arc::new(fs),
        Err(e) => {
            tracing::warn!("Failed to initialize Firestore: {} - using placeholder", e);
            match FirestoreService::new(firestore_project_id).await {
                Ok(fs) => Arc::new(fs),
                Err(retry_error) => {
                    tracing::error!(
                        "Failed to initialize Firestore after retry: {}",
                        retry_error
                    );
                    std::process::exit(1);
                }
            }
        }
    };

    // Initialize Redis (optional - for distributed request rate limiting)
    // Use explicit connection params to avoid URL encoding issues with special characters in password
    let redis = if let Some(host) = &config.redis_host {
        match RedisService::new_with_params(
            host,
            config.redis_port,
            config.redis_password.as_deref(),
        ) {
            Ok(rs) => {
                tracing::info!("Redis client created for {}:{}", host, config.redis_port);
                Some(Arc::new(rs))
            }
            Err(e) => {
                tracing::warn!(
                    "Failed to create Redis client: {} - distributed rate limiting is unavailable",
                    e
                );
                None
            }
        }
    } else {
        tracing::warn!("Redis not configured - distributed rate limiting is unavailable");
        None
    };

    // Initialize Vertex AI auth (when USE_VERTEX_AI=true)
    let vertex_auth = if config.use_vertex_ai {
        match (config.vertex_project_id.as_ref(), &config.vertex_location) {
            (Some(project_id), location) => {
                match vertex::VertexAuth::new(project_id.clone(), location.clone()).await {
                    Ok(auth) => {
                        // Verify we can get a token at startup
                        match auth.token().await {
                            Ok(_) => {
                                tracing::info!(
                                    "Vertex AI auth initialized (project={}, location={})",
                                    project_id,
                                    location
                                );
                                Some(auth)
                            }
                            Err(e) => {
                                tracing::error!(
                                    "Vertex AI token fetch failed: {} — falling back to API key",
                                    e
                                );
                                None
                            }
                        }
                    }
                    Err(e) => {
                        tracing::error!("Vertex AI init failed: {} — falling back to API key", e);
                        None
                    }
                }
            }
            _ => {
                tracing::warn!("USE_VERTEX_AI=true but no project ID — falling back to API key");
                None
            }
        }
    } else {
        None
    };

    // Create app state
    let gemini_rate_limiter = routes::rate_limit::GeminiRateLimiter::new();
    // Chat gets its own limiter (isolated Redis namespace, high burst cap, no daily
    // cap) so Gemini proxy bursts can't 429 a user's chat.
    let chat_rate_limiter = routes::rate_limit::GeminiRateLimiter::for_chat();

    // Spawn background task to evict stale rate limit entries every hour
    {
        let gemini_limiter = gemini_rate_limiter.clone();
        let chat_limiter = chat_rate_limiter.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(std::time::Duration::from_secs(3600)).await;
                gemini_limiter.evict_stale().await;
                chat_limiter.evict_stale().await;
            }
        });
    }

    // BYOK state cache — caches Firestore BYOK state per-uid for 30s.
    let byok_cache = Arc::new(ByokStateCache::new());

    // Paywall checker — reads subscription/BYOK/account-age from Firestore + Firebase Auth.
    let paywall_checker = Arc::new(PaywallChecker::new(
        firestore.clone(),
        auth_project_id.clone(),
        byok_cache.clone(),
    ));

    // Monthly chat-quota checker — asks the Python backend (quota SoT) per uid.
    let chat_quota_checker = Arc::new(quota::ChatQuotaChecker::new(config.base_api_url.clone()));

    let state = AppState {
        firestore,
        redis,
        config: Arc::new(config.clone()),
        crisp_session_cache: routes::crisp::new_session_cache(),
        gemini_rate_limiter,
        chat_rate_limiter,
        vertex_auth,
        gemini_client: routes::proxy::gemini_client(),
        gemini_stream_client: routes::proxy::gemini_stream_client(),
    };

    // Build CORS layer
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    // Build auth router (has its own state)
    let auth_router = auth_routes(state.config.clone());

    // Build main app router with AppState
    let main_router = Router::new()
        // ── Active routes (real traffic from current desktop app) ──────────
        .merge(health_routes())
        .merge(agent_routes())
        .merge(config_routes())
        .merge(crisp_routes())
        .merge(proxy_routes())
        .merge(realtime_routes())
        .merge(screen_activity_routes())
        .merge(tts_routes())
        .merge(chat_completions_routes())
        .merge(updates_routes())
        .merge(webhook_routes())
        .with_state(state)
        // ── Deprecated stubs (return 410 Gone) ───────────────────────────
        // This state-free compatibility router cannot reach backing services.
        .merge(deprecated_routes());

    // Merge both (now both are Router<()>), then add layers
    let app = main_router
        .merge(auth_router)
        .layer(firebase_auth_extension(firebase_auth))
        .layer(paywall_checker_extension(paywall_checker))
        .layer(chat_quota_checker_extension(chat_quota_checker))
        .layer(byok_cache_extension(byok_cache))
        .layer(cors)
        .layer(TraceLayer::new_for_http())
        // Outermost layer: turn any handler/middleware panic into a 500 + logged
        // error instead of a dropped connection with no response or structured log.
        .layer(CatchPanicLayer::new());

    // Start server
    let addr = format!("0.0.0.0:{}", config.port);
    tracing::info!("Starting OMI Desktop Backend on {}", addr);

    let listener = match tokio::net::TcpListener::bind(&addr).await {
        Ok(listener) => listener,
        Err(error) => {
            tracing::error!("Failed to bind {}: {}", addr, error);
            std::process::exit(1);
        }
    };
    if let Err(error) = axum::serve(listener, app).await {
        tracing::error!("Server error: {}", error);
        std::process::exit(1);
    }
}
