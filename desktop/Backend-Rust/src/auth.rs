// Firebase Authentication - Token verification
// Port from Python backend (main.py: get_current_user_uid)

use axum::{
    async_trait,
    extract::FromRequestParts,
    http::{request::Parts, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use jsonwebtoken::{decode, decode_header, DecodingKey, Validation};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Firebase public keys cache
/// Keys are fetched from Google's public key endpoint
pub struct FirebaseAuth {
    /// Cached public keys (kid -> PEM)
    keys: Arc<RwLock<HashMap<String, DecodingKey>>>,
    /// HTTP client for fetching keys
    client: Client,
    /// Firebase project ID
    project_id: String,
}

/// JWT Claims from Firebase ID token
/// Note: aud, iss, exp, iat are validated by jsonwebtoken library internally.
/// email, email_verified, name are kept for potential future use.
#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub struct FirebaseClaims {
    /// Subject (user ID)
    pub sub: String,
    /// Audience (project ID)
    pub aud: String,
    /// Issuer
    pub iss: String,
    /// Issued at
    pub iat: u64,
    /// Expiration
    pub exp: u64,
    /// Email (optional)
    pub email: Option<String>,
    /// Email verified
    pub email_verified: Option<bool>,
    /// Name (optional)
    pub name: Option<String>,
}

/// Google's public key response
#[derive(Debug, Deserialize)]
struct GoogleKeys {
    keys: Vec<JwkKey>,
}

#[derive(Debug, Deserialize)]
struct JwkKey {
    kid: String,
    n: String,
    e: String,
    kty: String,
    #[allow(dead_code)]
    alg: Option<String>,
}

/// Auth error response
#[derive(Debug, Serialize)]
pub struct AuthError {
    pub error: String,
    pub message: String,
}

impl IntoResponse for AuthError {
    fn into_response(self) -> Response {
        (StatusCode::UNAUTHORIZED, Json(self)).into_response()
    }
}

impl FirebaseAuth {
    /// Create a new Firebase Auth verifier
    pub fn new(project_id: String) -> Self {
        Self {
            keys: Arc::new(RwLock::new(HashMap::new())),
            client: Client::new(),
            project_id,
        }
    }

    /// Fetch public keys from Google
    /// URL: https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com
    /// Or JWK: https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com
    pub async fn refresh_keys(&self) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com";

        let response: GoogleKeys = self.client.get(url).send().await?.json().await?;

        let mut keys = self.keys.write().await;
        keys.clear();

        for key in response.keys {
            if key.kty == "RSA" {
                if let Ok(decoding_key) = DecodingKey::from_rsa_components(&key.n, &key.e) {
                    keys.insert(key.kid, decoding_key);
                }
            }
        }

        tracing::info!("Refreshed {} Firebase public keys", keys.len());
        Ok(())
    }

    /// Verify a Firebase ID token and extract the user ID and name
    pub async fn verify_token(&self, token: &str) -> Result<(String, Option<String>), AuthError> {
        // Decode header to get kid
        let header = decode_header(token).map_err(|e| AuthError {
            error: "invalid_token".to_string(),
            message: format!("Failed to decode token header: {}", e),
        })?;

        let kid = header.kid.ok_or_else(|| AuthError {
            error: "invalid_token".to_string(),
            message: "Token missing kid header".to_string(),
        })?;

        // Get the key for this kid
        let keys = self.keys.read().await;
        let key = keys.get(&kid).ok_or_else(|| AuthError {
            error: "invalid_token".to_string(),
            message: format!("Unknown key id: {}", kid),
        })?;

        // Set up validation
        let mut validation = Validation::new(jsonwebtoken::Algorithm::RS256);
        validation.set_audience(&[&self.project_id]);
        validation.set_issuer(&[format!(
            "https://securetoken.google.com/{}",
            self.project_id
        )]);

        // Decode and validate token
        let token_data = decode::<FirebaseClaims>(token, key, &validation).map_err(|e| {
            AuthError {
                error: "invalid_token".to_string(),
                message: format!("Token validation failed: {}", e),
            }
        })?;

        Ok((token_data.claims.sub, token_data.claims.name))
    }
}

/// Authenticated user extractor for Axum
/// Usage: async fn handler(user: AuthUser) -> impl IntoResponse { ... }
#[derive(Debug, Clone)]
pub struct AuthUser {
    pub uid: String,
    pub name: Option<String>,
}

/// Extension to store Firebase auth in request
#[derive(Clone)]
pub struct FirebaseAuthExt(pub Arc<FirebaseAuth>);

#[async_trait]
impl<S> FromRequestParts<S> for AuthUser
where
    S: Send + Sync,
{
    type Rejection = AuthError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        // Get Authorization header
        let auth_header = parts
            .headers
            .get("Authorization")
            .and_then(|h| h.to_str().ok())
            .ok_or_else(|| AuthError {
                error: "missing_token".to_string(),
                message: "Authorization header required".to_string(),
            })?;

        // Extract bearer token
        let token = auth_header
            .strip_prefix("Bearer ")
            .ok_or_else(|| AuthError {
                error: "invalid_token".to_string(),
                message: "Invalid Authorization header format".to_string(),
            })?;

        // Get Firebase auth from extensions (set by middleware)
        let firebase_auth = parts
            .extensions
            .get::<FirebaseAuthExt>()
            .ok_or_else(|| AuthError {
                error: "server_error".to_string(),
                message: "Firebase auth not configured".to_string(),
            })?;

        // Verify token
        let (uid, name) = firebase_auth.0.verify_token(token).await?;

        Ok(AuthUser { uid, name })
    }
}

/// Create a layer that adds Firebase auth to request extensions
pub fn firebase_auth_extension(auth: Arc<FirebaseAuth>) -> axum::Extension<FirebaseAuthExt> {
    axum::Extension(FirebaseAuthExt(auth))
}
