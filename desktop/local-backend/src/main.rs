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

    #[tokio::test]
    async fn processed_conversation_replay_conflicts_when_create_payload_changes() -> Result<()> {
        let app = test_app()?;
        let body = json!({
            "id": "conv-processed-conflict",
            "session_id": "session-processed-conflict",
            "title": "Original title",
            "overview": "Original overview",
            "metadata": {"source": "test"}
        });
        request_json(
            app.clone(),
            Method::POST,
            "/v1/conversations",
            Some(body.clone()),
        )
        .await?;
        request_json(
            app.clone(),
            Method::PATCH,
            "/v1/conversations/conv-processed-conflict",
            Some(json!({"status": "processed"})),
        )
        .await?;

        let replayed =
            request_json(app.clone(), Method::POST, "/v1/conversations", Some(body)).await?;
        assert_eq!(replayed["conversation"]["id"], "conv-processed-conflict");

        request_status(
            app.clone(),
            Method::POST,
            "/v1/conversations",
            Some(json!({
                "id": "conv-processed-conflict",
                "session_id": "session-processed-conflict",
                "title": "Changed title",
                "overview": "Original overview",
                "metadata": {"source": "test"}
            })),
            StatusCode::CONFLICT,
        )
        .await?;
        request_status(
            app,
            Method::POST,
            "/v1/conversations",
            Some(json!({
                "id": "conv-processed-conflict",
                "session_id": "session-processed-conflict",
                "title": "Original title",
                "overview": "Original overview",
                "metadata": {"source": "changed"}
            })),
            StatusCode::CONFLICT,
        )
        .await?;

        Ok(())
    }

    #[tokio::test]
    async fn memory_list_supports_pagination_category_and_tags() -> Result<()> {
        let app = test_app()?;

        let batch = request_json(
            app.clone(),
            Method::POST,
            "/v1/memories/batch",
            Some(json!({
                "memories": [
                    {"content": "Manual focus memory", "tags": ["focus", "productivity"]},
                    {"content": "Manual health memory", "tags": ["health"]},
                    {"content": "Manual focus followup", "tags": ["focus"]}
                ]
            })),
        )
        .await?;
        assert_eq!(batch["created_count"], 3);

        request_json(
            app.clone(),
            Method::POST,
            "/v1/memories",
            Some(json!({
                "id": "mem-system",
                "content": "System memory",
                "category": "system",
                "metadata": {"tags": ["focus"]}
            })),
        )
        .await?;

        let page_one = request_json(
            app.clone(),
            Method::GET,
            "/v1/memories?limit=2&offset=0",
            None,
        )
        .await?;
        let page_two = request_json(
            app.clone(),
            Method::GET,
            "/v1/memories?limit=2&offset=2",
            None,
        )
        .await?;
        let page_one_ids: Vec<&str> = page_one["memories"]
            .as_array()
            .unwrap()
            .iter()
            .map(|memory| memory["id"].as_str().unwrap())
            .collect();
        let page_two_ids: Vec<&str> = page_two["memories"]
            .as_array()
            .unwrap()
            .iter()
            .map(|memory| memory["id"].as_str().unwrap())
            .collect();
        assert_eq!(page_one_ids.len(), 2);
        assert_eq!(page_two_ids.len(), 2);
        assert!(page_one_ids.iter().all(|id| !page_two_ids.contains(id)));

        let system_focus = request_json(
            app.clone(),
            Method::GET,
            "/v1/memories?category=system&tags=focus",
            None,
        )
        .await?;
        assert_eq!(system_focus["memories"].as_array().unwrap().len(), 1);
        assert_eq!(system_focus["memories"][0]["id"], "mem-system");

        let focus = request_json(app, Method::GET, "/v1/memories?tags=focus", None).await?;
        assert_eq!(focus["memories"].as_array().unwrap().len(), 3);

        Ok(())
    }

    #[tokio::test]
    async fn settings_reject_omi_firebase_and_google_provider_hosts() -> Result<()> {
        let app = test_app()?;

        for base_url in [
            "https://api.omi.me/v1",
            "https://api.omiapi.com/v1",
            "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/v1",
            "https://identitytoolkit.googleapis.com/v1",
            "https://based-hardware.firebaseapp.com/v1",
        ] {
            request_status(
                app.clone(),
                Method::PUT,
                "/v1/settings",
                Some(json!({
                    "ai_provider": {
                        "kind": "openai_compatible",
                        "base_url": base_url,
                        "api_key": "blocked"
                    }
                })),
                StatusCode::BAD_REQUEST,
            )
            .await?;
        }

        let allowed = request_json(
            app,
            Method::PUT,
            "/v1/settings",
            Some(json!({
                "ai_provider": {
                    "kind": "openai_compatible",
                    "base_url": "http://127.0.0.1:11434/v1",
                    "api_key": "local"
                }
            })),
        )
        .await?;
        assert_eq!(allowed["settings"][0]["key"], "ai_provider");

        Ok(())
    }

    #[tokio::test]
    async fn hybrid_v2_chat_sessions_and_messages_routes() -> Result<()> {
        let app = test_app()?;

        let empty_list = request_json(app.clone(), Method::GET, "/v2/chat-sessions", None).await?;
        assert!(
            empty_list.as_array().map(|a| a.is_empty()).unwrap_or(false),
            "expected no user sessions yet"
        );

        let created = request_json(
            app.clone(),
            Method::POST,
            "/v2/chat-sessions",
            Some(json!({"title": "Route test"})),
        )
        .await?;
        let sid = created["id"].as_str().expect("session id");

        let listed = request_json(app.clone(), Method::GET, "/v2/chat-sessions", None).await?;
        assert_eq!(listed.as_array().expect("sessions").len(), 1);

        let one = request_json(
            app.clone(),
            Method::GET,
            &format!("/v2/chat-sessions/{sid}"),
            None,
        )
        .await?;
        assert_eq!(one["title"], "Route test");

        request_json(
            app.clone(),
            Method::PATCH,
            &format!("/v2/chat-sessions/{sid}"),
            Some(json!({"starred": true})),
        )
        .await?;

        let saved = request_json(
            app.clone(),
            Method::POST,
            &format!("/v2/chat-sessions/{sid}/messages"),
            Some(json!({"text": "hello daemon", "sender": "human"})),
        )
        .await?;
        assert!(saved["id"].as_str().is_some());

        let msgs = request_json(
            app.clone(),
            Method::GET,
            &format!("/v2/chat-sessions/{sid}/messages"),
            None,
        )
        .await?;
        assert_eq!(msgs.as_array().expect("messages").len(), 1);

        let default_sid = "00000000-0000-4000-8000-000000000001";
        request_json(
            app.clone(),
            Method::POST,
            &format!("/v2/chat-sessions/{default_sid}/messages"),
            Some(json!({"text": "default thread", "sender": "human"})),
        )
        .await?;

        let default_msgs = request_json(
            app.clone(),
            Method::GET,
            &format!("/v2/chat-sessions/{default_sid}/messages"),
            None,
        )
        .await?;
        assert_eq!(default_msgs.as_array().expect("default msgs").len(), 1);

        request_status(
            app.clone(),
            Method::DELETE,
            &format!("/v2/chat-sessions/{sid}"),
            None,
            StatusCode::NO_CONTENT,
        )
        .await?;

        Ok(())
    }

    #[tokio::test]
    async fn conversation_folders_merge_and_folder_assignment_routes() -> Result<()> {
        let app = test_app()?;

        let folder = request_json(
            app.clone(),
            Method::POST,
            "/v1/conversation-folders",
            Some(json!({
                "name": "Desk",
                "description": "papers",
                "color": "#111111",
            })),
        )
        .await?;
        let folder_id = folder["folder"]["id"].as_str().expect("folder id");

        let folders =
            request_json(app.clone(), Method::GET, "/v1/conversation-folders", None).await?;
        assert_eq!(folders["folders"].as_array().expect("folders array").len(), 1);

        let conv_a = request_json(
            app.clone(),
            Method::POST,
            "/v1/conversations",
            Some(json!({
                "session_id": "s-merge-a",
                "title": "A",
                "overview": "",
            })),
        )
        .await?;
        let id_a = conv_a["conversation"]["id"].as_str().unwrap();

        let conv_b = request_json(
            app.clone(),
            Method::POST,
            "/v1/conversations",
            Some(json!({
                "session_id": "s-merge-b",
                "title": "B",
                "overview": "",
            })),
        )
        .await?;
        let id_b = conv_b["conversation"]["id"].as_str().unwrap();

        request_json(
            app.clone(),
            Method::POST,
            &format!("/v1/conversations/{id_a}/transcript-segments"),
            Some(json!({"text": "one", "start_ms": 0, "end_ms": 50})),
        )
        .await?;
        request_json(
            app.clone(),
            Method::POST,
            &format!("/v1/conversations/{id_b}/transcript-segments"),
            Some(json!({"text": "two", "start_ms": 0, "end_ms": 60})),
        )
        .await?;

        let merge_resp = request_json(
            app.clone(),
            Method::POST,
            "/v1/conversations/merge",
            Some(json!({
                "conversation_ids": [id_a, id_b],
                "reprocess": false,
            })),
        )
        .await?;
        assert_eq!(merge_resp["status"], "completed");
        let merged_id = merge_resp["new_conversation_id"]
            .as_str()
            .expect("merged id")
            .to_string();

        let folder_update = request_json(
            app.clone(),
            Method::PATCH,
            &format!("/v1/conversation-folders/{folder_id}"),
            Some(json!({"name": "Desk2"})),
        )
        .await?;
        assert_eq!(folder_update["folder"]["name"], "Desk2");

        let assigned = request_json(
            app.clone(),
            Method::PATCH,
            &format!("/v1/conversations/{merged_id}"),
            Some(json!({"folder_id": folder_id})),
        )
        .await?;
        assert_eq!(assigned["conversation"]["folder_id"], folder_id);

        request_status(
            app.clone(),
            Method::DELETE,
            &format!("/v1/conversation-folders/{folder_id}"),
            None,
            StatusCode::NO_CONTENT,
        )
        .await?;

        let unfiled =
            request_json(app.clone(), Method::GET, &format!("/v1/conversations/{merged_id}"), None)
                .await?;
        assert!(unfiled["conversation"]["folder_id"].is_null());

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
