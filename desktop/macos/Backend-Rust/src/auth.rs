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
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::{Mutex, RwLock};
use tokio::time::timeout;

const UNKNOWN_KID_REFRESH_COOLDOWN: Duration = Duration::from_secs(5);
const UNKNOWN_KID_REFRESH_TIMEOUT: Duration = Duration::from_secs(5);

/// Firebase public keys cache
/// Keys are fetched from Google's public key endpoint
pub struct FirebaseAuth {
    /// Cached public keys (kid -> PEM)
    keys: Arc<RwLock<HashMap<String, DecodingKey>>>,
    /// HTTP client for fetching keys
    client: Client,
    /// Firebase project ID
    project_id: String,
    /// Serializes on-demand JWK refreshes so an unknown kid burst only fetches once.
    refresh_lock: Arc<Mutex<()>>,
    /// Last on-demand refresh attempt for unknown kids. Throttles invalid-token probes.
    last_unknown_kid_refresh: Arc<RwLock<Option<Instant>>>,
    /// Whether the most recent unknown-kid refresh attempt failed.
    last_unknown_kid_refresh_failed: Arc<RwLock<bool>>,
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

/// Auth error response.
///
/// Status codes:
/// - `trial_expired` → 402 Payment Required (so clients can distinguish paywall
///   from auth failure and show the upgrade UI)
/// - any other error string → 401 Unauthorized
#[derive(Debug, Serialize)]
pub struct AuthError {
    pub error: String,
    pub message: String,
}

impl IntoResponse for AuthError {
    fn into_response(self) -> Response {
        let status = if self.error == "trial_expired" {
            StatusCode::PAYMENT_REQUIRED
        } else if self.error == "byok_validation_failed" {
            StatusCode::FORBIDDEN
        } else if self.error == "jwks_refresh_failed" {
            StatusCode::SERVICE_UNAVAILABLE
        } else if self.error == "request_deadline_exceeded" {
            StatusCode::GATEWAY_TIMEOUT
        } else {
            StatusCode::UNAUTHORIZED
        };
        (status, Json(self)).into_response()
    }
}

impl FirebaseAuth {
    /// True when the Firebase Auth emulator is active (local harness).
    pub fn auth_emulator_active() -> bool {
        std::env::var("FIREBASE_AUTH_EMULATOR_HOST")
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
    }

    /// Create a new Firebase Auth verifier
    pub fn new(project_id: String) -> Self {
        Self {
            keys: Arc::new(RwLock::new(HashMap::new())),
            client: Client::new(),
            project_id,
            refresh_lock: Arc::new(Mutex::new(())),
            last_unknown_kid_refresh: Arc::new(RwLock::new(None)),
            last_unknown_kid_refresh_failed: Arc::new(RwLock::new(false)),
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
    pub async fn verify_token(
        &self,
        token: &str,
    ) -> Result<(String, Option<String>, Option<String>), AuthError> {
        if Self::auth_emulator_active() {
            return self.verify_emulator_token(token);
        }

        // Decode header to get kid
        let header = decode_header(token).map_err(|e| AuthError {
            error: "invalid_token".to_string(),
            message: format!("Failed to decode token header: {}", e),
        })?;

        let kid = header.kid.ok_or_else(|| AuthError {
            error: "invalid_token".to_string(),
            message: "Token missing kid header".to_string(),
        })?;

        // Set up validation
        let mut validation = Validation::new(jsonwebtoken::Algorithm::RS256);
        validation.set_audience(&[&self.project_id]);
        validation.set_issuer(&[format!(
            "https://securetoken.google.com/{}",
            self.project_id
        )]);

        if let Some(result) = self
            .try_decode_with_cached_key(token, &kid, &validation)
            .await
        {
            let token_data = result?;
            return Ok((
                token_data.claims.sub,
                token_data.claims.name,
                token_data.claims.email,
            ));
        }

        tracing::warn!("Firebase token kid unknown; refreshing JWKs once");
        self.refresh_keys_for_unknown_kid().await?;

        let result = self
            .try_decode_with_cached_key(token, &kid, &validation)
            .await;
        let token_data = match result {
            Some(result) => result?,
            None => {
                return Err(AuthError {
                    error: "unknown_key_id".to_string(),
                    message: "Firebase token key id is not recognized after JWK refresh"
                        .to_string(),
                });
            }
        };

        Ok((
            token_data.claims.sub,
            token_data.claims.name,
            token_data.claims.email,
        ))
    }

    /// Verify unsigned JWTs issued by the Firebase Auth emulator (alg "none").
    fn verify_emulator_token(
        &self,
        token: &str,
    ) -> Result<(String, Option<String>, Option<String>), AuthError> {
        let alg = Self::jwt_header_alg(token).ok_or_else(|| AuthError {
            error: "invalid_token".to_string(),
            message: "Failed to decode emulator token header".to_string(),
        })?;
        if alg != "none" {
            return Err(AuthError {
                error: "invalid_token".to_string(),
                message: format!("Auth emulator expects alg=none, got {alg}"),
            });
        }

        let claims =
            Self::decode_jwt_payload::<FirebaseClaims>(token).map_err(|message| AuthError {
                error: "invalid_token".to_string(),
                message,
            })?;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_secs())
            .unwrap_or(0);

        if claims.aud != self.project_id {
            return Err(AuthError {
                error: "invalid_token".to_string(),
                message: format!(
                    "Token audience mismatch: expected {}, got {}",
                    self.project_id, claims.aud
                ),
            });
        }

        let expected_iss = format!("https://securetoken.google.com/{}", self.project_id);
        if claims.iss != expected_iss {
            return Err(AuthError {
                error: "invalid_token".to_string(),
                message: format!(
                    "Token issuer mismatch: expected {}, got {}",
                    expected_iss, claims.iss
                ),
            });
        }

        if claims.exp < now {
            return Err(AuthError {
                error: "invalid_token".to_string(),
                message: "Token expired".to_string(),
            });
        }

        if claims.sub.is_empty() {
            return Err(AuthError {
                error: "invalid_token".to_string(),
                message: "Token missing subject".to_string(),
            });
        }

        Ok((claims.sub, claims.name, claims.email))
    }

    fn jwt_header_alg(token: &str) -> Option<String> {
        let encoded = token.split('.').next()?;
        Self::decode_jwt_part_json(encoded).ok().and_then(|value| {
            value
                .get("alg")
                .and_then(|item| item.as_str())
                .map(str::to_string)
        })
    }

    fn decode_jwt_payload<T: DeserializeOwned>(token: &str) -> Result<T, String> {
        let encoded = token
            .split('.')
            .nth(1)
            .ok_or_else(|| "Emulator token missing payload".to_string())?;
        let value = Self::decode_jwt_part_json(encoded)?;
        serde_json::from_value(value)
            .map_err(|error| format!("Emulator token payload invalid: {error}"))
    }

    fn decode_jwt_part_json(encoded: &str) -> Result<serde_json::Value, String> {
        use base64::Engine;
        let bytes = base64::engine::general_purpose::URL_SAFE_NO_PAD
            .decode(encoded)
            .or_else(|_| {
                let padded = match encoded.len() % 4 {
                    0 => encoded.to_string(),
                    n => format!("{}{}", encoded, "=".repeat(4 - n)),
                };
                base64::engine::general_purpose::STANDARD.decode(padded)
            })
            .map_err(|error| format!("Emulator token base64 decode failed: {error}"))?;
        serde_json::from_slice(&bytes)
            .map_err(|error| format!("Emulator token JSON decode failed: {error}"))
    }

    async fn try_decode_with_cached_key(
        &self,
        token: &str,
        kid: &str,
        validation: &Validation,
    ) -> Option<Result<jsonwebtoken::TokenData<FirebaseClaims>, AuthError>> {
        let keys = self.keys.read().await;
        let key = keys.get(kid)?;
        Some(
            decode::<FirebaseClaims>(token, key, validation).map_err(|e| AuthError {
                error: "invalid_token".to_string(),
                message: format!("Token validation failed: {}", e),
            }),
        )
    }

    async fn refresh_keys_for_unknown_kid(&self) -> Result<(), AuthError> {
        let _guard = self.refresh_lock.lock().await;

        {
            let last = self.last_unknown_kid_refresh.read().await;
            if last
                .map(|instant| instant.elapsed() < UNKNOWN_KID_REFRESH_COOLDOWN)
                .unwrap_or(false)
            {
                tracing::warn!(
                    "Skipping Firebase JWK refresh; unknown-kid refresh was attempted recently"
                );
                if *self.last_unknown_kid_refresh_failed.read().await {
                    return Err(AuthError {
                        error: "jwks_refresh_failed".to_string(),
                        message: "Firebase signing keys refresh was attempted recently and failed"
                            .to_string(),
                    });
                }
                return Ok(());
            }
        }

        {
            let mut last = self.last_unknown_kid_refresh.write().await;
            *last = Some(Instant::now());
        }

        match timeout(UNKNOWN_KID_REFRESH_TIMEOUT, self.refresh_keys()).await {
            Ok(Ok(())) => {
                let mut failed = self.last_unknown_kid_refresh_failed.write().await;
                *failed = false;
                Ok(())
            }
            Ok(Err(e)) => {
                let mut failed = self.last_unknown_kid_refresh_failed.write().await;
                *failed = true;
                tracing::warn!("Firebase JWK refresh after unknown kid failed: {}", e);
                Err(AuthError {
                    error: "jwks_refresh_failed".to_string(),
                    message: "Firebase signing keys could not be refreshed".to_string(),
                })
            }
            Err(_) => {
                let mut failed = self.last_unknown_kid_refresh_failed.write().await;
                *failed = true;
                tracing::warn!(
                    "Firebase JWK refresh after unknown kid timed out after {:?}",
                    UNKNOWN_KID_REFRESH_TIMEOUT
                );
                Err(AuthError {
                    error: "jwks_refresh_failed".to_string(),
                    message: "Firebase signing keys refresh timed out".to_string(),
                })
            }
        }
    }
}

/// Authenticated user extractor for Axum
/// Usage: async fn handler(user: AuthUser) -> impl IntoResponse { ... }
#[derive(Debug, Clone)]
pub struct AuthUser {
    pub uid: String,
    #[allow(dead_code)] // populated from the Firebase token but not currently read
    pub name: Option<String>,
    pub email: Option<String>,
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
        let (uid, name, email) = firebase_auth.0.verify_token(token).await?;

        Ok(AuthUser { uid, name, email })
    }
}

/// Create a layer that adds Firebase auth to request extensions
pub fn firebase_auth_extension(auth: Arc<FirebaseAuth>) -> axum::Extension<FirebaseAuthExt> {
    axum::Extension(FirebaseAuthExt(auth))
}

impl From<PaywalledAuthUser> for AuthUser {
    fn from(p: PaywalledAuthUser) -> Self {
        AuthUser {
            uid: p.uid,
            name: p.name,
            email: p.email,
        }
    }
}

/// Authenticated user extractor that ALSO enforces:
/// 1. BYOK fingerprint validation (SHA-256 against Firestore enrollment)
/// 2. Desktop trial paywall (plan + BYOK + account age)
///
/// If the user is BYOK-active but sends mismatched fingerprints → HTTP 403.
/// If the user is past their trial → HTTP 402.
///
/// `byok_stripped`: true if the request carried BYOK headers that were silently
/// cleared (non-enrolled user or expired heartbeat). Route handlers should check
/// this flag and ignore BYOK headers when true.
///
/// Use this for every $-incurring route handler in the Rust backend:
/// proxy.rs (Gemini), chat_completions.rs (Anthropic), screen_activity.rs
/// (Pinecone), tts.rs, agent.rs.
#[derive(Debug, Clone)]
pub struct PaywalledAuthUser {
    pub uid: String,
    pub name: Option<String>,
    pub email: Option<String>,
    pub byok_stripped: bool,
}

/// Bound one extractor stage by the request budget when the route admitted one
/// (#9835). Routes without the deadline middleware keep today's behavior; the
/// unknown-kid refresh cooldown and cache TTLs are policy clocks and stay
/// independent — only this request's wait is bounded.
async fn within_request_deadline<T, F>(
    deadline: Option<&crate::request_deadline::RequestDeadline>,
    stage: &str,
    future: F,
) -> Result<T, AuthError>
where
    F: std::future::Future<Output = T>,
{
    match deadline {
        None => Ok(future.await),
        Some(d) => tokio::time::timeout(d.remaining(), future)
            .await
            .map_err(|_| AuthError {
                error: "request_deadline_exceeded".to_string(),
                message: format!("Request deadline budget exhausted during {stage}"),
            }),
    }
}

#[async_trait]
impl<S> FromRequestParts<S> for PaywalledAuthUser
where
    S: Send + Sync,
{
    type Rejection = AuthError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        let deadline = parts
            .extensions
            .get::<crate::request_deadline::RequestDeadline>()
            .copied();
        // Get + extract bearer token
        let auth_header = parts
            .headers
            .get("Authorization")
            .and_then(|h| h.to_str().ok())
            .ok_or_else(|| AuthError {
                error: "missing_token".to_string(),
                message: "Authorization header required".to_string(),
            })?;

        let token = auth_header
            .strip_prefix("Bearer ")
            .ok_or_else(|| AuthError {
                error: "invalid_token".to_string(),
                message: "Invalid Authorization header format".to_string(),
            })?;

        // Verify Firebase token (same flow AuthUser uses)
        let firebase_auth = parts
            .extensions
            .get::<FirebaseAuthExt>()
            .ok_or_else(|| AuthError {
                error: "server_error".to_string(),
                message: "Firebase auth not configured".to_string(),
            })?;

        let (uid, name, email) = within_request_deadline(
            deadline.as_ref(),
            "token verification",
            firebase_auth.0.verify_token(token),
        )
        .await??;

        // BYOK fingerprint validation (issue #7357).
        // Validates SHA-256 fingerprints against Firestore enrollment.
        // Non-BYOK users who send BYOK headers get them silently cleared.
        let mut byok_stripped = false;
        if let Some(byok_ext) = parts.extensions.get::<crate::byok::ByokCacheExt>() {
            // Get the Firestore service from the paywall checker (shares the same Arc)
            if let Some(checker) = parts.extensions.get::<crate::paywall::PaywallCheckerExt>() {
                let byok_state = within_request_deadline(
                    deadline.as_ref(),
                    "BYOK state fetch",
                    byok_ext.0.get_or_fetch(&uid, &checker.0.firestore),
                )
                .await?;

                match crate::byok::validate_byok_request(&uid, &parts.headers, &byok_state) {
                    Ok(crate::byok::ByokValidation::Active) => {
                        // BYOK keys validated, proceed with user's keys
                    }
                    Ok(crate::byok::ByokValidation::Inactive { clear_headers }) => {
                        byok_stripped = clear_headers;
                    }
                    Err(error_msg) => {
                        tracing::warn!("BYOK validation failed for uid={}: {}", uid, error_msg);
                        return Err(AuthError {
                            error: "byok_validation_failed".to_string(),
                            message: error_msg,
                        });
                    }
                }
            }
        }

        // Paywall check — fail open if Firestore is unreachable so a backend
        // outage never makes paying users look paywalled. Budget exhaustion is
        // different from an outage: the typed timeout is returned instead of
        // spending provider budget on a request that can no longer finish.
        if let Some(checker) = parts.extensions.get::<crate::paywall::PaywallCheckerExt>() {
            if within_request_deadline(
                deadline.as_ref(),
                "paywall check",
                checker.0.is_paywalled(&uid, &parts.headers, byok_stripped),
            )
            .await?
            {
                return Err(AuthError {
                    error: "trial_expired".to_string(),
                    message: "Desktop trial expired. Upgrade or bring your own keys.".to_string(),
                });
            }
        } else {
            tracing::warn!(
                "PaywalledAuthUser: PaywallChecker extension missing, failing open for uid={}",
                uid
            );
        }

        Ok(PaywalledAuthUser {
            uid,
            name,
            email,
            byok_stripped,
        })
    }
}

/// Layer that adds the paywall checker to request extensions.
pub fn paywall_checker_extension(
    checker: Arc<crate::paywall::PaywallChecker>,
) -> axum::Extension<crate::paywall::PaywallCheckerExt> {
    axum::Extension(crate::paywall::PaywallCheckerExt(checker))
}

/// Layer that adds the BYOK state cache to request extensions.
pub fn byok_cache_extension(
    cache: Arc<crate::byok::ByokStateCache>,
) -> axum::Extension<crate::byok::ByokCacheExt> {
    axum::Extension(crate::byok::ByokCacheExt(cache))
}
