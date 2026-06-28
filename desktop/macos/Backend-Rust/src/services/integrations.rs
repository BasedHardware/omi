// App integrations service - External webhook triggers
// Port of Python backend utils/app_integrations.py

use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::time::Duration;

use crate::models::{App, Conversation, TriggerEvent};

/// Truncate a string to at most `max_bytes` bytes at a valid UTF-8 character boundary.
fn truncate_str(s: &str, max_bytes: usize) -> &str {
    if s.len() <= max_bytes {
        return s;
    }
    let mut end = max_bytes;
    while end > 0 && !s.is_char_boundary(end) {
        end -= 1;
    }
    &s[..end]
}

/// Response from an app's webhook
#[derive(Debug, Clone, Deserialize)]
pub struct WebhookResponse {
    /// Optional message to display to the user
    pub message: Option<String>,
}

/// Result of triggering an integration
#[derive(Debug, Clone, Serialize)]
pub struct IntegrationResult {
    pub app_id: String,
    pub app_name: String,
    pub success: bool,
    pub message: Option<String>,
    pub error: Option<String>,
}

/// Integration service for triggering external app webhooks
pub struct IntegrationService {
    client: Client,
}

impl IntegrationService {
    /// Create a new integration service
    pub fn new() -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("Failed to create HTTP client");

        Self { client }
    }

    /// Trigger external integrations for a newly created conversation
    /// This is called after a conversation is saved to Firestore
    ///
    /// Returns a list of results from each triggered integration
    pub async fn trigger_conversation_created(
        &self,
        uid: &str,
        conversation: &Conversation,
        enabled_apps: &[App],
    ) -> Vec<IntegrationResult> {
        // Don't trigger for discarded conversations
        if conversation.discarded {
            tracing::debug!("Skipping integration triggers for discarded conversation");
            return vec![];
        }

        // Filter to apps that:
        // 1. Have external_integration capability
        // 2. Are enabled by the user
        // 3. Have triggers_on = memory_creation
        // 4. Have a webhook_url configured
        let triggered_apps: Vec<&App> = enabled_apps
            .iter()
            .filter(|app| {
                if let Some(ref integration) = app.external_integration {
                    integration.triggers_on == TriggerEvent::MemoryCreation
                        && !integration.webhook_url.is_empty()
                } else {
                    false
                }
            })
            .collect();

        if triggered_apps.is_empty() {
            tracing::debug!("No apps to trigger for conversation {}", conversation.id);
            return vec![];
        }

        tracing::info!(
            "Triggering {} app integrations for conversation {}",
            triggered_apps.len(),
            conversation.id
        );

        // Trigger all apps concurrently
        let mut handles = vec![];

        for app in triggered_apps {
            let client = self.client.clone();
            let uid = uid.to_string();
            let conversation = conversation.clone();
            let app = app.clone();

            let handle = tokio::spawn(async move {
                Self::call_webhook(&client, &uid, &conversation, &app).await
            });

            handles.push(handle);
        }

        // Collect results
        let mut results = vec![];
        for handle in handles {
            match handle.await {
                Ok(result) => results.push(result),
                Err(e) => {
                    tracing::error!("Task join error: {}", e);
                }
            }
        }

        results
    }

    /// Call a single app's webhook with conversation data
    async fn call_webhook(
        client: &Client,
        uid: &str,
        conversation: &Conversation,
        app: &App,
    ) -> IntegrationResult {
        let integration = match &app.external_integration {
            Some(i) => i,
            None => {
                return IntegrationResult {
                    app_id: app.id.clone(),
                    app_name: app.name.clone(),
                    success: false,
                    message: None,
                    error: Some("No integration config".to_string()),
                };
            }
        };

        // Build webhook URL with uid parameter
        let mut url = integration.webhook_url.clone();
        if url.contains('?') {
            url.push_str(&format!("&uid={}", uid));
        } else {
            url.push_str(&format!("?uid={}", uid));
        }

        tracing::info!(
            "Calling webhook for app {} at {}",
            app.id,
            integration.webhook_url
        );

        // Serialize conversation to JSON
        let payload = match serde_json::to_value(conversation) {
            Ok(v) => v,
            Err(e) => {
                return IntegrationResult {
                    app_id: app.id.clone(),
                    app_name: app.name.clone(),
                    success: false,
                    message: None,
                    error: Some(format!("Failed to serialize conversation: {}", e)),
                };
            }
        };

        // Make the webhook call
        match client.post(&url).json(&payload).send().await {
            Ok(response) => {
                let status = response.status();

                if !status.is_success() {
                    let error_text = response
                        .text()
                        .await
                        .unwrap_or_else(|_| "Unknown error".to_string());
                    let truncated = truncate_str(&error_text, 100);
                    tracing::warn!(
                        "Webhook failed for app {}: status={}, error={}",
                        app.id,
                        status,
                        truncated
                    );

                    return IntegrationResult {
                        app_id: app.id.clone(),
                        app_name: app.name.clone(),
                        success: false,
                        message: None,
                        error: Some(format!("HTTP {}: {}", status, truncated)),
                    };
                }

                // Parse response
                let message = match response.json::<WebhookResponse>().await {
                    Ok(resp) => resp.message,
                    Err(_) => None, // Response might not be JSON, that's OK
                };

                tracing::info!(
                    "Webhook succeeded for app {}: message={:?}",
                    app.id,
                    message
                );

                IntegrationResult {
                    app_id: app.id.clone(),
                    app_name: app.name.clone(),
                    success: true,
                    message,
                    error: None,
                }
            }
            Err(e) => {
                tracing::error!("Webhook request failed for app {}: {}", app.id, e);

                IntegrationResult {
                    app_id: app.id.clone(),
                    app_name: app.name.clone(),
                    success: false,
                    message: None,
                    error: Some(format!("Request failed: {}", e)),
                }
            }
        }
    }

    /// Trigger integrations for realtime transcript processing
    /// Called when transcript segments are processed in real-time
    pub async fn trigger_transcript_processed(
        &self,
        uid: &str,
        segments: &[Value],
        conversation_id: Option<&str>,
        enabled_apps: &[App],
    ) -> Vec<IntegrationResult> {
        // Filter to apps that trigger on transcript_processed
        let triggered_apps: Vec<&App> = enabled_apps
            .iter()
            .filter(|app| {
                if let Some(ref integration) = app.external_integration {
                    integration.triggers_on == TriggerEvent::TranscriptProcessed
                        && !integration.webhook_url.is_empty()
                } else {
                    false
                }
            })
            .collect();

        if triggered_apps.is_empty() {
            return vec![];
        }

        tracing::info!(
            "Triggering {} realtime integrations for {} segments",
            triggered_apps.len(),
            segments.len()
        );

        let mut handles = vec![];

        for app in triggered_apps {
            let client = self.client.clone();
            let uid = uid.to_string();
            let segments = segments.to_vec();
            let conversation_id = conversation_id.map(|s| s.to_string());
            let app = app.clone();

            let handle = tokio::spawn(async move {
                Self::call_realtime_webhook(&client, &uid, &segments, conversation_id.as_deref(), &app).await
            });

            handles.push(handle);
        }

        let mut results = vec![];
        for handle in handles {
            match handle.await {
                Ok(result) => results.push(result),
                Err(e) => {
                    tracing::error!("Task join error: {}", e);
                }
            }
        }

        results
    }

    /// Call webhook for realtime transcript processing
    async fn call_realtime_webhook(
        client: &Client,
        uid: &str,
        segments: &[Value],
        conversation_id: Option<&str>,
        app: &App,
    ) -> IntegrationResult {
        let integration = match &app.external_integration {
            Some(i) => i,
            None => {
                return IntegrationResult {
                    app_id: app.id.clone(),
                    app_name: app.name.clone(),
                    success: false,
                    message: None,
                    error: Some("No integration config".to_string()),
                };
            }
        };

        let mut url = integration.webhook_url.clone();
        if url.contains('?') {
            url.push_str(&format!("&uid={}", uid));
        } else {
            url.push_str(&format!("?uid={}", uid));
        }

        let payload = serde_json::json!({
            "session_id": uid,
            "segments": segments,
            "conversation_id": conversation_id,
        });

        match client
            .post(&url)
            .json(&payload)
            .timeout(Duration::from_secs(10))
            .send()
            .await
        {
            Ok(response) => {
                let status = response.status();

                if !status.is_success() {
                    return IntegrationResult {
                        app_id: app.id.clone(),
                        app_name: app.name.clone(),
                        success: false,
                        message: None,
                        error: Some(format!("HTTP {}", status)),
                    };
                }

                let message = response
                    .json::<WebhookResponse>()
                    .await
                    .ok()
                    .and_then(|r| r.message);

                IntegrationResult {
                    app_id: app.id.clone(),
                    app_name: app.name.clone(),
                    success: true,
                    message,
                    error: None,
                }
            }
            Err(e) => IntegrationResult {
                app_id: app.id.clone(),
                app_name: app.name.clone(),
                success: false,
                message: None,
                error: Some(format!("Request failed: {}", e)),
            },
        }
    }
}

impl Default for IntegrationService {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_integration_service_creation() {
        let service = IntegrationService::new();
        // Just verify it creates successfully
        assert!(true);
    }
}
