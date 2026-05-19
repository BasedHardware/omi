use std::fs;
use std::sync::Arc;

use anyhow::Result;
use axum::Router;
use tokio::net::TcpListener;
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

mod config;
mod health;
mod processing;
mod providers;
mod routes;
mod storage;

use config::Config;
use health::health;
use storage::Store;

#[derive(Clone)]
pub struct AppState {
    pub config: Arc<Config>,
    pub store: Store,
}

#[tokio::main]
async fn main() -> Result<()> {
    init_tracing();

    let config = Config::from_env()?;
    fs::create_dir_all(&config.data_dir)?;
    let store = Store::open(config.data_dir.join("omi-local-backend.sqlite"))?;

    let bind_addr = config.bind_addr;
    let state = AppState {
        config: Arc::new(config),
        store: store.clone(),
    };
    processing::spawn_worker(store);

    let app = app(state);

    let listener = TcpListener::bind(bind_addr).await?;
    tracing::info!(
        service = "omi-local-backend",
        mode = "local",
        %bind_addr,
        "listening"
    );

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    Ok(())
}

fn app(state: AppState) -> Router {
    Router::new()
        .merge(routes::router())
        .route("/health", axum::routing::get(health))
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

fn init_tracing() {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "omi_local_backend=info,tower_http=info".into()),
        )
        .with(tracing_subscriber::fmt::layer().json())
        .init();
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}

#[cfg(test)]
mod tests {
    use std::net::{IpAddr, Ipv4Addr, SocketAddr};
    use std::sync::Arc;

    use anyhow::Result;
    use axum::{
        body::{to_bytes, Body},
        http::{Method, Request, StatusCode},
    };
    use serde_json::{json, Value};
    use tower::ServiceExt;

    use super::*;

    #[tokio::test]
    async fn mvp_routes_support_local_desktop_flow() -> Result<()> {
        let app = test_app()?;

        let created = request_json(
            app.clone(),
            Method::POST,
            "/v1/conversations",
            Some(json!({
                "session_id": "session-route",
                "title": "Local route test",
                "overview": "Exercise the MVP API"
            })),
        )
        .await?;
        let conversation_id = created["conversation"]["id"]
            .as_str()
            .expect("conversation id")
            .to_string();

        request_json(
            app.clone(),
            Method::POST,
            &format!("/v1/conversations/{conversation_id}/transcript-segments"),
            Some(json!({
                "text": "The local daemon stores transcript text for search.",
                "start_ms": 0,
                "end_ms": 1200
            })),
        )
        .await?;

        let job = request_json(
            app.clone(),
            Method::POST,
            &format!("/v1/conversations/{conversation_id}/finalize-transcript"),
            None,
        )
        .await?;
        assert_eq!(job["processing_job"]["status"], "queued");

        let starred = request_json(
            app.clone(),
            Method::PATCH,
            &format!("/v1/conversations/{conversation_id}"),
            Some(json!({"starred": true})),
        )
        .await?;
        assert_eq!(starred["conversation"]["starred"], true);

        let conversation = request_json(
            app.clone(),
            Method::GET,
            &format!("/v1/conversations/{conversation_id}"),
            None,
        )
        .await?;
        assert_eq!(conversation["conversation"]["starred"], true);
        assert_eq!(
            conversation["transcript_segments"]
                .as_array()
                .unwrap()
                .len(),
            1
        );

        let search = request_json(
            app.clone(),
            Method::GET,
            "/v1/search/conversations?q=daemon",
            None,
        )
        .await?;
        assert_eq!(search["results"].as_array().unwrap().len(), 1);

        let status =
            request_json(app.clone(), Method::GET, "/v1/processing-jobs/status", None).await?;
        assert_eq!(status["queued"], 1);

        let memory = request_json(
            app.clone(),
            Method::POST,
            "/v1/memories",
            Some(json!({"content": "Prefers local-first desktop mode"})),
        )
        .await?;
        assert!(memory["memory"]["id"].is_string());
        let memory_id = memory["memory"]["id"].as_str().expect("memory id");

        let updated_memory = request_json(
            app.clone(),
            Method::PATCH,
            &format!("/v1/memories/{memory_id}"),
            Some(json!({"content": "Prefers local-only desktop mode"})),
        )
        .await?;
        assert_eq!(
            updated_memory["memory"]["content"],
            "Prefers local-only desktop mode"
        );

        let memories = request_json(app.clone(), Method::GET, "/v1/memories", None).await?;
        assert_eq!(memories["memories"].as_array().unwrap().len(), 1);

        let action_item = request_json(
            app.clone(),
            Method::POST,
            "/v1/action-items",
            Some(json!({"title": "Review local processing status"})),
        )
        .await?;
        assert_eq!(action_item["action_item"]["status"], "open");
        let action_item_id = action_item["action_item"]["id"]
            .as_str()
            .expect("action item id");

        let updated_action_item = request_json(
            app.clone(),
            Method::PATCH,
            &format!("/v1/action-items/{action_item_id}"),
            Some(json!({
                "status": "completed",
                "due_at": "2026-05-19T12:00:00Z"
            })),
        )
        .await?;
        assert_eq!(updated_action_item["action_item"]["status"], "completed");
        assert!(updated_action_item["action_item"]["completed_at"].is_string());
        assert_eq!(
            updated_action_item["action_item"]["due_at"],
            "2026-05-19T12:00:00Z"
        );

        let cleared_due_at = request_json(
            app.clone(),
            Method::PATCH,
            &format!("/v1/action-items/{action_item_id}"),
            Some(json!({"clear_due_at": true, "due_at": null})),
        )
        .await?;
        assert!(cleared_due_at["action_item"]["due_at"].is_null());

        request_status(
            app.clone(),
            Method::DELETE,
            &format!("/v1/memories/{memory_id}"),
            None,
            StatusCode::NO_CONTENT,
        )
        .await?;
        let memories = request_json(app.clone(), Method::GET, "/v1/memories", None).await?;
        assert!(memories["memories"].as_array().unwrap().is_empty());

        request_status(
            app.clone(),
            Method::DELETE,
            &format!("/v1/action-items/{action_item_id}"),
            None,
            StatusCode::NO_CONTENT,
        )
        .await?;
        let action_items = request_json(app, Method::GET, "/v1/action-items", None).await?;
        assert!(action_items["action_items"].as_array().unwrap().is_empty());

        Ok(())
    }

    #[tokio::test]
    async fn profile_and_settings_routes_are_local_without_auth() -> Result<()> {
        let app = test_app()?;

        let status = request_json(app.clone(), Method::GET, "/profile/status", None).await?;
        assert_eq!(status["mode"], "local");
        assert_eq!(status["authenticated"], false);

        let profile = request_json(
            app.clone(),
            Method::PUT,
            "/v1/profile",
            Some(json!({
                "display_name": "Local User",
                "timezone": "UTC",
                "locale": "en"
            })),
        )
        .await?;
        assert_eq!(profile["profile"]["display_name"], "Local User");

        let settings = request_json(
            app,
            Method::PUT,
            "/v1/settings",
            Some(json!({
                "provider": {"kind": "openai"},
                "local_first": true
            })),
        )
        .await?;
        assert_eq!(settings["settings"].as_array().unwrap().len(), 2);

        Ok(())
    }

    #[tokio::test]
    async fn duplicate_finalize_reuses_active_and_current_completed_job() -> Result<()> {
        let app = test_app()?;

        let created = request_json(
            app.clone(),
            Method::POST,
            "/v1/conversations",
            Some(json!({"session_id": "session-finalize-retry"})),
        )
        .await?;
        let conversation_id = created["conversation"]["id"].as_str().unwrap();
        request_json(
            app.clone(),
            Method::POST,
            &format!("/v1/conversations/{conversation_id}/transcript-segments"),
            Some(json!({
                "text": "Finalize should be retry safe.",
                "start_ms": 0,
                "end_ms": 1000,
                "segment_index": 0
            })),
        )
        .await?;

        let first = request_json(
            app.clone(),
            Method::POST,
            &format!("/v1/conversations/{conversation_id}/finalize-transcript"),
            None,
        )
        .await?;
        let second = request_json(
            app.clone(),
            Method::POST,
            &format!("/v1/conversations/{conversation_id}/finalize-transcript"),
            None,
        )
        .await?;
        assert_eq!(
            first["processing_job"]["id"],
            second["processing_job"]["id"]
        );
        assert_eq!(second["processing_job"]["status"], "queued");

        request_json(
            app.clone(),
            Method::POST,
            "/v1/processing-jobs/process-next",
            None,
        )
        .await?;
        let third = request_json(
            app,
            Method::POST,
            &format!("/v1/conversations/{conversation_id}/finalize-transcript"),
            None,
        )
        .await?;
        assert_eq!(first["processing_job"]["id"], third["processing_job"]["id"]);
        assert_eq!(third["processing_job"]["status"], "completed");

        Ok(())
    }

    #[tokio::test]
    async fn create_routes_are_idempotent_for_client_supplied_ids() -> Result<()> {
        let app = test_app()?;

        let conversation_body = json!({
            "id": "conv-idempotent",
            "session_id": "session-idempotent",
            "title": "Replay safe",
            "overview": "Same client payload",
            "metadata": {"source": "test"}
        });
        let first_conversation = request_json(
            app.clone(),
            Method::POST,
            "/v1/conversations",
            Some(conversation_body.clone()),
        )
        .await?;
        let second_conversation = request_json(
            app.clone(),
            Method::POST,
            "/v1/conversations",
            Some(conversation_body),
        )
        .await?;
        assert_eq!(
            first_conversation["conversation"]["id"],
            second_conversation["conversation"]["id"]
        );
        assert_eq!(
            first_conversation["conversation"]["created_at"],
            second_conversation["conversation"]["created_at"]
        );

        let memory_body = json!({
            "id": "mem-idempotent",
            "content": "User prefers local retries.",
            "category": "preference",
            "conversation_id": "conv-idempotent",
            "metadata": {"source": "test"}
        });
        request_json(
            app.clone(),
            Method::POST,
            "/v1/memories",
            Some(memory_body.clone()),
        )
        .await?;
        let replayed_memory =
            request_json(app.clone(), Method::POST, "/v1/memories", Some(memory_body)).await?;
        assert_eq!(replayed_memory["memory"]["id"], "mem-idempotent");

        let action_item_body = json!({
            "id": "act-idempotent",
            "conversation_id": "conv-idempotent",
            "title": "Check retry path",
            "description": "Replay the create call",
            "status": "open",
            "metadata": {"source": "test"}
        });
        request_json(
            app.clone(),
            Method::POST,
            "/v1/action-items",
            Some(action_item_body.clone()),
        )
        .await?;
        let replayed_action_item = request_json(
            app,
            Method::POST,
            "/v1/action-items",
            Some(action_item_body),
        )
        .await?;
        assert_eq!(replayed_action_item["action_item"]["id"], "act-idempotent");

        Ok(())
    }

    #[tokio::test]
    async fn create_routes_return_conflict_for_same_id_different_payload() -> Result<()> {
        let app = test_app()?;

        request_json(
            app.clone(),
            Method::POST,
            "/v1/conversations",
            Some(json!({
                "id": "conv-conflict",
                "session_id": "session-conflict",
                "title": "Original"
            })),
        )
        .await?;
        request_status(
            app.clone(),
            Method::POST,
            "/v1/conversations",
            Some(json!({
                "id": "conv-conflict",
                "session_id": "session-conflict",
                "title": "Changed"
            })),
            StatusCode::CONFLICT,
        )
        .await?;

        request_json(
            app.clone(),
            Method::POST,
            "/v1/memories",
            Some(json!({"id": "mem-conflict", "content": "Original"})),
        )
        .await?;
        request_status(
            app.clone(),
            Method::POST,
            "/v1/memories",
            Some(json!({"id": "mem-conflict", "content": "Changed"})),
            StatusCode::CONFLICT,
        )
        .await?;

        request_json(
            app.clone(),
            Method::POST,
            "/v1/action-items",
            Some(json!({"id": "act-conflict", "title": "Original"})),
        )
        .await?;
        request_status(
            app,
            Method::POST,
            "/v1/action-items",
            Some(json!({"id": "act-conflict", "title": "Changed"})),
            StatusCode::CONFLICT,
        )
        .await?;

        Ok(())
    }

    fn test_app() -> Result<Router> {
        let config = Config {
            bind_addr: SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
            data_dir: std::env::temp_dir().join("omi-local-backend-route-tests"),
        };
        let state = AppState {
            config: Arc::new(config),
            store: Store::open_in_memory()?,
        };
        Ok(app(state))
    }

    async fn request_json(
        app: Router,
        method: Method,
        uri: &str,
        body: Option<Value>,
    ) -> Result<Value> {
        let request_body = match body {
            Some(value) => Body::from(serde_json::to_vec(&value)?),
            None => Body::empty(),
        };
        let request = Request::builder()
            .method(method)
            .uri(uri)
            .header("content-type", "application/json")
            .body(request_body)?;

        let response = app.oneshot(request).await?;
        let status = response.status();
        let bytes = to_bytes(response.into_body(), 1024 * 1024).await?;
        assert!(
            status == StatusCode::OK || status == StatusCode::CREATED,
            "unexpected status {status}: {}",
            String::from_utf8_lossy(&bytes)
        );
        Ok(serde_json::from_slice(&bytes)?)
    }

    async fn request_status(
        app: Router,
        method: Method,
        uri: &str,
        body: Option<Value>,
        expected_status: StatusCode,
    ) -> Result<()> {
        let request_body = match body {
            Some(value) => Body::from(serde_json::to_vec(&value)?),
            None => Body::empty(),
        };
        let request = Request::builder()
            .method(method)
            .uri(uri)
            .header("content-type", "application/json")
            .body(request_body)?;

        let response = app.oneshot(request).await?;
        let status = response.status();
        let bytes = to_bytes(response.into_body(), 1024 * 1024).await?;
        assert_eq!(
            status,
            expected_status,
            "unexpected status {status}: {}",
            String::from_utf8_lossy(&bytes)
        );
        Ok(())
    }
}
