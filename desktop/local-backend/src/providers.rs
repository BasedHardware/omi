use anyhow::{anyhow, Context, Result};
use reqwest::{Client, Method};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::storage::Store;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
}

impl ChatMessage {
    pub fn system(content: impl Into<String>) -> Self {
        Self {
            role: "system".to_string(),
            content: content.into(),
        }
    }

    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: "user".to_string(),
            content: content.into(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProviderHttpRequest {
    pub method: Method,
    pub url: String,
    pub authorization: String,
    pub body: Value,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OpenAiCompatibleConfig {
    pub base_url: String,
    pub model: String,
    pub api_key: String,
}

#[derive(Clone)]
pub struct OpenAiCompatibleProvider {
    config: OpenAiCompatibleConfig,
    client: Client,
}

impl OpenAiCompatibleProvider {
    pub fn new(config: OpenAiCompatibleConfig) -> Self {
        Self {
            config,
            client: Client::new(),
        }
    }

    pub fn build_chat_completions_request(
        &self,
        messages: Vec<ChatMessage>,
    ) -> ProviderHttpRequest {
        ProviderHttpRequest {
            method: Method::POST,
            url: format!(
                "{}/chat/completions",
                self.config.base_url.trim_end_matches('/')
            ),
            authorization: format!("Bearer {}", self.config.api_key),
            body: json!({
                "model": self.config.model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"}
            }),
        }
    }

    pub async fn complete_json(&self, messages: Vec<ChatMessage>) -> Result<Value> {
        let request = self.build_chat_completions_request(messages);
        let response: Value = self
            .client
            .request(request.method, request.url)
            .header("authorization", request.authorization)
            .json(&request.body)
            .send()
            .await
            .context("failed to send OpenAI-compatible chat completion request")?
            .error_for_status()
            .context("OpenAI-compatible chat completion request failed")?
            .json()
            .await
            .context("failed to decode OpenAI-compatible chat completion response")?;

        let content = response["choices"][0]["message"]["content"]
            .as_str()
            .ok_or_else(|| anyhow!("OpenAI-compatible response did not include message content"))?;
        serde_json::from_str(content).context("provider message content was not valid JSON")
    }
}

pub fn configured_openai_provider(store: &Store) -> Result<Option<OpenAiCompatibleProvider>> {
    let Some(config) = load_openai_config(store)? else {
        return Ok(None);
    };
    Ok(Some(OpenAiCompatibleProvider::new(config)))
}

pub fn load_openai_config(store: &Store) -> Result<Option<OpenAiCompatibleConfig>> {
    for key in ["ai_provider", "provider"] {
        let Some(setting) = store.settings().get(key)? else {
            continue;
        };
        let value: Value = serde_json::from_str(&setting.value_json)
            .with_context(|| format!("failed to parse {key} provider setting"))?;
        let kind = value["kind"].as_str().unwrap_or_default();
        if kind != "openai" && kind != "openai_compatible" {
            continue;
        }

        let base_url = value["base_url"]
            .as_str()
            .unwrap_or("https://api.openai.com/v1")
            .to_string();
        validate_provider_base_url(&base_url)?;
        let model = value["model"].as_str().unwrap_or("gpt-4o-mini").to_string();
        let api_key = value["api_key"]
            .as_str()
            .or_else(|| value["key"].as_str())
            .unwrap_or_default()
            .to_string();

        if api_key.trim().is_empty() {
            continue;
        }

        return Ok(Some(OpenAiCompatibleConfig {
            base_url,
            model,
            api_key,
        }));
    }

    Ok(None)
}

pub fn validate_provider_setting(value: &Value) -> Result<()> {
    let kind = value["kind"].as_str().unwrap_or_default();
    if kind != "openai" && kind != "openai_compatible" {
        return Ok(());
    }

    let base_url = value["base_url"]
        .as_str()
        .unwrap_or("https://api.openai.com/v1");
    validate_provider_base_url(base_url)
}

fn validate_provider_base_url(base_url: &str) -> Result<()> {
    let url = reqwest::Url::parse(base_url)
        .with_context(|| format!("provider base_url is not a valid URL: {base_url}"))?;
    match url.scheme() {
        "http" | "https" => {}
        scheme => return Err(anyhow!("provider base_url scheme is not allowed: {scheme}")),
    }

    let host = url
        .host_str()
        .ok_or_else(|| anyhow!("provider base_url must include a host"))?
        .trim_end_matches('.')
        .to_ascii_lowercase();
    if is_denied_provider_host(&host) {
        return Err(anyhow!(
            "provider base_url host is not allowed in local daemon mode: {host}"
        ));
    }
    Ok(())
}

fn is_denied_provider_host(host: &str) -> bool {
    matches!(host, "api.omi.me" | "api.omiapi.com")
        || (host.starts_with("desktop-backend-") && host.ends_with(".a.run.app"))
        || host == "firebase.google.com"
        || host.ends_with(".firebase.google.com")
        || host.ends_with(".firebaseio.com")
        || host.ends_with(".firebaseapp.com")
        || host.ends_with(".firebasestorage.app")
        || matches!(
            host,
            "googleapis.com"
                | "identitytoolkit.googleapis.com"
                | "securetoken.googleapis.com"
                | "firestore.googleapis.com"
                | "firebasestorage.googleapis.com"
                | "firebase.googleapis.com"
                | "www.googleapis.com"
                | "oauth2.googleapis.com"
        )
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{routing::post, Json, Router};
    use serde_json::{json, Map};
    use tokio::net::TcpListener;

    #[test]
    fn openai_compatible_request_uses_configured_endpoint_model_and_key() {
        let provider = OpenAiCompatibleProvider::new(OpenAiCompatibleConfig {
            base_url: "http://localhost:11434/v1/".to_string(),
            model: "local-model".to_string(),
            api_key: "test-key".to_string(),
        });

        let request = provider.build_chat_completions_request(vec![
            ChatMessage::system("Return JSON."),
            ChatMessage::user("Summarize."),
        ]);

        assert_eq!(request.method, Method::POST);
        assert_eq!(request.url, "http://localhost:11434/v1/chat/completions");
        assert_eq!(request.authorization, "Bearer test-key");
        assert_eq!(request.body["model"], "local-model");
        assert_eq!(request.body["temperature"], 0);
        assert_eq!(request.body["messages"][0]["role"], "system");
        assert_eq!(request.body["messages"][1]["content"], "Summarize.");
    }

    #[test]
    fn load_openai_config_reads_structured_local_setting() -> Result<()> {
        let store = Store::open_in_memory()?;
        let mut settings = Map::new();
        settings.insert(
            "ai_provider".to_string(),
            json!({
                "kind": "openai_compatible",
                "base_url": "http://127.0.0.1:43210/v1",
                "model": "stub-model",
                "api_key": "local-test-key"
            }),
        );
        store.settings().upsert_many(settings)?;

        let config = load_openai_config(&store)?.expect("provider should be configured");
        assert_eq!(config.base_url, "http://127.0.0.1:43210/v1");
        assert_eq!(config.model, "stub-model");
        assert_eq!(config.api_key, "local-test-key");

        Ok(())
    }

    #[test]
    fn provider_validation_denies_omi_firebase_and_google_hosts() {
        for base_url in [
            "https://api.omi.me/v1",
            "https://api.omiapi.com/v1",
            "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/v1",
            "https://identitytoolkit.googleapis.com/v1",
            "https://based-hardware.firebaseio.com",
            "https://based-hardware.firebaseapp.com",
            "https://based-hardware.firebasestorage.app",
        ] {
            assert!(
                validate_provider_setting(&json!({
                    "kind": "openai_compatible",
                    "base_url": base_url,
                    "api_key": "key"
                }))
                .is_err(),
                "{base_url} should be denied"
            );
        }
    }

    #[test]
    fn provider_validation_allows_direct_provider_and_loopback_hosts() -> Result<()> {
        for base_url in [
            "https://api.openai.com/v1",
            "https://api.anthropic.com/v1",
            "https://generativelanguage.googleapis.com/v1beta",
            "http://127.0.0.1:11434/v1",
            "http://localhost:43210/v1",
        ] {
            validate_provider_setting(&json!({
                "kind": "openai_compatible",
                "base_url": base_url,
                "api_key": "key"
            }))?;
        }
        Ok(())
    }

    #[tokio::test]
    async fn openai_compatible_provider_uses_local_stub_endpoint() -> Result<()> {
        let app = Router::new().route(
            "/v1/chat/completions",
            post(|| async {
                Json(json!({
                    "choices": [{
                        "message": {
                            "content": "{\"title\":\"Stub title\",\"overview\":\"Stub overview\",\"action_items\":[],\"memories\":[]}"
                        }
                    }]
                }))
            }),
        );
        let listener = TcpListener::bind("127.0.0.1:0").await?;
        let addr = listener.local_addr()?;
        tokio::spawn(async move {
            axum::serve(listener, app)
                .await
                .expect("stub server failed");
        });

        let provider = OpenAiCompatibleProvider::new(OpenAiCompatibleConfig {
            base_url: format!("http://{addr}/v1"),
            model: "stub-model".to_string(),
            api_key: "local-test-key".to_string(),
        });

        let response = provider
            .complete_json(vec![ChatMessage::user("Summarize locally.")])
            .await?;
        assert_eq!(response["title"], "Stub title");
        assert_eq!(response["overview"], "Stub overview");

        Ok(())
    }
}
