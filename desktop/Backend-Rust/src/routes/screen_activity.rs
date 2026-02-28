// Screen Activity sync route
// Receives screenshot metadata + embeddings from the desktop app,
// writes metadata to Firestore and embeddings to Pinecone ns3.

use axum::{
    extract::State,
    http::StatusCode,
    routing::post,
    Json, Router,
};

use crate::auth::AuthUser;
use crate::models::screen_activity::{ScreenActivitySyncRequest, ScreenActivitySyncResponse};
use crate::AppState;

/// POST /v1/screen-activity/sync
async fn sync_screen_activity(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<ScreenActivitySyncRequest>,
) -> Result<Json<ScreenActivitySyncResponse>, (StatusCode, String)> {
    if request.rows.len() > 100 {
        return Err((StatusCode::BAD_REQUEST, "Maximum 100 rows per batch".to_string()));
    }

    if request.rows.is_empty() {
        return Ok(Json(ScreenActivitySyncResponse { synced: 0, last_id: 0 }));
    }

    let last_id = request.rows.iter().map(|r| r.id).max().unwrap_or(0);

    tracing::info!(
        "Screen activity sync for user {} — {} rows (last_id={})",
        user.uid,
        request.rows.len(),
        last_id
    );

    // Write metadata to Firestore
    let firestore_result = state
        .firestore
        .upsert_screen_activity(&user.uid, &request.rows)
        .await;

    if let Err(e) = &firestore_result {
        tracing::error!("Screen activity Firestore write failed: {}", e);
        return Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Firestore write failed: {}", e)));
    }

    let written = firestore_result.unwrap();

    // Upsert embeddings to Pinecone ns3 (fire-and-forget in background)
    let rows_with_embeddings: Vec<_> = request
        .rows
        .into_iter()
        .filter(|r| r.embedding.is_some())
        .collect();

    if !rows_with_embeddings.is_empty() {
        let config = state.config.clone();
        let uid = user.uid.clone();
        tokio::spawn(async move {
            if let Err(e) = upsert_pinecone_vectors(&config, &uid, &rows_with_embeddings).await {
                tracing::error!("Screen activity Pinecone upsert failed: {}", e);
            }
        });
    }

    Ok(Json(ScreenActivitySyncResponse {
        synced: written,
        last_id,
    }))
}

/// Upsert screen activity embeddings to Pinecone ns3 via REST API.
async fn upsert_pinecone_vectors(
    config: &crate::config::Config,
    uid: &str,
    rows: &[crate::models::screen_activity::ScreenActivityRow],
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let api_key = config
        .pinecone_api_key
        .as_ref()
        .ok_or("PINECONE_API_KEY not configured")?;
    let host = config
        .pinecone_host
        .as_ref()
        .ok_or("PINECONE_HOST not configured")?;

    let vectors: Vec<serde_json::Value> = rows
        .iter()
        .filter_map(|row| {
            let embedding = row.embedding.as_ref()?;
            // Parse timestamp to unix epoch
            let ts = chrono::DateTime::parse_from_rfc3339(&row.timestamp)
                .or_else(|_| chrono::DateTime::parse_from_str(&row.timestamp, "%Y-%m-%d %H:%M:%S"))
                .map(|dt| dt.timestamp())
                .unwrap_or(0);

            Some(serde_json::json!({
                "id": format!("{}-sa-{}", uid, row.id),
                "values": embedding,
                "metadata": {
                    "uid": uid,
                    "screenshot_id": row.id.to_string(),
                    "timestamp": ts,
                    "appName": row.app_name,
                }
            }))
        })
        .collect();

    if vectors.is_empty() {
        return Ok(());
    }

    let client = reqwest::Client::new();
    let url = format!("{}/vectors/upsert", host);

    // Pinecone limit: 100 vectors per upsert
    for chunk in vectors.chunks(100) {
        let body = serde_json::json!({
            "vectors": chunk,
            "namespace": "ns3"
        });

        let resp = client
            .post(&url)
            .header("Api-Key", api_key)
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await?;

        if !resp.status().is_success() {
            let error_text = resp.text().await?;
            tracing::error!("Pinecone upsert error: {}", error_text);
            return Err(format!("Pinecone upsert failed: {}", error_text).into());
        }
    }

    tracing::info!(
        "Screen activity Pinecone upsert uid={} count={}",
        uid,
        vectors.len()
    );
    Ok(())
}

pub fn screen_activity_routes() -> Router<AppState> {
    Router::new().route("/v1/screen-activity/sync", post(sync_screen_activity))
}
