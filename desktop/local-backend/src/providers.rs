use anyhow::{anyhow, Context, Result};
use reqwest::{Client, Method};
use std::collections::BTreeMap;

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

pub const PROVIDER_POLICY_SETTING_KEY: &str = "provider_policy";
pub const PROVIDER_POLICY_VERSION: u32 = 1;

pub const SLOT_CHAT: &str = "chat";
pub const SLOT_POST_TRANSCRIPT: &str = "post_transcript";
pub const SLOT_PROACTIVE: &str = "proactive";
pub const SLOT_VISION: &str = "vision";
pub const SLOT_STT: &str = "stt";
pub const SLOT_MEMORY_SEARCH: &str = "memory_search";

const LEGACY_SLOT_KEYS: &[(&str, &[&str])] = &[
    (SLOT_POST_TRANSCRIPT, &["ai_provider", "provider"]),
    (SLOT_CHAT, &["chat_provider"]),
    (SLOT_VISION, &["vision_provider"]),
    (SLOT_STT, &["stt_provider"]),
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProviderPolicy {
    pub version: u32,
    #[serde(default)]
    pub provider_accounts: Vec<ProviderAccount>,
    #[serde(default)]
    pub model_slots: BTreeMap<String, ModelSlotTarget>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProviderAccount {
    pub id: String,
    pub kind: String,
    pub base_url: Option<String>,
    pub api_key: Option<String>,
    pub display_name: Option<String>,
    #[serde(default)]
    pub capabilities: ProviderCapabilities,
    pub subscription_integration: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProviderCapabilities {
    #[serde(default)]
    pub chat_completions: bool,
    #[serde(default)]
    pub json_mode: bool,
    #[serde(default)]
    pub tool_calls: bool,
    #[serde(default)]
    pub vision: bool,
    #[serde(default)]
    pub speech_to_text: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelSlotTarget {
    pub provider_account_id: Option<String>,
    pub model_id: String,
    #[serde(default)]
    pub options: ModelSlotOptions,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelSlotOptions {
    pub json_mode: Option<bool>,
    pub tool_support: Option<bool>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ResolvedModelSlot {
    pub slot: String,
    pub provider_account: Option<ProviderAccount>,
    pub model_id: String,
    pub options: ModelSlotOptions,
    pub source: String,
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
    let Some(resolved) = resolve_model_slot(store, SLOT_POST_TRANSCRIPT)? else {
        return Ok(None);
    };
    let Some(account) = resolved.provider_account else {
        return Ok(None);
    };
    if !is_openai_compatible_kind(&account.kind) {
        return Ok(None);
    }
    let base_url = account
        .base_url
        .unwrap_or_else(|| "https://api.openai.com/v1".to_string());
    validate_provider_base_url(&base_url)?;
    Ok(Some(OpenAiCompatibleConfig {
        base_url,
        model: resolved.model_id,
        api_key: account.api_key.unwrap_or_default(),
    }))
}

pub fn load_provider_policy(store: &Store) -> Result<ProviderPolicy> {
    let mut policy = if let Some(setting) = store.settings().get(PROVIDER_POLICY_SETTING_KEY)? {
        let policy: ProviderPolicy = serde_json::from_str(&setting.value_json)
            .context("failed to parse provider_policy setting")?;
        if policy.version != PROVIDER_POLICY_VERSION {
            return Err(anyhow!(
                "unsupported provider_policy version: {}",
                policy.version
            ));
        }
        policy
    } else {
        ProviderPolicy {
            version: PROVIDER_POLICY_VERSION,
            provider_accounts: Vec::new(),
            model_slots: BTreeMap::new(),
        }
    };
    add_legacy_policy_bridge(store, &mut policy)?;
    Ok(policy)
}

pub fn save_provider_policy(store: &Store, policy: ProviderPolicy) -> Result<ProviderPolicy> {
    validate_provider_policy(&policy)?;
    let value = serde_json::to_value(&policy).context("failed to serialize provider policy")?;
    let mut settings = serde_json::Map::new();
    settings.insert(PROVIDER_POLICY_SETTING_KEY.to_string(), value);
    store.settings().upsert_many(settings)?;
    load_provider_policy(store)
}

pub fn resolve_model_slot(store: &Store, slot: &str) -> Result<Option<ResolvedModelSlot>> {
    if slot == SLOT_MEMORY_SEARCH {
        return Ok(Some(ResolvedModelSlot {
            slot: SLOT_MEMORY_SEARCH.to_string(),
            provider_account: None,
            model_id: "local_wiki".to_string(),
            options: ModelSlotOptions::default(),
            source: "default".to_string(),
        }));
    }

    let policy = load_provider_policy(store)?;
    let Some(target) = policy.model_slots.get(slot) else {
        return Ok(None);
    };
    let account = match target.provider_account_id.as_deref() {
        Some(account_id) => Some(
            policy
                .provider_accounts
                .iter()
                .find(|account| account.id == account_id)
                .cloned()
                .ok_or_else(|| {
                    anyhow!("model slot {slot} references missing provider account: {account_id}")
                })?,
        ),
        None => None,
    };
    Ok(Some(ResolvedModelSlot {
        slot: slot.to_string(),
        provider_account: account,
        model_id: target.model_id.clone(),
        options: target.options.clone(),
        source: if target
            .provider_account_id
            .as_deref()
            .is_some_and(|id| id.starts_with("legacy-"))
        {
            "legacy_setting".to_string()
        } else {
            "provider_policy".to_string()
        },
    }))
}

pub fn validate_provider_policy(policy: &ProviderPolicy) -> Result<()> {
    if policy.version != PROVIDER_POLICY_VERSION {
        return Err(anyhow!(
            "provider_policy version must be {}",
            PROVIDER_POLICY_VERSION
        ));
    }
    let mut account_ids = std::collections::BTreeSet::new();
    for account in &policy.provider_accounts {
        if account.id.trim().is_empty() {
            return Err(anyhow!("provider account id is required"));
        }
        if !account_ids.insert(account.id.as_str()) {
            return Err(anyhow!("duplicate provider account id: {}", account.id));
        }
        validate_provider_account(account)?;
    }
    for slot in [
        SLOT_CHAT,
        SLOT_POST_TRANSCRIPT,
        SLOT_PROACTIVE,
        SLOT_VISION,
        SLOT_STT,
        SLOT_MEMORY_SEARCH,
    ] {
        if let Some(target) = policy.model_slots.get(slot) {
            validate_model_slot_target(slot, target, &account_ids)?;
        }
    }
    for slot in policy.model_slots.keys() {
        if ![
            SLOT_CHAT,
            SLOT_POST_TRANSCRIPT,
            SLOT_PROACTIVE,
            SLOT_VISION,
            SLOT_STT,
            SLOT_MEMORY_SEARCH,
        ]
        .contains(&slot.as_str())
        {
            return Err(anyhow!("unsupported model slot: {slot}"));
        }
    }
    Ok(())
}

/// Settings keys validated on `PUT /v1/settings` for hybrid direct providers.
pub const HYBRID_PROVIDER_SETTING_KEYS: &[&str] = &[
    "ai_provider",
    "provider",
    "stt_provider",
    "chat_provider",
    "embedding_provider",
    "vision_provider",
];

fn add_legacy_policy_bridge(store: &Store, policy: &mut ProviderPolicy) -> Result<()> {
    for (slot, keys) in LEGACY_SLOT_KEYS {
        if policy.model_slots.contains_key(*slot) {
            continue;
        }
        for key in *keys {
            let Some(setting) = store.settings().get(key)? else {
                continue;
            };
            let value: Value = serde_json::from_str(&setting.value_json)
                .with_context(|| format!("failed to parse {key} provider setting"))?;
            if value.is_null() {
                continue;
            }
            let Some(account) = legacy_provider_account(slot, key, &value)? else {
                continue;
            };
            let model_id = value["model"]
                .as_str()
                .unwrap_or("gpt-5.4-mini")
                .to_string();
            policy.provider_accounts.push(account.clone());
            policy.model_slots.insert(
                (*slot).to_string(),
                ModelSlotTarget {
                    provider_account_id: Some(account.id),
                    model_id,
                    options: ModelSlotOptions {
                        json_mode: Some(matches!(*slot, SLOT_POST_TRANSCRIPT | SLOT_PROACTIVE)),
                        tool_support: None,
                    },
                },
            );
            break;
        }
    }
    Ok(())
}

fn legacy_provider_account(
    slot: &str,
    key: &str,
    value: &Value,
) -> Result<Option<ProviderAccount>> {
    let kind = value["kind"].as_str().unwrap_or_default();
    if !is_openai_compatible_kind(kind) {
        return Ok(None);
    }
    let base_url = value["base_url"]
        .as_str()
        .unwrap_or("https://api.openai.com/v1")
        .to_string();
    let account = ProviderAccount {
        id: format!("legacy-{slot}"),
        kind: "openai_compatible".to_string(),
        base_url: Some(base_url),
        api_key: value["api_key"]
            .as_str()
            .or_else(|| value["key"].as_str())
            .map(ToString::to_string),
        display_name: Some(format!("Legacy {key}")),
        capabilities: ProviderCapabilities {
            chat_completions: true,
            json_mode: true,
            tool_calls: false,
            vision: slot == SLOT_VISION,
            speech_to_text: slot == SLOT_STT,
        },
        subscription_integration: value["subscription_integration"]
            .as_str()
            .map(ToString::to_string),
    };
    validate_provider_account(&account)?;
    Ok(Some(account))
}

fn validate_provider_account(account: &ProviderAccount) -> Result<()> {
    if !is_openai_compatible_kind(&account.kind) {
        return Ok(());
    }
    let base_url = account
        .base_url
        .as_deref()
        .unwrap_or("https://api.openai.com/v1");
    validate_provider_base_url(base_url)?;
    let has_api_key = account
        .api_key
        .as_deref()
        .is_some_and(|api_key| !api_key.trim().is_empty());
    let has_subscription_integration = account
        .subscription_integration
        .as_deref()
        .is_some_and(|value| !value.trim().is_empty());
    if !has_api_key && !has_subscription_integration && !is_loopback_provider_base_url(base_url)? {
        return Err(anyhow!(
            "api_key or subscription_integration is required for non-loopback provider account {}",
            account.id
        ));
    }
    Ok(())
}

fn validate_model_slot_target(
    slot: &str,
    target: &ModelSlotTarget,
    account_ids: &std::collections::BTreeSet<&str>,
) -> Result<()> {
    if target.model_id.trim().is_empty() {
        return Err(anyhow!("model slot {slot} requires model_id"));
    }
    if slot == SLOT_MEMORY_SEARCH && target.model_id != "local_wiki" {
        return Err(anyhow!(
            "memory_search must use local_wiki in this local profile"
        ));
    }
    if let Some(account_id) = target.provider_account_id.as_deref() {
        if !account_ids.contains(account_id) {
            return Err(anyhow!(
                "model slot {slot} references missing provider account: {account_id}"
            ));
        }
    } else if slot != SLOT_MEMORY_SEARCH {
        return Err(anyhow!(
            "model slot {slot} requires provider_account_id unless it is memory_search"
        ));
    }
    Ok(())
}

pub fn validate_provider_setting(value: &Value) -> Result<()> {
    if value.is_null() {
        return Ok(());
    }
    let kind = value["kind"].as_str().unwrap_or_default();
    if kind != "openai" && kind != "openai_compatible" {
        return Ok(());
    }

    let base_url = value["base_url"]
        .as_str()
        .unwrap_or("https://api.openai.com/v1");
    validate_provider_base_url(base_url)?;
    let api_key = value["api_key"]
        .as_str()
        .or_else(|| value["key"].as_str())
        .unwrap_or_default();
    let subscription_integration = value["subscription_integration"]
        .as_str()
        .unwrap_or_default();
    if api_key.trim().is_empty()
        && subscription_integration.trim().is_empty()
        && !is_loopback_provider_base_url(base_url)?
    {
        return Err(anyhow!(
            "api_key or subscription_integration is required for non-loopback provider"
        ));
    }
    Ok(())
}

pub fn validate_hybrid_provider_setting(key: &str, value: &Value) -> Result<()> {
    if value.is_null() {
        return Ok(());
    }
    if !HYBRID_PROVIDER_SETTING_KEYS.contains(&key) {
        return Ok(());
    }
    validate_provider_setting(value)
}

pub fn is_provider_configured(value: &Value) -> bool {
    if value.is_null() {
        return false;
    }
    let kind = value["kind"].as_str().unwrap_or_default();
    if kind != "openai" && kind != "openai_compatible" {
        return false;
    }
    let api_key = value["api_key"]
        .as_str()
        .or_else(|| value["key"].as_str())
        .unwrap_or_default();
    !api_key.trim().is_empty()
        || value["base_url"]
            .as_str()
            .is_some_and(|url| url.contains("127.0.0.1") || url.contains("localhost"))
}

fn is_openai_compatible_kind(kind: &str) -> bool {
    kind == "openai" || kind == "openai_compatible"
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

fn is_loopback_provider_base_url(base_url: &str) -> Result<bool> {
    let url = reqwest::Url::parse(base_url)
        .with_context(|| format!("provider base_url is not a valid URL: {base_url}"))?;
    let Some(host) = url.host_str() else {
        return Ok(false);
    };
    Ok(matches!(host, "localhost" | "127.0.0.1" | "::1"))
}

pub async fn test_configured_provider(store: &Store, key: &str) -> Result<String> {
    let Some(setting) = store.settings().get(key)? else {
        return Err(anyhow!("setting {key} is not configured"));
    };
    let value: Value = serde_json::from_str(&setting.value_json)
        .with_context(|| format!("failed to parse {key}"))?;
    if value.is_null() {
        return Err(anyhow!("setting {key} is not configured"));
    }
    let kind = value["kind"].as_str().unwrap_or_default();
    if kind != "openai" && kind != "openai_compatible" {
        return Err(anyhow!(
            "test connection supports openai_compatible providers only"
        ));
    }
    let provider = load_openai_config_from_value(&value)?;
    let client = OpenAiCompatibleProvider::new(provider);
    let _ = client
        .complete_json(vec![
            ChatMessage::system("Reply with JSON only: {\"ok\":true}"),
            ChatMessage::user("ping"),
        ])
        .await?;
    Ok(format!("{key} responded successfully"))
}

fn load_openai_config_from_value(value: &Value) -> Result<OpenAiCompatibleConfig> {
    let kind = value["kind"].as_str().unwrap_or_default();
    if kind != "openai" && kind != "openai_compatible" {
        return Err(anyhow!("unsupported provider kind: {kind}"));
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
    if api_key.trim().is_empty()
        && !base_url.contains("127.0.0.1")
        && !base_url.contains("localhost")
    {
        return Err(anyhow!("api_key is required for test connection"));
    }
    Ok(OpenAiCompatibleConfig {
        base_url,
        model,
        api_key,
    })
}

pub fn is_denied_provider_host(host: &str) -> bool {
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
    fn provider_policy_round_trips_through_settings() -> Result<()> {
        let store = Store::open_in_memory()?;
        let mut slots = BTreeMap::new();
        slots.insert(
            SLOT_POST_TRANSCRIPT.to_string(),
            ModelSlotTarget {
                provider_account_id: Some("local-ollama".to_string()),
                model_id: "llama3.2".to_string(),
                options: ModelSlotOptions {
                    json_mode: Some(true),
                    tool_support: Some(false),
                },
            },
        );
        slots.insert(
            SLOT_MEMORY_SEARCH.to_string(),
            ModelSlotTarget {
                provider_account_id: None,
                model_id: "local_wiki".to_string(),
                options: ModelSlotOptions::default(),
            },
        );
        let policy = ProviderPolicy {
            version: PROVIDER_POLICY_VERSION,
            provider_accounts: vec![ProviderAccount {
                id: "local-ollama".to_string(),
                kind: "openai_compatible".to_string(),
                base_url: Some("http://127.0.0.1:11434/v1".to_string()),
                api_key: None,
                display_name: Some("Local Ollama".to_string()),
                capabilities: ProviderCapabilities {
                    chat_completions: true,
                    json_mode: true,
                    tool_calls: false,
                    vision: false,
                    speech_to_text: false,
                },
                subscription_integration: None,
            }],
            model_slots: slots,
        };

        let saved = save_provider_policy(&store, policy.clone())?;
        assert_eq!(saved, policy);

        let loaded = load_provider_policy(&store)?;
        assert_eq!(loaded, policy);

        let resolved = resolve_model_slot(&store, SLOT_POST_TRANSCRIPT)?.expect("slot");
        assert_eq!(resolved.model_id, "llama3.2");
        assert_eq!(resolved.source, "provider_policy");

        Ok(())
    }

    #[test]
    fn legacy_settings_resolve_to_typed_slots() -> Result<()> {
        let store = Store::open_in_memory()?;
        let mut settings = Map::new();
        settings.insert(
            "chat_provider".to_string(),
            json!({
                "kind": "openai_compatible",
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "chat-local"
            }),
        );
        settings.insert(
            "ai_provider".to_string(),
            json!({
                "kind": "openai_compatible",
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "post-local"
            }),
        );
        settings.insert(
            "embedding_provider".to_string(),
            json!({
                "kind": "openai_compatible",
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "legacy-embedding"
            }),
        );
        store.settings().upsert_many(settings)?;

        let chat = resolve_model_slot(&store, SLOT_CHAT)?.expect("chat slot");
        assert_eq!(chat.model_id, "chat-local");
        assert_eq!(chat.source, "legacy_setting");

        let post_transcript = resolve_model_slot(&store, SLOT_POST_TRANSCRIPT)?.expect("post slot");
        assert_eq!(post_transcript.model_id, "post-local");

        let memory_search = resolve_model_slot(&store, SLOT_MEMORY_SEARCH)?.expect("memory");
        assert_eq!(memory_search.provider_account, None);
        assert_eq!(memory_search.model_id, "local_wiki");

        Ok(())
    }

    #[test]
    fn unresolved_slots_return_none() -> Result<()> {
        let store = Store::open_in_memory()?;

        assert!(resolve_model_slot(&store, SLOT_PROACTIVE)?.is_none());
        assert!(resolve_model_slot(&store, SLOT_VISION)?.is_none());

        Ok(())
    }

    #[test]
    fn local_loopback_provider_does_not_require_api_key() -> Result<()> {
        let store = Store::open_in_memory()?;
        let mut settings = Map::new();
        settings.insert(
            "ai_provider".to_string(),
            json!({
                "kind": "openai_compatible",
                "base_url": "http://localhost:11434/v1",
                "model": "local-no-key"
            }),
        );
        store.settings().upsert_many(settings)?;

        let config = load_openai_config(&store)?.expect("loopback provider should resolve");
        assert_eq!(config.base_url, "http://localhost:11434/v1");
        assert_eq!(config.model, "local-no-key");
        assert_eq!(config.api_key, "");

        Ok(())
    }

    #[test]
    fn non_loopback_provider_requires_key_or_subscription_integration() {
        assert!(validate_provider_setting(&json!({
            "kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5.4-mini"
        }))
        .is_err());

        validate_provider_setting(&json!({
            "kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5.4-mini",
            "api_key": "key"
        }))
        .expect("api key should satisfy remote provider policy");

        validate_provider_setting(&json!({
            "kind": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5.4-mini",
            "subscription_integration": "chatgpt_plan"
        }))
        .expect("subscription integration should satisfy remote provider policy");
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
