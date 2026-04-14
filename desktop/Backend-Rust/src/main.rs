// OMI Desktop Backend - Standalone server
//
// Thin wrapper around the library crate. Initializes tracing,
// then delegates to `lib::init_services()` + `lib::build_router()`.

use std::fs::OpenOptions;
use std::io::LineWriter;
use tracing_subscriber::fmt::format::Writer;
use tracing_subscriber::fmt::time::FormatTime;
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt};

use nooto_desktop_backend::{build_router, init_services};

/// Custom time formatter: [HH:mm:ss] [backend]
#[derive(Clone)]
struct BackendTimer;

impl FormatTime for BackendTimer {
    fn format_time(&self, w: &mut Writer<'_>) -> std::fmt::Result {
        let now = chrono::Utc::now();
        write!(w, "[{}] [backend]", now.format("%H:%M:%S"))
    }
}

#[tokio::main]
async fn main() {
    // Open log file (same as Swift dev app: /tmp/nooto-dev.log)
    let log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open("/tmp/nooto-dev.log")
        .expect("Failed to open log file");
    let line_writer = LineWriter::new(log_file);

    let (non_blocking, _guard) = tracing_appender::non_blocking(line_writer);

    // Initialize tracing with both stdout and file output
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "nooto_desktop_backend=info,tower_http=info".into()),
        )
        .with(
            fmt::layer()
                .with_timer(BackendTimer)
                .with_target(false)
                .with_level(false)
                .with_ansi(true),
        )
        .with(
            fmt::layer()
                .with_timer(BackendTimer)
                .with_target(false)
                .with_level(false)
                .with_ansi(false)
                .with_writer(non_blocking),
        )
        .init();

    // Initialize services and build router
    let (state, firebase_auth) = init_services()
        .await
        .expect("Failed to initialize backend services");

    let port = state.config.port;
    let app = build_router(state, firebase_auth);

    // Start server
    let addr = format!("0.0.0.0:{}", port);
    tracing::info!("Starting OMI Desktop Backend on {}", addr);

    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
