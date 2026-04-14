use base64::{engine::general_purpose::URL_SAFE_NO_PAD as BASE64URL, Engine};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_store::StoreExt;
use tokio::sync::oneshot;

const STORE_PATH: &str = "claude_oauth.json";
const CLIENT_ID: &str = "9d1c250a-e61b-44d9-88ed-5944d1962f5e";
const AUTHORIZE_URL: &str = "https://claude.ai/oauth/authorize";
const TOKEN_URL: &str = "https://console.anthropic.com/v1/oauth/token";
const SCOPE: &str = "user:inference";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClaudeAuthResult {
    pub access_token: String,
    /// When the token expires (unix seconds), if known.
    pub expires_at: Option<u64>,
}

/// Token exchange response from Anthropic.
#[derive(Debug, Deserialize)]
struct TokenResponse {
    access_token: String,
    #[serde(default)]
    expires_in: Option<u64>,
    #[serde(default)]
    refresh_token: Option<String>,
}

/// Generate a PKCE code verifier (random 43-char URL-safe string).
fn generate_code_verifier() -> String {
    let a = uuid::Uuid::new_v4();
    let b = uuid::Uuid::new_v4();
    let mut bytes = [0u8; 32];
    bytes[..16].copy_from_slice(a.as_bytes());
    bytes[16..].copy_from_slice(b.as_bytes());
    BASE64URL.encode(bytes)
}

/// Compute the PKCE code challenge (S256): BASE64URL(SHA256(verifier)).
fn compute_code_challenge(verifier: &str) -> String {
    let digest = Sha256::digest(verifier.as_bytes());
    BASE64URL.encode(digest)
}

/// HTML page shown in the browser after successful OAuth callback.
const SUCCESS_HTML: &str = r#"<!DOCTYPE html>
<html><head><title>Nooto</title>
<style>body{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#111;color:#fff}
.card{text-align:center;padding:2rem}h1{font-size:1.5rem;margin-bottom:.5rem}p{color:#888;font-size:.9rem}</style>
</head><body><div class="card"><h1>Signed in successfully</h1><p>You can close this tab and return to Nooto.</p></div></body></html>"#;

/// Axum query params for the callback route.
#[derive(Deserialize)]
struct CallbackParams {
    #[serde(default)]
    code: String,
    #[serde(default)]
    state: String,
}

/// Initiate Claude OAuth PKCE sign-in.
///
/// 1. Generates PKCE code_verifier + code_challenge.
/// 2. Starts a temporary local HTTP server on a random port.
/// 3. Opens Claude authorize URL in the system browser.
/// 4. Browser redirects to `http://localhost:{port}/callback?code=...&state=...`.
/// 5. Exchanges the authorization code for tokens.
/// 6. Persists the access token and returns it.
#[tauri::command]
pub async fn claude_sign_in(app: tauri::AppHandle) -> Result<ClaudeAuthResult, String> {
    // 1. PKCE
    let code_verifier = generate_code_verifier();
    let code_challenge = compute_code_challenge(&code_verifier);
    let state_nonce = uuid::Uuid::new_v4().to_string();

    // 2. Bind a TCP listener on a random port.
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .map_err(|e| format!("Failed to bind callback server: {}", e))?;

    let port = listener
        .local_addr()
        .map_err(|e| format!("Failed to get local addr: {}", e))?
        .port();

    let redirect_uri = format!("http://localhost:{}/callback", port);
    tracing::info!("OAuth callback server listening on {}", redirect_uri);

    // Channel for passing the code+state from the callback handler.
    let (tx, rx) = oneshot::channel::<(String, String)>();
    let tx = std::sync::Arc::new(std::sync::Mutex::new(Some(tx)));

    // Build a minimal Axum app with one route.
    let callback_tx = tx.clone();
    let router = axum::Router::new().route(
        "/callback",
        axum::routing::get(
            move |axum::extract::Query(params): axum::extract::Query<CallbackParams>| {
                let tx = callback_tx.clone();
                async move {
                    if let Some(sender) = tx.lock().unwrap().take() {
                        let _ = sender.send((params.code, params.state));
                    }
                    axum::response::Html(SUCCESS_HTML)
                }
            },
        ),
    );

    // Spawn the server.
    let server_handle = tokio::spawn(async move {
        let _ = axum::serve(listener, router).await;
    });

    // 3. Open the authorize URL in the browser.
    let authorize_url = format!(
        "{}?code=true&response_type=code&client_id={}&redirect_uri={}&scope={}&state={}&code_challenge={}&code_challenge_method=S256",
        AUTHORIZE_URL,
        CLIENT_ID,
        urlencoding::encode(&redirect_uri),
        urlencoding::encode(SCOPE),
        urlencoding::encode(&state_nonce),
        urlencoding::encode(&code_challenge),
    );

    tracing::info!("Opening Claude OAuth URL in browser");

    app.opener()
        .open_url(&authorize_url, None::<&str>)
        .map_err(|e| format!("Failed to open browser: {}", e))?;

    // 4. Wait for callback (10 min timeout, matching ACP bridge).
    let (code, returned_state) = tokio::time::timeout(
        std::time::Duration::from_secs(600),
        rx,
    )
    .await
    .map_err(|_| {
        server_handle.abort();
        "Claude sign-in timed out — no response from browser within 10 minutes.".to_string()
    })?
    .map_err(|_| {
        server_handle.abort();
        "Callback channel closed unexpectedly.".to_string()
    })?;

    // Shut down the callback server.
    server_handle.abort();

    if code.is_empty() {
        return Err("OAuth callback did not include an authorization code.".to_string());
    }

    if returned_state != state_nonce {
        tracing::warn!("State mismatch: expected={}, got={}", state_nonce, returned_state);
        return Err("OAuth state mismatch — possible CSRF. Please try again.".to_string());
    }

    tracing::info!("Claude auth code received, exchanging for tokens...");

    // 5. Exchange code for tokens.
    let client = reqwest::Client::new();
    let token_resp = client
        .post(TOKEN_URL)
        .form(&[
            ("grant_type", "authorization_code"),
            ("client_id", CLIENT_ID),
            ("code", code.as_str()),
            ("redirect_uri", redirect_uri.as_str()),
            ("code_verifier", code_verifier.as_str()),
            ("state", state_nonce.as_str()),
            ("expires_in", "31536000"),
        ])
        .send()
        .await
        .map_err(|e| format!("Token exchange request failed: {}", e))?;

    if !token_resp.status().is_success() {
        let status = token_resp.status();
        let body = token_resp.text().await.unwrap_or_default();
        tracing::error!("Claude token exchange failed ({}): {}", status, body);
        return Err(format!("Token exchange failed ({}): {}", status, body));
    }

    let token_data: TokenResponse = token_resp
        .json()
        .await
        .map_err(|e| format!("Failed to parse token response: {}", e))?;

    let now_secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    let expires_at = token_data.expires_in.map(|secs| now_secs + secs);

    // 6. Persist to store.
    let store = app
        .store(STORE_PATH)
        .map_err(|e| format!("Failed to open store: {}", e))?;

    store.set("access_token", serde_json::json!(&token_data.access_token));
    if let Some(rt) = &token_data.refresh_token {
        store.set("refresh_token", serde_json::json!(rt));
    }
    if let Some(ea) = expires_at {
        store.set("expires_at", serde_json::json!(ea));
    }
    store
        .save()
        .map_err(|e| format!("Failed to save store: {}", e))?;

    tracing::info!("Claude OAuth sign-in complete");

    Ok(ClaudeAuthResult {
        access_token: token_data.access_token,
        expires_at,
    })
}

/// Clear stored Claude OAuth tokens.
#[tauri::command]
pub async fn claude_sign_out(app: tauri::AppHandle) -> Result<(), String> {
    let store = app
        .store(STORE_PATH)
        .map_err(|e| format!("Failed to open store: {}", e))?;

    store.delete("access_token");
    store.delete("refresh_token");
    store.delete("expires_at");
    store
        .save()
        .map_err(|e| format!("Failed to save store: {}", e))?;

    Ok(())
}

/// Attempt to restore a previous Claude OAuth session.
///
/// Returns `None` if no valid session exists or the token has expired.
#[tauri::command]
pub async fn claude_restore_session(app: tauri::AppHandle) -> Result<Option<ClaudeAuthResult>, String> {
    let store = app
        .store(STORE_PATH)
        .map_err(|e| format!("Failed to open store: {}", e))?;

    let access_token = store.get("access_token");
    let expires_at = store.get("expires_at");

    match access_token {
        Some(tok) => {
            let tok_str = tok.as_str().unwrap_or_default().to_string();
            if tok_str.is_empty() {
                return Ok(None);
            }

            let ea = expires_at.and_then(|v| v.as_u64());
            if let Some(exp) = ea {
                let now = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs();
                if now >= exp {
                    let refresh_token = store
                        .get("refresh_token")
                        .and_then(|v| v.as_str().map(|s| s.to_string()));

                    if let Some(rt) = refresh_token {
                        match refresh_claude_token(&rt).await {
                            Ok(new_token) => {
                                let new_ea = new_token.expires_in.map(|secs| now + secs);

                                store.set("access_token", serde_json::json!(&new_token.access_token));
                                if let Some(new_rt) = &new_token.refresh_token {
                                    store.set("refresh_token", serde_json::json!(new_rt));
                                }
                                if let Some(ea) = new_ea {
                                    store.set("expires_at", serde_json::json!(ea));
                                }
                                let _ = store.save();

                                tracing::info!("Claude token refreshed successfully");
                                return Ok(Some(ClaudeAuthResult {
                                    access_token: new_token.access_token,
                                    expires_at: new_ea,
                                }));
                            }
                            Err(e) => {
                                tracing::warn!("Claude token refresh failed: {}", e);
                                return Ok(None);
                            }
                        }
                    } else {
                        tracing::warn!("Claude token expired and no refresh token available");
                        return Ok(None);
                    }
                }
            }

            Ok(Some(ClaudeAuthResult {
                access_token: tok_str,
                expires_at: ea,
            }))
        }
        None => Ok(None),
    }
}

/// Refresh an expired Claude OAuth token.
async fn refresh_claude_token(refresh_token: &str) -> Result<TokenResponse, String> {
    let client = reqwest::Client::new();
    let resp = client
        .post(TOKEN_URL)
        .form(&[
            ("grant_type", "refresh_token"),
            ("client_id", CLIENT_ID),
            ("refresh_token", refresh_token),
        ])
        .send()
        .await
        .map_err(|e| format!("Token refresh failed: {}", e))?;

    if !resp.status().is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("Token refresh failed: {}", body));
    }

    resp.json::<TokenResponse>()
        .await
        .map_err(|e| format!("Failed to parse refresh response: {}", e))
}
