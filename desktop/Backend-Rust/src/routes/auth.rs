// OAuth Authentication Routes
// Port from Python backend (main.py)

use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::{Html, IntoResponse, Redirect, Response},
    routing::{get, post},
    Form, Json, Router,
};
use chrono::Utc;
use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

use crate::config::Config;

/// In-memory session storage for OAuth state
#[derive(Clone)]
pub struct AuthSessionStore {
    sessions: Arc<RwLock<HashMap<String, AuthSession>>>,
    codes: Arc<RwLock<HashMap<String, AuthCode>>>,
}

#[derive(Clone)]
struct AuthSession {
    data: AuthSessionData,
    expires: i64,
}

#[derive(Clone, Serialize, Deserialize)]
struct AuthSessionData {
    provider: String,
    redirect_uri: String,
    state: Option<String>,
}

#[derive(Clone)]
struct AuthCode {
    data: String,
    expires: i64,
}

impl Default for AuthSessionStore {
    fn default() -> Self {
        Self::new()
    }
}

impl AuthSessionStore {
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
            codes: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    async fn set_session(&self, session_id: &str, data: AuthSessionData, ttl_secs: i64) {
        let expires = Utc::now().timestamp() + ttl_secs;
        let mut sessions = self.sessions.write().await;
        sessions.insert(session_id.to_string(), AuthSession { data, expires });
    }

    async fn get_session(&self, session_id: &str) -> Option<AuthSessionData> {
        let sessions = self.sessions.read().await;
        sessions.get(session_id).and_then(|s| {
            if s.expires > Utc::now().timestamp() {
                Some(s.data.clone())
            } else {
                None
            }
        })
    }

    async fn set_code(&self, code: &str, data: String, ttl_secs: i64) {
        let expires = Utc::now().timestamp() + ttl_secs;
        let mut codes = self.codes.write().await;
        codes.insert(code.to_string(), AuthCode { data, expires });
    }

    async fn get_code(&self, code: &str) -> Option<String> {
        let codes = self.codes.read().await;
        codes.get(code).and_then(|c| {
            if c.expires > Utc::now().timestamp() {
                Some(c.data.clone())
            } else {
                None
            }
        })
    }

    async fn delete_code(&self, code: &str) {
        let mut codes = self.codes.write().await;
        codes.remove(code);
    }
}

/// Auth state shared across handlers
#[derive(Clone)]
pub struct AuthState {
    pub config: Arc<Config>,
    pub sessions: AuthSessionStore,
    pub http_client: Client,
}

// Request/Response types
#[derive(Debug, Deserialize)]
pub struct AuthorizeQuery {
    provider: String,
    redirect_uri: String,
    state: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct AppleCallbackForm {
    code: String,
    state: String,
    error: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct GoogleCallbackQuery {
    code: Option<String>,
    state: Option<String>,
    error: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct TokenRequest {
    grant_type: String,
    code: String,
    /// OAuth redirect_uri - validated against the original authorization request
    redirect_uri: String,
    #[serde(default)]
    use_custom_token: bool,
}

#[derive(Debug, Serialize)]
pub struct TokenResponse {
    provider: String,
    id_token: String,
    access_token: Option<String>,
    provider_id: String,
    token_type: String,
    expires_in: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    custom_token: Option<String>,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
    message: String,
}

impl IntoResponse for ErrorResponse {
    fn into_response(self) -> Response {
        (StatusCode::BAD_REQUEST, Json(self)).into_response()
    }
}

// OAuth credential data stored in auth codes
#[derive(Debug, Serialize, Deserialize)]
struct OAuthCredentials {
    provider: String,
    id_token: String,
    access_token: Option<String>,
    provider_id: String,
    /// Original redirect_uri from authorization request (for validation)
    redirect_uri: String,
}

// Apple JWT claims for client secret
#[derive(Debug, Serialize)]
struct AppleClientSecretClaims {
    iss: String,
    iat: i64,
    exp: i64,
    aud: String,
    sub: String,
}

/// Apple domain verification endpoint
async fn apple_domain_association() -> impl IntoResponse {
    // Return empty content for domain verification
    // Update this with actual content from Apple Developer Portal if needed
    ""
}

/// Start OAuth flow
async fn auth_authorize(
    State(state): State<AuthState>,
    Query(params): Query<AuthorizeQuery>,
) -> Result<Redirect, ErrorResponse> {
    if params.provider != "google" && params.provider != "apple" {
        return Err(ErrorResponse {
            error: "invalid_provider".to_string(),
            message: "Unsupported provider. Use 'google' or 'apple'.".to_string(),
        });
    }

    let session_id = uuid::Uuid::new_v4().to_string();
    let session_data = AuthSessionData {
        provider: params.provider.clone(),
        redirect_uri: params.redirect_uri,
        state: params.state,
    };
    state.sessions.set_session(&session_id, session_data, 300).await;

    match params.provider.as_str() {
        "apple" => apple_auth_redirect(&state.config, &session_id),
        "google" => google_auth_redirect(&state.config, &session_id),
        _ => Err(ErrorResponse {
            error: "invalid_provider".to_string(),
            message: "Unsupported provider".to_string(),
        }),
    }
}

fn apple_auth_redirect(config: &Config, session_id: &str) -> Result<Redirect, ErrorResponse> {
    let client_id = config.apple_client_id.as_ref().ok_or_else(|| ErrorResponse {
        error: "not_configured".to_string(),
        message: "APPLE_CLIENT_ID not configured".to_string(),
    })?;

    let api_base_url = config.base_api_url.as_deref().unwrap_or("http://localhost:8080");
    let callback_url = format!("{}/v1/auth/callback/apple", api_base_url);

    let auth_url = format!(
        "https://appleid.apple.com/auth/authorize?\
        client_id={}&\
        redirect_uri={}&\
        response_type=code&\
        scope=name%20email&\
        response_mode=form_post&\
        state={}",
        client_id, callback_url, session_id
    );

    Ok(Redirect::to(&auth_url))
}

fn google_auth_redirect(config: &Config, session_id: &str) -> Result<Redirect, ErrorResponse> {
    let client_id = config.google_client_id.as_ref().ok_or_else(|| ErrorResponse {
        error: "not_configured".to_string(),
        message: "GOOGLE_CLIENT_ID not configured".to_string(),
    })?;

    let api_base_url = config.base_api_url.as_deref().unwrap_or("http://localhost:8080");
    let callback_url_raw = format!("{}/v1/auth/callback/google", api_base_url);
    let callback_url = urlencoding::encode(&callback_url_raw);
    let scope = urlencoding::encode("openid email profile");

    let auth_url = format!(
        "https://accounts.google.com/o/oauth2/v2/auth?\
        client_id={}&\
        redirect_uri={}&\
        response_type=code&\
        scope={}&\
        state={}",
        client_id, callback_url, scope, session_id
    );

    Ok(Redirect::to(&auth_url))
}

/// Apple OAuth callback (POST - form_post mode)
async fn auth_callback_apple(
    State(state): State<AuthState>,
    Form(form): Form<AppleCallbackForm>,
) -> Result<Html<String>, ErrorResponse> {
    if let Some(error) = form.error {
        return Err(ErrorResponse {
            error: "auth_error".to_string(),
            message: format!("Auth error: {}", error),
        });
    }

    let session_data = state.sessions.get_session(&form.state).await.ok_or_else(|| ErrorResponse {
        error: "invalid_session".to_string(),
        message: "Invalid or expired auth session".to_string(),
    })?;

    // Exchange Apple code for tokens
    let oauth_credentials = exchange_apple_code(&state, &form.code, &session_data).await?;

    // Create temporary auth code
    let auth_code = uuid::Uuid::new_v4().to_string();
    state.sessions.set_code(&auth_code, oauth_credentials, 300).await;

    // Return HTML that redirects to app
    let html = render_auth_callback(
        &auth_code,
        session_data.state.as_deref().unwrap_or(""),
        &session_data.redirect_uri,
        None,
    );

    Ok(Html(html))
}

/// Google OAuth callback (GET - redirect mode)
async fn auth_callback_google(
    State(state): State<AuthState>,
    Query(query): Query<GoogleCallbackQuery>,
) -> Result<Html<String>, ErrorResponse> {
    if let Some(error) = query.error {
        return Err(ErrorResponse {
            error: "auth_error".to_string(),
            message: format!("Auth error: {}", error),
        });
    }

    let code = query.code.ok_or_else(|| ErrorResponse {
        error: "missing_code".to_string(),
        message: "Missing code parameter".to_string(),
    })?;

    let session_id = query.state.ok_or_else(|| ErrorResponse {
        error: "missing_state".to_string(),
        message: "Missing state parameter".to_string(),
    })?;

    let session_data = state.sessions.get_session(&session_id).await.ok_or_else(|| ErrorResponse {
        error: "invalid_session".to_string(),
        message: "Invalid or expired auth session".to_string(),
    })?;

    // Exchange Google code for tokens
    let oauth_credentials = exchange_google_code(&state, &code, &session_data).await?;

    // Create temporary auth code
    let auth_code = uuid::Uuid::new_v4().to_string();
    state.sessions.set_code(&auth_code, oauth_credentials, 300).await;

    // Return HTML that redirects to app
    let html = render_auth_callback(
        &auth_code,
        session_data.state.as_deref().unwrap_or(""),
        &session_data.redirect_uri,
        None,
    );

    Ok(Html(html))
}

/// Exchange auth code for tokens
async fn auth_token(
    State(state): State<AuthState>,
    Form(form): Form<TokenRequest>,
) -> Result<Json<TokenResponse>, ErrorResponse> {
    if form.grant_type != "authorization_code" {
        return Err(ErrorResponse {
            error: "unsupported_grant".to_string(),
            message: "Unsupported grant type".to_string(),
        });
    }

    let oauth_credentials_json = state.sessions.get_code(&form.code).await.ok_or_else(|| ErrorResponse {
        error: "invalid_code".to_string(),
        message: "Invalid or expired code".to_string(),
    })?;

    state.sessions.delete_code(&form.code).await;

    let credentials: OAuthCredentials = serde_json::from_str(&oauth_credentials_json)
        .map_err(|e| ErrorResponse {
            error: "parse_error".to_string(),
            message: format!("Failed to parse credentials: {}", e),
        })?;

    // Validate redirect_uri matches the one from authorization
    if form.redirect_uri != credentials.redirect_uri {
        return Err(ErrorResponse {
            error: "invalid_redirect_uri".to_string(),
            message: "redirect_uri does not match the original authorization request".to_string(),
        });
    }

    let provider_id = credentials.provider_id.clone();
    let mut response = TokenResponse {
        provider: credentials.provider.clone(),
        id_token: credentials.id_token.clone(),
        access_token: credentials.access_token.clone(),
        provider_id,
        token_type: "Bearer".to_string(),
        expires_in: 3600,
        custom_token: None,
    };

    if form.use_custom_token {
        match generate_custom_token(&state, &credentials).await {
            Ok(token) => response.custom_token = Some(token),
            Err(e) => tracing::warn!("Failed to generate custom token: {}", e),
        }
    }

    Ok(Json(response))
}

async fn exchange_apple_code(
    state: &AuthState,
    code: &str,
    session_data: &AuthSessionData,
) -> Result<String, ErrorResponse> {
    let config = &state.config;

    let client_id = config.apple_client_id.as_ref().ok_or_else(|| ErrorResponse {
        error: "not_configured".to_string(),
        message: "Apple auth not configured".to_string(),
    })?;

    let team_id = config.apple_team_id.as_ref().ok_or_else(|| ErrorResponse {
        error: "not_configured".to_string(),
        message: "APPLE_TEAM_ID not configured".to_string(),
    })?;

    let key_id = config.apple_key_id.as_ref().ok_or_else(|| ErrorResponse {
        error: "not_configured".to_string(),
        message: "APPLE_KEY_ID not configured".to_string(),
    })?;

    let private_key = config.apple_private_key.as_ref().ok_or_else(|| ErrorResponse {
        error: "not_configured".to_string(),
        message: "APPLE_PRIVATE_KEY not configured".to_string(),
    })?;

    let api_base_url = config.base_api_url.as_deref().unwrap_or("http://localhost:8080");
    let callback_url = format!("{}/v1/auth/callback/apple", api_base_url);

    // Generate client secret JWT
    let client_secret = generate_apple_client_secret(client_id, team_id, key_id, private_key)?;

    // Exchange code for tokens
    let response = state
        .http_client
        .post("https://appleid.apple.com/auth/token")
        .form(&[
            ("client_id", client_id.as_str()),
            ("client_secret", &client_secret),
            ("code", code),
            ("grant_type", "authorization_code"),
            ("redirect_uri", &callback_url),
        ])
        .send()
        .await
        .map_err(|e| ErrorResponse {
            error: "request_failed".to_string(),
            message: format!("Apple token request failed: {}", e),
        })?;

    if !response.status().is_success() {
        let error_text = response.text().await.unwrap_or_default();
        tracing::error!("Apple token exchange failed: {}", error_text);
        return Err(ErrorResponse {
            error: "token_exchange_failed".to_string(),
            message: "Failed to exchange Apple code".to_string(),
        });
    }

    #[derive(Deserialize)]
    struct AppleTokenResponse {
        id_token: String,
        access_token: Option<String>,
    }

    let token_response: AppleTokenResponse = response.json().await.map_err(|e| ErrorResponse {
        error: "parse_error".to_string(),
        message: format!("Failed to parse Apple response: {}", e),
    })?;

    let credentials = OAuthCredentials {
        provider: "apple".to_string(),
        id_token: token_response.id_token,
        access_token: token_response.access_token,
        provider_id: "apple.com".to_string(),
        redirect_uri: session_data.redirect_uri.clone(),
    };

    serde_json::to_string(&credentials).map_err(|e| ErrorResponse {
        error: "serialize_error".to_string(),
        message: format!("Failed to serialize credentials: {}", e),
    })
}

async fn exchange_google_code(
    state: &AuthState,
    code: &str,
    session_data: &AuthSessionData,
) -> Result<String, ErrorResponse> {
    let config = &state.config;

    let client_id = config.google_client_id.as_ref().ok_or_else(|| ErrorResponse {
        error: "not_configured".to_string(),
        message: "Google auth not configured".to_string(),
    })?;

    let client_secret = config.google_client_secret.as_ref().ok_or_else(|| ErrorResponse {
        error: "not_configured".to_string(),
        message: "GOOGLE_CLIENT_SECRET not configured".to_string(),
    })?;

    let api_base_url = config.base_api_url.as_deref().unwrap_or("http://localhost:8080");
    let callback_url = format!("{}/v1/auth/callback/google", api_base_url);

    // Exchange code for tokens
    let response = state
        .http_client
        .post("https://oauth2.googleapis.com/token")
        .form(&[
            ("code", code),
            ("client_id", client_id.as_str()),
            ("client_secret", client_secret.as_str()),
            ("redirect_uri", &callback_url),
            ("grant_type", "authorization_code"),
        ])
        .send()
        .await
        .map_err(|e| ErrorResponse {
            error: "request_failed".to_string(),
            message: format!("Google token request failed: {}", e),
        })?;

    if !response.status().is_success() {
        let error_text = response.text().await.unwrap_or_default();
        tracing::error!("Google token exchange failed: {}", error_text);
        return Err(ErrorResponse {
            error: "token_exchange_failed".to_string(),
            message: "Failed to exchange Google code".to_string(),
        });
    }

    #[derive(Deserialize)]
    struct GoogleTokenResponse {
        id_token: String,
        access_token: Option<String>,
    }

    let token_response: GoogleTokenResponse = response.json().await.map_err(|e| ErrorResponse {
        error: "parse_error".to_string(),
        message: format!("Failed to parse Google response: {}", e),
    })?;

    let credentials = OAuthCredentials {
        provider: "google".to_string(),
        id_token: token_response.id_token,
        access_token: token_response.access_token,
        provider_id: "google.com".to_string(),
        redirect_uri: session_data.redirect_uri.clone(),
    };

    serde_json::to_string(&credentials).map_err(|e| ErrorResponse {
        error: "serialize_error".to_string(),
        message: format!("Failed to serialize credentials: {}", e),
    })
}

fn generate_apple_client_secret(
    client_id: &str,
    team_id: &str,
    key_id: &str,
    private_key: &str,
) -> Result<String, ErrorResponse> {
    let now = Utc::now().timestamp();
    let claims = AppleClientSecretClaims {
        iss: team_id.to_string(),
        iat: now,
        exp: now + 3600,
        aud: "https://appleid.apple.com".to_string(),
        sub: client_id.to_string(),
    };

    let mut header = Header::new(Algorithm::ES256);
    header.kid = Some(key_id.to_string());

    let key = EncodingKey::from_ec_pem(private_key.as_bytes()).map_err(|e| ErrorResponse {
        error: "key_error".to_string(),
        message: format!("Failed to parse Apple private key: {}", e),
    })?;

    encode(&header, &claims, &key).map_err(|e| ErrorResponse {
        error: "jwt_error".to_string(),
        message: format!("Failed to generate Apple client secret: {}", e),
    })
}

async fn generate_custom_token(
    state: &AuthState,
    credentials: &OAuthCredentials,
) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let firebase_api_key = state.config.firebase_api_key.as_ref()
        .ok_or("FIREBASE_API_KEY not configured")?;

    // Sign in with OAuth credential using Firebase Auth REST API
    let sign_in_url = format!(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={}",
        firebase_api_key
    );

    let provider_id = match credentials.provider.as_str() {
        "google" => "google.com",
        "apple" => "apple.com",
        _ => return Err(format!("Unsupported provider: {}", credentials.provider).into()),
    };

    let mut post_body = format!("id_token={}&providerId={}", credentials.id_token, provider_id);
    if let Some(access_token) = &credentials.access_token {
        post_body.push_str(&format!("&access_token={}", access_token));
    }

    #[derive(Serialize)]
    struct SignInRequest {
        #[serde(rename = "postBody")]
        post_body: String,
        #[serde(rename = "requestUri")]
        request_uri: String,
        #[serde(rename = "returnIdpCredential")]
        return_idp_credential: bool,
        #[serde(rename = "returnSecureToken")]
        return_secure_token: bool,
    }

    let response = state
        .http_client
        .post(&sign_in_url)
        .json(&SignInRequest {
            post_body,
            request_uri: "http://localhost".to_string(),
            return_idp_credential: true,
            return_secure_token: true,
        })
        .send()
        .await?;

    if !response.status().is_success() {
        let error = response.text().await?;
        tracing::error!("Firebase sign-in failed: {}", error);
        return Err("Firebase sign-in failed".into());
    }

    #[derive(Deserialize)]
    struct SignInResponse {
        #[serde(rename = "localId")]
        local_id: String,
    }

    let result: SignInResponse = response.json().await?;
    let firebase_uid = result.local_id;

    tracing::info!("Firebase sign-in successful, UID: {}", firebase_uid);

    // For custom token generation, we need Firebase Admin SDK
    // In Rust, we'd need to use the service account to create a custom token
    // For now, return an error indicating this needs server-side implementation
    // The Python version uses firebase_admin.auth.create_custom_token()

    // TODO: Implement custom token generation using service account
    // This requires signing a JWT with the service account private key
    Err("Custom token generation requires Firebase Admin SDK - not yet implemented in Rust".into())
}

fn render_auth_callback(code: &str, state: &str, redirect_uri: &str, error: Option<&str>) -> String {
    // Load template and replace placeholders
    let template = include_str!("../../templates/auth_callback.html");

    template
        .replace("{{ code }}", code)
        .replace("{{ state }}", state)
        .replace("{{ redirect_uri }}", redirect_uri)
        .replace("{{ error if error is defined else '' }}", error.unwrap_or(""))
}

/// Create auth routes
pub fn auth_routes(config: Arc<Config>) -> Router {
    let auth_state = AuthState {
        config,
        sessions: AuthSessionStore::new(),
        http_client: Client::new(),
    };

    Router::new()
        .route("/.well-known/apple-developer-domain-association.txt", get(apple_domain_association))
        .route("/v1/auth/authorize", get(auth_authorize))
        .route("/v1/auth/callback/apple", post(auth_callback_apple))
        .route("/v1/auth/callback/google", get(auth_callback_google))
        .route("/v1/auth/token", post(auth_token))
        .with_state(auth_state)
}
