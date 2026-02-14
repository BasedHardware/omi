// Redis service for conversation visibility
// Mirrors the Python backend's redis_db.py functionality for sharing conversations

use redis::{AsyncCommands, Client, ConnectionAddr, ConnectionInfo, RedisConnectionInfo};
use std::sync::Arc;
use tokio::sync::RwLock;

/// Redis service for conversation visibility and sharing
pub struct RedisService {
    client: Client,
    connection: Arc<RwLock<Option<redis::aio::MultiplexedConnection>>>,
}

/// Review data stored in Redis
#[derive(Debug, Clone)]
pub struct RedisReview {
    pub score: i32,
}

impl RedisService {
    /// Create a new Redis service with explicit connection parameters
    /// This avoids URL encoding issues with special characters in passwords
    pub fn new_with_params(host: &str, port: u16, password: Option<&str>) -> Result<Self, redis::RedisError> {
        let info = ConnectionInfo {
            addr: ConnectionAddr::Tcp(host.to_string(), port),
            redis: RedisConnectionInfo {
                db: 0,
                username: Some("default".to_string()),
                password: password.map(|p| p.to_string()),
            },
        };
        let client = Client::open(info)?;
        Ok(Self {
            client,
            connection: Arc::new(RwLock::new(None)),
        })
    }

    /// Create a new Redis service from URL (legacy, may have encoding issues)
    pub fn new(redis_url: &str) -> Result<Self, redis::RedisError> {
        let client = Client::open(redis_url)?;
        Ok(Self {
            client,
            connection: Arc::new(RwLock::new(None)),
        })
    }

    /// Get or create a connection
    async fn get_connection(&self) -> Result<redis::aio::MultiplexedConnection, redis::RedisError> {
        // Check if we have a cached connection
        {
            let conn = self.connection.read().await;
            if let Some(c) = conn.as_ref() {
                return Ok(c.clone());
            }
        }

        // Create new connection
        let conn = self.client.get_multiplexed_async_connection().await?;

        // Cache it
        {
            let mut cached = self.connection.write().await;
            *cached = Some(conn.clone());
        }

        Ok(conn)
    }

    // ============================================================================
    // CONVERSATION VISIBILITY - matches Python backend redis_db.py
    // ============================================================================

    /// Store conversation_id -> uid mapping for visibility lookup
    /// Key format: memories-visibility:{conversation_id}
    pub async fn store_conversation_to_uid(
        &self,
        conversation_id: &str,
        uid: &str,
    ) -> Result<(), redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("memories-visibility:{}", conversation_id);
        let _: () = conn.set(&key, uid).await?;
        tracing::info!("Stored conversation visibility: {} -> {}", conversation_id, uid);
        Ok(())
    }

    /// Remove conversation_id -> uid mapping
    pub async fn remove_conversation_to_uid(
        &self,
        conversation_id: &str,
    ) -> Result<(), redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("memories-visibility:{}", conversation_id);
        let _: () = conn.del(&key).await?;
        tracing::info!("Removed conversation visibility: {}", conversation_id);
        Ok(())
    }

    /// Get the uid that owns a public conversation
    /// Returns None if conversation is not public/shared
    pub async fn get_conversation_uid(
        &self,
        conversation_id: &str,
    ) -> Result<Option<String>, redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("memories-visibility:{}", conversation_id);
        let uid: Option<String> = conn.get(&key).await?;
        Ok(uid)
    }

    /// Add conversation to the public conversations set
    /// Key: public-memories (SET)
    pub async fn add_public_conversation(
        &self,
        conversation_id: &str,
    ) -> Result<(), redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let _: () = conn.sadd("public-memories", conversation_id).await?;
        tracing::info!("Added conversation to public set: {}", conversation_id);
        Ok(())
    }

    /// Remove conversation from the public conversations set
    pub async fn remove_public_conversation(
        &self,
        conversation_id: &str,
    ) -> Result<(), redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let _: () = conn.srem("public-memories", conversation_id).await?;
        tracing::info!("Removed conversation from public set: {}", conversation_id);
        Ok(())
    }

    /// Get all public conversation IDs
    pub async fn get_public_conversations(&self) -> Result<Vec<String>, redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let ids: Vec<String> = conn.smembers("public-memories").await?;
        Ok(ids)
    }

    /// Check if Redis connection is healthy
    pub async fn health_check(&self) -> Result<bool, redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let pong: String = redis::cmd("PING").query_async(&mut conn).await?;
        Ok(pong == "PONG")
    }

    // ============================================================================
    // TASK SHARING
    // ============================================================================

    /// Store task share data in Redis with 30-day TTL
    /// Key format: task_share:{token}
    pub async fn store_task_share(
        &self,
        token: &str,
        uid: &str,
        display_name: &str,
        task_ids: &[String],
    ) -> Result<(), redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("task_share:{}", token);
        let value = serde_json::json!({
            "uid": uid,
            "display_name": display_name,
            "task_ids": task_ids,
        });
        let _: () = conn.set_ex(&key, value.to_string(), 30 * 24 * 60 * 60).await?;
        tracing::info!("Stored task share: {} -> {} tasks", token, task_ids.len());
        Ok(())
    }

    /// Get task share data from Redis
    /// Returns (uid, display_name, task_ids) or None if expired/missing
    pub async fn get_task_share(
        &self,
        token: &str,
    ) -> Result<Option<(String, String, Vec<String>)>, redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("task_share:{}", token);
        let raw: Option<String> = conn.get(&key).await?;
        match raw {
            Some(data) => {
                if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&data) {
                    let uid = parsed["uid"].as_str().unwrap_or("").to_string();
                    let display_name = parsed["display_name"].as_str().unwrap_or("").to_string();
                    let task_ids: Vec<String> = parsed["task_ids"]
                        .as_array()
                        .map(|arr| arr.iter().filter_map(|v| v.as_str().map(String::from)).collect())
                        .unwrap_or_default();
                    Ok(Some((uid, display_name, task_ids)))
                } else {
                    Ok(None)
                }
            }
            None => Ok(None),
        }
    }

    /// Atomically try to accept a task share for a user
    /// Returns true if this is a new acceptance, false if already accepted
    pub async fn try_accept_task_share(
        &self,
        token: &str,
        uid: &str,
    ) -> Result<bool, redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("task_share:{}:accepted", token);
        let added: i32 = conn.sadd(&key, uid).await?;
        // Set 30-day TTL on the accepted set
        let _: () = conn.expire(&key, 30 * 24 * 60 * 60).await?;
        Ok(added == 1)
    }

    // ============================================================================
    // APP INSTALLS - matches Python backend redis_db.py
    // ============================================================================

    /// Get installs count for multiple apps
    /// Key format: plugins:{app_id}:installs
    /// Returns a HashMap of app_id -> installs count
    pub async fn get_apps_installs_count(
        &self,
        app_ids: &[String],
    ) -> Result<std::collections::HashMap<String, i32>, redis::RedisError> {
        if app_ids.is_empty() {
            return Ok(std::collections::HashMap::new());
        }

        let mut conn = self.get_connection().await?;
        let keys: Vec<String> = app_ids
            .iter()
            .map(|id| format!("plugins:{}:installs", id))
            .collect();

        let counts: Vec<Option<String>> = conn.mget(&keys).await?;

        let result: std::collections::HashMap<String, i32> = app_ids
            .iter()
            .zip(counts.iter())
            .map(|(id, count)| {
                let installs = count
                    .as_ref()
                    .and_then(|s| s.parse::<i32>().ok())
                    .unwrap_or(0);
                (id.clone(), installs)
            })
            .collect();

        Ok(result)
    }

    // ============================================================================
    // APP REVIEWS - matches Python backend redis_db.py
    // ============================================================================

    /// Get reviews for multiple apps
    /// Key format: plugins:{app_id}:reviews
    /// Returns a HashMap of app_id -> HashMap of uid -> review
    /// Python stores reviews as: {uid: {score: int, review: str, ...}}
    pub async fn get_apps_reviews(
        &self,
        app_ids: &[String],
    ) -> Result<std::collections::HashMap<String, Vec<RedisReview>>, redis::RedisError> {
        if app_ids.is_empty() {
            return Ok(std::collections::HashMap::new());
        }

        let mut conn = self.get_connection().await?;
        let keys: Vec<String> = app_ids
            .iter()
            .map(|id| format!("plugins:{}:reviews", id))
            .collect();

        let reviews_data: Vec<Option<String>> = conn.mget(&keys).await?;

        let mut result: std::collections::HashMap<String, Vec<RedisReview>> =
            std::collections::HashMap::new();

        for (id, data) in app_ids.iter().zip(reviews_data.iter()) {
            if let Some(raw) = data {
                // Python stores reviews as a dict: {uid: {score: int, review: str, ...}}
                // We need to parse this to extract scores
                let reviews = parse_python_reviews(raw);
                if !reviews.is_empty() {
                    result.insert(id.clone(), reviews);
                }
            }
        }

        Ok(result)
    }
}

/// Parse Python dict format for reviews
/// Format: {'uid1': {'score': 5, 'review': 'text', ...}, 'uid2': {...}}
fn parse_python_reviews(raw: &str) -> Vec<RedisReview> {
    let mut reviews = Vec::new();

    // Try to parse as JSON first (newer format)
    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(raw) {
        if let Some(obj) = parsed.as_object() {
            for (_uid, review) in obj {
                if let Some(score) = review.get("score").and_then(|s| s.as_i64()) {
                    reviews.push(RedisReview { score: score as i32 });
                }
            }
        }
        return reviews;
    }

    // Fallback: parse Python dict format using regex
    // Looking for 'score': <number> patterns
    let score_regex = regex::Regex::new(r"'score':\s*(\d+)").unwrap();
    for cap in score_regex.captures_iter(raw) {
        if let Some(score_match) = cap.get(1) {
            if let Ok(score) = score_match.as_str().parse::<i32>() {
                reviews.push(RedisReview { score });
            }
        }
    }

    reviews
}
