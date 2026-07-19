use async_trait::async_trait;
use rx4::provider::{OpenAIProvider, ProviderError, StreamResult};
use rx4::{Message, Provider};
use std::sync::Arc;
use thiserror::Error;

const PROVIDER_ID: &str = "omi-managed";
const PROVIDER_NAME: &str = "Omi";
const TRANSPORT_FAILURE: &str = "Omi managed transport request failed";

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ManagedTransport {
    base_url: String,
    bearer_token: String,
}

impl ManagedTransport {
    pub fn new(
        base_url: impl Into<String>,
        bearer_token: impl Into<String>,
    ) -> Result<Self, ConfigError> {
        let base_url = base_url.into();
        let bearer_token = bearer_token.into();
        if base_url.trim().is_empty() {
            return Err(ConfigError::MissingBaseUrl);
        }
        if bearer_token.trim().is_empty() {
            return Err(ConfigError::MissingBearerToken);
        }
        Ok(Self {
            base_url: base_url.trim_end_matches('/').to_owned(),
            bearer_token,
        })
    }

    pub fn provider(&self) -> ManagedProvider {
        ManagedProvider::from_provider(Arc::new(OpenAIProvider::with_base_url(
            &self.base_url,
            &self.bearer_token,
            PROVIDER_ID,
            PROVIDER_NAME,
        )))
    }
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ConfigError {
    #[error("Omi managed transport base URL is required")]
    MissingBaseUrl,
    #[error("Omi managed transport bearer token is required")]
    MissingBearerToken,
}

pub struct ManagedProvider {
    inner: Arc<dyn Provider>,
}

impl ManagedProvider {
    fn from_provider(inner: Arc<dyn Provider>) -> Self {
        Self { inner }
    }
}

#[async_trait]
impl Provider for ManagedProvider {
    fn id(&self) -> &str {
        PROVIDER_ID
    }

    fn name(&self) -> &str {
        PROVIDER_NAME
    }

    async fn stream(
        &self,
        messages: &[Message],
        system: &Option<String>,
        model: &str,
        tools: &[serde_json::Value],
    ) -> Result<StreamResult, ProviderError> {
        self.inner
            .stream(messages, system, model, tools)
            .await
            .map_err(|_| ProviderError::Api(TRANSPORT_FAILURE.into()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use futures::executor::block_on;

    struct FailingProvider;

    #[async_trait]
    impl Provider for FailingProvider {
        fn id(&self) -> &str {
            "test"
        }

        fn name(&self) -> &str {
            "test"
        }

        async fn stream(
            &self,
            _: &[Message],
            _: &Option<String>,
            _: &str,
            _: &[serde_json::Value],
        ) -> Result<StreamResult, ProviderError> {
            Err(ProviderError::Http("internal transport detail".into()))
        }
    }

    #[test]
    fn managed_transport_requires_routing_and_auth() {
        assert_eq!(
            ManagedTransport::new("", "token").expect_err("empty endpoint must fail"),
            ConfigError::MissingBaseUrl
        );
        assert_eq!(
            ManagedTransport::new("https://api.omi.me/v2", "").expect_err("empty token must fail"),
            ConfigError::MissingBearerToken
        );
    }

    #[test]
    fn provider_uses_omi_identity() {
        let transport = ManagedTransport::new("https://api.omi.me/v2/", "token")
            .expect("configured transport must construct");
        let provider = transport.provider();
        assert_eq!(provider.id(), PROVIDER_ID);
        assert_eq!(provider.name(), PROVIDER_NAME);
    }

    #[test]
    fn provider_hides_transport_errors_and_disables_rx4_retries() {
        let provider = ManagedProvider::from_provider(Arc::new(FailingProvider));
        let result = block_on(provider.stream(&[], &None, "model", &[]));
        let Err(error) = result else {
            panic!("inner failure must surface as a managed failure");
        };
        assert_eq!(error.to_string(), format!("api error: {TRANSPORT_FAILURE}"));
        assert!(!error.is_transient());
    }
}
