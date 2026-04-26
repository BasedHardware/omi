use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use serde::{Deserialize, Serialize};
use tauri_plugin_store::StoreExt;

use super::oauth_callback;

const STORE_PATH: &str = "auth.json";
const API_BASE: &str = "https://nooto-desktop-auth-1060764816205.us-central1.run.app";
const FIREBASE_API_KEY: &str = "AIzaSyAPDdy9ZUCMQOPvcbjkB-dQn6WPcPY5nng";
const CALLBACK_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(300);

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

/// Initiate sign-in flow.
///
/// 1. Binds a localhost HTTP listener on a random port as the OAuth redirect target.
/// 2. Opens `{API}/v1/auth/authorize?provider=...&redirect_uri=http://127.0.0.1:<port>/callback`
///    in the system browser.
/// 3. The production backend handles OAuth with Google/Apple and redirects the
///    browser to our local callback with `?code=xxx&state=yyy`.
/// 4. The local server captures the code and shuts down.
/// 5. We exchange the code for tokens via `POST {API}/v1/auth/token`.
/// 6. Persist session and return `AuthResult`.
#[tauri::command]
pub async fn sign_in(app: tauri::AppHandle, provider: String) -> Result<AuthResult, String> {
    let provider = if provider == "apple" || provider == "google" {
        provider
    } else {
        return Err(format!("Unsupported provider: {}. Use 'google' or 'apple'.", provider));
    };

    let state_nonce = uuid::Uuid::new_v4().to_string();

    let callback = oauth_callback::run(&app, CALLBACK_TIMEOUT, &state_nonce, |redirect_uri| {
        format!(
            "{}/v1/auth/authorize?provider={}&redirect_uri={}&state={}",
            API_BASE,
            provider,
            urlencoding::encode(redirect_uri),
            urlencoding::encode(&state_nonce),
        )
    })
    .await?;

    tracing::info!("Auth code received, exchanging for tokens...");

    let client = reqwest::Client::new();
    let token_resp = client
        .post(format!("{}/v1/auth/token", API_BASE))
        .form(&[
            ("grant_type", "authorization_code"),
            ("code", &callback.code),
            ("redirect_uri", &callback.redirect_uri),
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
