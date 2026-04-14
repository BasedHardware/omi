use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use serde::{Deserialize, Serialize};
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_store::StoreExt;
use tokio::sync::oneshot;

const STORE_PATH: &str = "auth.json";
const API_BASE: &str = "https://nooto-desktop-auth-1060764816205.us-central1.run.app";
const REDIRECT_URI: &str = "nooto://auth/callback";
const FIREBASE_API_KEY: &str = "AIzaSyAPDdy9ZUCMQOPvcbjkB-dQn6WPcPY5nng";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthResult {
    pub user_id: String,
    pub email: String,
    pub id_token: String,
}

/// Decoded JWT payload (only the fields we need).
#[derive(Debug, Deserialize)]
struct JwtClaims {
    #[serde(default)]
    sub: String,
    #[serde(default)]
    email: String,
    #[serde(default)]
    user_id: String,
}

/// Token exchange response from the backend.
#[derive(Debug, Deserialize)]
struct TokenResponse {
    /// Provider's ID token (Google/Apple) — NOT a Firebase ID token.
    #[serde(default)]
    id_token: String,
    /// OAuth provider name ("google" or "apple").
    #[serde(default)]
    provider: String,
    /// Provider's access token.
    #[serde(default)]
    access_token: Option<String>,
}

/// Response from Firebase `signInWithIdp` REST API.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct FirebaseSignInResponse {
    id_token: String,
    #[serde(default)]
    local_id: String,
    #[serde(default)]
    refresh_token: String,
    #[serde(default)]
    email: String,
}

/// Sign in to Firebase using a provider's ID token (Google/Apple) via
/// the `signInWithIdp` REST API.  Returns a Firebase ID token.
async fn firebase_sign_in_with_provider(
    client: &reqwest::Client,
    provider: &str,
    provider_id_token: &str,
    provider_access_token: Option<&str>,
) -> Result<FirebaseSignInResponse, String> {
    let url = format!(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={}",
        FIREBASE_API_KEY,
    );

    let provider_id = match provider {
        "google" => "google.com",
        "apple" => "apple.com",
        _ => return Err(format!("Unsupported provider: {}", provider)),
    };

    let mut post_body = format!("id_token={}&providerId={}", provider_id_token, provider_id);
    if let Some(at) = provider_access_token {
        post_body.push_str(&format!("&access_token={}", at));
    }

    let resp = client
        .post(&url)
        .json(&serde_json::json!({
            "postBody": post_body,
            "requestUri": "http://localhost",
            "returnIdpCredential": true,
            "returnSecureToken": true,
        }))
        .send()
        .await
        .map_err(|e| format!("Firebase signInWithIdp failed: {}", e))?;

    if !resp.status().is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("Firebase signInWithIdp failed: {}", body));
    }

    resp.json::<FirebaseSignInResponse>()
        .await
        .map_err(|e| format!("Failed to parse Firebase response: {}", e))
}

/// Decode the payload of a JWT without verifying the signature.
fn decode_jwt_payload(token: &str) -> Result<JwtClaims, String> {
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() != 3 {
        return Err("Invalid JWT: expected 3 parts".into());
    }
    // base64url may not be padded — add padding
    let b64 = parts[1].replace('-', "+").replace('_', "/");
    let padded = match b64.len() % 4 {
        2 => format!("{}==", b64),
        3 => format!("{}=", b64),
        _ => b64,
    };
    let payload = BASE64
        .decode(&padded)
        .map_err(|e| format!("Failed to decode JWT payload: {}", e))?;
    serde_json::from_slice::<JwtClaims>(&payload)
        .map_err(|e| format!("Failed to parse JWT claims: {}", e))
}

/// Global channel for the deep-link callback to deliver the auth code to
/// the `sign_in` command that is waiting for it.
static AUTH_TX: std::sync::Mutex<Option<oneshot::Sender<(String, String)>>> =
    std::sync::Mutex::new(None);

/// Called from the deep-link handler in `main.rs` when a `omi://auth/callback`
/// URL arrives.  Extracts `code` and `state` and delivers them.
pub fn deliver_auth_callback(url: &url::Url) {
    let params: std::collections::HashMap<String, String> =
        url.query_pairs().map(|(k, v)| (k.to_string(), v.to_string())).collect();

    let code = params.get("code").cloned().unwrap_or_default();
    let state = params.get("state").cloned().unwrap_or_default();

    tracing::info!("Deep-link auth callback received (code present: {})", !code.is_empty());

    if let Some(tx) = AUTH_TX.lock().unwrap().take() {
        let _ = tx.send((code, state));
    } else {
        tracing::warn!("Auth callback received but no sign-in is waiting for it");
    }
}

/// Initiate sign-in flow.
///
/// 1. Opens `{API}/v1/auth/authorize?provider=...&redirect_uri=omi://auth/callback`
///    in the system browser.
/// 2. The production backend handles OAuth and redirects the browser to
///    `omi://auth/callback?code=xxx&state=yyy`.
/// 3. The OS routes the `omi://` deep link back to this Tauri app.
/// 4. `deliver_auth_callback` is called, which sends the code through the channel.
/// 5. We exchange the code for tokens via `POST {API}/v1/auth/token`.
/// 6. Persist session and return `AuthResult`.
#[tauri::command]
pub async fn sign_in(app: tauri::AppHandle, provider: String) -> Result<AuthResult, String> {
    let provider = if provider == "apple" || provider == "google" {
        provider
    } else {
        return Err(format!("Unsupported provider: {}. Use 'google' or 'apple'.", provider));
    };

    // 1. Set up the channel for receiving the deep-link callback
    let (tx, rx) = oneshot::channel::<(String, String)>();
    {
        let mut slot = AUTH_TX.lock().unwrap();
        // Drop any previous pending sender (e.g. a timed-out sign-in)
        *slot = Some(tx);
    }

    let state_nonce = uuid::Uuid::new_v4().to_string();

    // 2. Build the authorize URL and open it in the browser
    let authorize_url = format!(
        "{}/v1/auth/authorize?provider={}&redirect_uri={}&state={}",
        API_BASE,
        provider,
        urlencoding::encode(REDIRECT_URI),
        urlencoding::encode(&state_nonce),
    );

    tracing::info!("Opening OAuth URL in browser");

    app.opener()
        .open_url(&authorize_url, None::<&str>)
        .map_err(|e| format!("Failed to open browser: {}", e))?;

    // 3. Wait for the deep-link callback (up to 5 min)
    let (code, returned_state) = tokio::time::timeout(
        std::time::Duration::from_secs(300),
        rx,
    )
    .await
    .map_err(|_| "Sign-in timed out — no response from browser within 5 minutes.".to_string())?
    .map_err(|_| "Callback channel closed unexpectedly.".to_string())?;

    if code.is_empty() {
        return Err("OAuth callback did not include an auth code.".to_string());
    }

    if returned_state != state_nonce {
        tracing::warn!("State mismatch: expected={}, got={}", state_nonce, returned_state);
        return Err("OAuth state mismatch — possible CSRF. Please try again.".to_string());
    }

    tracing::info!("Auth code received, exchanging for tokens...");

    // 4. Exchange the code for tokens
    let client = reqwest::Client::new();
    let token_resp = client
        .post(format!("{}/v1/auth/token", API_BASE))
        .form(&[
            ("grant_type", "authorization_code"),
            ("code", &code),
            ("redirect_uri", REDIRECT_URI),
        ])
        .send()
        .await
        .map_err(|e| format!("Token exchange request failed: {}", e))?;

    if !token_resp.status().is_success() {
        let status = token_resp.status();
        let body = token_resp.text().await.unwrap_or_default();
        tracing::error!("Token exchange failed ({}): {}", status, body);
        return Err(format!("Token exchange failed ({}): {}", status, body));
    }

    let token_data: TokenResponse = token_resp
        .json()
        .await
        .map_err(|e| format!("Failed to parse token response: {}", e))?;

    // 5. Sign in to Firebase using the provider's ID token via signInWithIdp.
    //    The `id_token` from /v1/auth/token is the *provider's* token (Google/Apple),
    //    not a Firebase ID token. We use it to get a Firebase ID token.
    let provider_name = if token_data.provider.is_empty() {
        provider.clone()
    } else {
        token_data.provider.clone()
    };

    tracing::info!("Signing in to Firebase with provider {} token...", provider_name);

    let firebase = firebase_sign_in_with_provider(
        &client,
        &provider_name,
        &token_data.id_token,
        token_data.access_token.as_deref(),
    )
    .await?;
    let firebase_id_token = firebase.id_token;

    // Decode Firebase ID token to get uid and email
    let claims = decode_jwt_payload(&firebase_id_token)?;
    let user_id = if claims.user_id.is_empty() {
        claims.sub.clone()
    } else {
        claims.user_id.clone()
    };
    let email = claims.email.clone();

    if user_id.is_empty() {
        return Err("Could not extract user ID from Firebase token.".to_string());
    }

    // 6. Persist to store
    let store = app
        .store(STORE_PATH)
        .map_err(|e| format!("Failed to open store: {}", e))?;

    store.set("user_id", serde_json::json!(&user_id));
    store.set("email", serde_json::json!(&email));
    store.set("id_token", serde_json::json!(&firebase_id_token));
    store.set("refresh_token", serde_json::json!(&firebase.refresh_token));
    store
        .save()
        .map_err(|e| format!("Failed to save store: {}", e))?;

    tracing::info!("Sign-in complete for {}", email);

    Ok(AuthResult {
        user_id,
        email,
        id_token: firebase_id_token,
    })
}

/// Clear stored auth tokens and sign out.
#[tauri::command]
pub async fn sign_out(app: tauri::AppHandle) -> Result<(), String> {
    let store = app
        .store(STORE_PATH)
        .map_err(|e| format!("Failed to open store: {}", e))?;

    store.delete("user_id");
    store.delete("email");
    store.delete("id_token");
    store.delete("custom_token");
    store.delete("refresh_token");
    store.delete("token_expiry");
    store
        .save()
        .map_err(|e| format!("Failed to save store: {}", e))?;

    Ok(())
}

/// Response from Firebase token refresh endpoint.
#[derive(Debug, Deserialize)]
struct RefreshTokenResponse {
    id_token: String,
    refresh_token: String,
    #[serde(default)]
    user_id: String,
}

/// Use a Firebase refresh token to get a fresh ID token.
async fn refresh_firebase_token(
    client: &reqwest::Client,
    refresh_token: &str,
) -> Result<RefreshTokenResponse, String> {
    let url = format!(
        "https://securetoken.googleapis.com/v1/token?key={}",
        FIREBASE_API_KEY,
    );

    let resp = client
        .post(&url)
        .form(&[
            ("grant_type", "refresh_token"),
            ("refresh_token", refresh_token),
        ])
        .send()
        .await
        .map_err(|e| format!("Token refresh failed: {}", e))?;

    if !resp.status().is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("Token refresh failed: {}", body));
    }

    resp.json::<RefreshTokenResponse>()
        .await
        .map_err(|e| format!("Failed to parse refresh response: {}", e))
}

/// Check if a JWT token is expired (or will expire within 5 minutes).
fn is_token_expired(token: &str) -> bool {
    match decode_jwt_payload(token) {
        Ok(claims) => {
            // JwtClaims doesn't have exp, so decode raw to check
            let parts: Vec<&str> = token.split('.').collect();
            if parts.len() != 3 {
                return true;
            }
            let b64 = parts[1].replace('-', "+").replace('_', "/");
            let padded = match b64.len() % 4 {
                2 => format!("{}==", b64),
                3 => format!("{}=", b64),
                _ => b64,
            };
            let payload = match BASE64.decode(&padded) {
                Ok(p) => p,
                Err(_) => return true,
            };
            let value: serde_json::Value = match serde_json::from_slice(&payload) {
                Ok(v) => v,
                Err(_) => return true,
            };
            let exp = value.get("exp").and_then(|e| e.as_u64()).unwrap_or(0);
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs();
            // Treat as expired if less than 5 minutes remaining
            let _ = claims; // suppress unused warning
            now + 300 >= exp
        }
        Err(_) => true,
    }
}

/// Attempt to restore a previous session from persisted tokens.
///
/// If the stored ID token is expired, automatically refreshes it
/// using the stored refresh token.
///
/// Returns `None` if no valid session exists.
#[tauri::command]
pub async fn restore_session(app: tauri::AppHandle) -> Result<Option<AuthResult>, String> {
    let store = app
        .store(STORE_PATH)
        .map_err(|e| format!("Failed to open store: {}", e))?;

    let user_id = store.get("user_id");
    let email = store.get("email");
    let id_token = store.get("id_token");
    let refresh_token = store.get("refresh_token");

    match (user_id, email, id_token) {
        (Some(uid), Some(em), Some(tok)) => {
            let uid_str = uid.as_str().unwrap_or_default().to_string();
            let em_str = em.as_str().unwrap_or_default().to_string();
            let mut tok_str = tok.as_str().unwrap_or_default().to_string();

            if uid_str.is_empty() || tok_str.is_empty() {
                return Ok(None);
            }

            // Check if token is expired and refresh if needed
            if is_token_expired(&tok_str) {
                let rt = refresh_token
                    .and_then(|v| v.as_str().map(|s| s.to_string()))
                    .unwrap_or_default();

                if rt.is_empty() {
                    tracing::warn!("Token expired and no refresh token available");
                    return Ok(None);
                }

                tracing::info!("ID token expired, refreshing...");
                let client = reqwest::Client::new();
                match refresh_firebase_token(&client, &rt).await {
                    Ok(refreshed) => {
                        tok_str = refreshed.id_token.clone();

                        // Persist the new tokens
                        store.set("id_token", serde_json::json!(&refreshed.id_token));
                        store.set("refresh_token", serde_json::json!(&refreshed.refresh_token));
                        let _ = store.save();

                        tracing::info!("Token refreshed successfully");
                    }
                    Err(e) => {
                        tracing::error!("Token refresh failed: {}", e);
                        return Ok(None);
                    }
                }
            }

            Ok(Some(AuthResult {
                user_id: uid_str,
                email: em_str,
                id_token: tok_str,
            }))
        }
        _ => Ok(None),
    }
}

/// Force-refresh the Firebase ID token using the stored refresh token,
/// regardless of the current token's expiry claim. Used by the JS side
/// when the backend returns 401 to recover from stale/invalid tokens.
#[tauri::command]
pub async fn force_refresh_token(app: tauri::AppHandle) -> Result<Option<AuthResult>, String> {
    let store = app
        .store(STORE_PATH)
        .map_err(|e| format!("Failed to open store: {}", e))?;

    let user_id = store.get("user_id");
    let email = store.get("email");
    let refresh_token = store.get("refresh_token");

    let (uid_str, em_str, rt) = match (user_id, email, refresh_token) {
        (Some(uid), Some(em), Some(rt)) => {
            let uid_s = uid.as_str().unwrap_or_default().to_string();
            let em_s = em.as_str().unwrap_or_default().to_string();
            let rt_s = rt.as_str().unwrap_or_default().to_string();
            if uid_s.is_empty() || rt_s.is_empty() {
                return Ok(None);
            }
            (uid_s, em_s, rt_s)
        }
        _ => return Ok(None),
    };

    let client = reqwest::Client::new();
    let refreshed = refresh_firebase_token(&client, &rt).await?;

    store.set("id_token", serde_json::json!(&refreshed.id_token));
    store.set("refresh_token", serde_json::json!(&refreshed.refresh_token));
    let _ = store.save();

    tracing::info!("Firebase token force-refreshed");

    Ok(Some(AuthResult {
        user_id: uid_str,
        email: em_str,
        id_token: refreshed.id_token,
    }))
}
