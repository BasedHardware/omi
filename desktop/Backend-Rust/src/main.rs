// OMI Desktop Backend - Rust
// Port from Python backend (main.py)

use axum::Router;
use std::fs::OpenOptions;
use std::io::LineWriter;
use std::sync::Arc;
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
mod config;
mod encryption;
mod llm;
mod models;
mod routes;
mod services;

use auth::{firebase_auth_extension, FirebaseAuth};
use config::Config;
use routes::{action_items_routes, advice_routes, agent_routes, apps_routes, auth_routes, chat_routes, chat_sessions_routes, conversations_routes, crisp_routes, daily_score_routes, focus_sessions_routes, folder_routes, goals_routes, health_routes, knowledge_graph_routes, memories_routes, messages_routes, people_routes, personas_routes, staged_tasks_routes, stats_routes, updates_routes, users_routes, webhook_routes};
use services::{FirestoreService, IntegrationService, RedisService};

/// Application state shared across handlers
#[derive(Clone)]
pub struct AppState {
    pub firestore: Arc<FirestoreService>,
    pub integrations: Arc<IntegrationService>,
    pub redis: Option<Arc<RedisService>>,
    pub config: Arc<Config>,
    pub crisp_session_cache: routes::crisp::SessionCache,
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
                .with_ansi(true)
        )
        // File layer (same format, no ANSI colors)
        .with(
            fmt::layer()
                .with_timer(BackendTimer)
                .with_target(false)
                .with_level(false)
                .with_ansi(false)
                .with_writer(non_blocking)
        )
        .init();

    // Load environment variables
    dotenvy::dotenv().ok();

    // Load and validate config
    let config = Config::from_env();
    if let Err(e) = config.validate() {
        tracing::error!("Configuration error: {}", e);
    }

    // Initialize Firebase Auth
    let firebase_auth = Arc::new(FirebaseAuth::new(
        config.firebase_project_id.clone().unwrap_or_else(|| "based-hardware".to_string()),
    ));

    // Refresh Firebase keys with retry (transient network failures at startup)
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
                    tracing::warn!("Firebase key fetch attempt {}/{} failed: {}", attempt, max_attempts, e);
                    last_err = Some(e);
                    if attempt < max_attempts {
                        tokio::time::sleep(std::time::Duration::from_secs(1 << (attempt - 1))).await;
                    }
                }
            }
        }
        if let Some(e) = last_err {
            tracing::warn!("All {} Firebase key fetch attempts failed: {} - auth may not work", max_attempts, e);
        }
    }

    // Initialize Firestore
    let firestore = match FirestoreService::new(
        config.firebase_project_id.clone().unwrap_or_else(|| "based-hardware".to_string()),
        config.encryption_secret.clone(),
    ).await {
        Ok(fs) => Arc::new(fs),
        Err(e) => {
            tracing::warn!("Failed to initialize Firestore: {} - using placeholder", e);
            Arc::new(FirestoreService::new("based-hardware".to_string(), config.encryption_secret.clone()).await.unwrap())
        }
    };

    // Initialize Integration Service
    let integrations = Arc::new(IntegrationService::new());

    // Initialize Redis (optional - for conversation visibility/sharing)
    // Use explicit connection params to avoid URL encoding issues with special characters in password
    let redis = if let Some(host) = &config.redis_host {
        match RedisService::new_with_params(host, config.redis_port, config.redis_password.as_deref()) {
            Ok(rs) => {
                tracing::info!("Redis client created for {}:{}", host, config.redis_port);
                Some(Arc::new(rs))
            }
            Err(e) => {
                tracing::warn!("Failed to create Redis client: {} - conversation sharing will not work", e);
                None
            }
        }
    } else {
        tracing::warn!("Redis not configured - conversation sharing will not work");
        None
    };

    // Create app state
    let state = AppState {
        firestore,
        integrations,
        redis,
        config: Arc::new(config.clone()),
        crisp_session_cache: routes::crisp::new_session_cache(),
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
        .merge(stats_routes())
        .merge(webhook_routes())
        .merge(crisp_routes())
        .with_state(state);

    // Merge both (now both are Router<()>), then add layers
    let app = main_router
        .merge(auth_router)
        .layer(firebase_auth_extension(firebase_auth))
        .layer(cors)
        .layer(TraceLayer::new_for_http());

    // Start server
    let addr = format!("0.0.0.0:{}", config.port);
    tracing::info!("Starting OMI Desktop Backend on {}", addr);

    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
