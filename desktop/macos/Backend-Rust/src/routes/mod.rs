// Routes module

// ── Active routes (have real traffic) ─────────────────────────────────────────
pub mod agent;
pub mod auth;
pub mod chat_completions;
pub mod config;
pub mod crisp;
pub mod health;
pub mod llm_stub;
pub mod proxy;
pub mod rate_limit;
pub mod realtime;
mod retrieval_policy;
pub mod screen_activity;
pub mod tts;
pub mod updates;
pub mod webhooks;

// ── Deprecated route stubs (return 410 Gone) ────────────────────────────────
// Current desktop app routes all data CRUD to Python (api.omi.me).
// deprecated.rs returns 410 for all non-active paths.
pub mod deprecated;

// ── Active re-exports ─────────────────────────────────────────────────────────
pub use agent::agent_routes;
pub use auth::auth_routes;
pub use chat_completions::chat_completions_routes;
pub use config::config_routes;
pub use crisp::crisp_routes;
pub(crate) use deprecated::deprecated_routes;
pub use health::health_routes;
pub use proxy::proxy_routes;
pub use realtime::realtime_routes;
pub use screen_activity::screen_activity_routes;
pub use tts::tts_routes;
pub use updates::updates_routes;
pub use webhooks::webhook_routes;

/// Build a response from `builder` + `body`, falling back to a logged 500 if the
/// builder rejects the body. Shared by the proxy / chat-completions / tts routes
/// so the fallback behavior lives in one place; `context` names the caller for
/// the log line.
pub(crate) fn response_or_500(
    context: &str,
    builder: axum::http::response::Builder,
    body: axum::body::Body,
) -> axum::response::Response {
    use axum::response::IntoResponse;
    match builder.body(body) {
        Ok(response) => response,
        Err(error) => {
            tracing::error!("{}: failed to build response: {}", context, error);
            axum::http::StatusCode::INTERNAL_SERVER_ERROR.into_response()
        }
    }
}
