// Routes module

// ── Active routes (have real traffic) ─────────────────────────────────────────
pub mod agent;
pub mod auth;
pub mod chat_completions;
pub mod config;
pub mod crisp;
pub mod health;
pub mod proxy;
pub mod rate_limit;
pub mod screen_activity;
pub mod tts;
pub mod updates;
pub mod webhooks;

// ── Deprecated route stubs (return 410 Gone) ────────────────────────────────
// Current desktop app routes all data CRUD to Python (api.omi.me).
// deprecated.rs returns 410 for all non-active paths.
pub mod deprecated;

// ── Deprecated modules (source files retained for reference) ─────────────────
pub mod action_items;
pub mod advice;
pub mod apps;
pub mod chat;
pub mod chat_sessions;
pub mod conversations;
pub mod daily_score;
pub mod focus_sessions;
pub mod folders;
pub mod goals;
pub mod knowledge_graph;
pub mod llm_usage;
pub mod memories;
pub mod messages;
pub mod people;
pub mod personas;
pub mod staged_tasks;
pub mod stats;
pub mod users;

// ── Active re-exports ─────────────────────────────────────────────────────────
pub use agent::agent_routes;
pub use auth::auth_routes;
pub use chat_completions::chat_completions_routes;
pub use config::config_routes;
pub use crisp::crisp_routes;
pub use deprecated::deprecated_routes;
pub use health::health_routes;
pub use proxy::proxy_routes;
pub use screen_activity::screen_activity_routes;
pub use tts::tts_routes;
pub use updates::updates_routes;
pub use webhooks::webhook_routes;
