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

#[cfg(test)]
mod tests {
    use super::*;

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
}
