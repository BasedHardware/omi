// Health check routes

use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use serde::Serialize;

use crate::AppState;

#[derive(Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub service: String,
    pub version: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub release_tag: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub release_sha: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub release_channel: Option<String>,
}

#[derive(Serialize)]
pub struct ReadinessResponse {
    pub status: &'static str,
    pub service: &'static str,
    pub redis: RedisReadiness,
}

#[derive(Serialize)]
pub struct RedisReadiness {
    pub status: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failure_class: Option<&'static str>,
}

/// Health check endpoint for Kubernetes probes
async fn health_check(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "healthy".to_string(),
        service: "omi-desktop-backend".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        release_tag: state.config.desktop_release_tag.clone(),
        release_sha: state.config.desktop_release_sha.clone(),
        release_channel: state.config.desktop_release_channel.clone(),
    })
}

/// Dependency readiness is intentionally separate from process liveness.
/// Server-key TTS/chat/Gemini requests must not be admitted unmetered when
/// Redis is absent or unavailable, while `/health` must continue to prove the
/// process itself is alive for diagnosis and restart policy.
async fn readiness_check(State(state): State<AppState>) -> Response {
    let probe = match state.redis.as_ref() {
        None => None,
        Some(redis) => Some(redis.health_check().await),
    };
    let (status, redis) = readiness_from_probe(probe);

    (
        status,
        Json(ReadinessResponse {
            status: if status == StatusCode::OK {
                "ready"
            } else {
                "not_ready"
            },
            service: "omi-desktop-backend",
            redis,
        }),
    )
        .into_response()
}

fn readiness_from_probe(
    probe: Option<Result<bool, redis::RedisError>>,
) -> (StatusCode, RedisReadiness) {
    match probe {
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            RedisReadiness {
                status: "not_configured",
                failure_class: Some("not_configured"),
            },
        ),
        Some(result) => match result {
            Ok(true) => (
                StatusCode::OK,
                RedisReadiness {
                    status: "ready",
                    failure_class: None,
                },
            ),
            Ok(false) => (
                StatusCode::SERVICE_UNAVAILABLE,
                RedisReadiness {
                    status: "unexpected_response",
                    failure_class: Some("command_data"),
                },
            ),
            Err(error) => {
                let class = crate::services::redis::classify_redis_error(&error);
                (
                    StatusCode::SERVICE_UNAVAILABLE,
                    RedisReadiness {
                        status: "unavailable",
                        failure_class: Some(class.as_str()),
                    },
                )
            }
        },
    }
}

pub fn health_routes() -> Router<AppState> {
    Router::new()
        .route("/health", get(health_check))
        .route("/ready", get(readiness_check))
        .route("/", get(health_check))
}

#[cfg(test)]
mod tests {
    use super::*;
    use redis::ErrorKind;

    #[test]
    fn readiness_distinguishes_healthy_process_from_missing_redis() {
        let (status, redis) = readiness_from_probe(None);
        assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(redis.status, "not_configured");
        assert_eq!(redis.failure_class, Some("not_configured"));

        let (status, redis) = readiness_from_probe(Some(Ok(true)));
        assert_eq!(status, StatusCode::OK);
        assert_eq!(redis.status, "ready");
        assert_eq!(redis.failure_class, None);
    }

    #[test]
    fn readiness_exposes_bounded_dependency_failure_class() {
        let transport = (ErrorKind::IoError, "broken pipe").into();
        let (status, redis) = readiness_from_probe(Some(Err(transport)));
        assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(redis.status, "unavailable");
        assert_eq!(redis.failure_class, Some("transport"));

        let auth = (ErrorKind::AuthenticationFailed, "wrong password").into();
        let (_, redis) = readiness_from_probe(Some(Err(auth)));
        assert_eq!(redis.failure_class, Some("auth_config"));
    }
}
