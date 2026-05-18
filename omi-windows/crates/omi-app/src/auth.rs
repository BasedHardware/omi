use dioxus::prelude::*;
use serde::Deserialize;

use crate::config::AppConfig;

const AUTH_CALLBACK_PORT: u16 = 19876;

/// Auth state shared via Dioxus context.
#[derive(Debug, Clone, PartialEq)]
pub enum AuthStatus {
    SignedOut,
    Pending,
    SignedIn { email: String, name: String },
    Error(String),
}

/// Response from Backend-Rust /v1/auth/token
#[derive(Debug, Deserialize)]
struct TokenResponse {
    id_token: String,
    #[serde(default)]
    provider_id: String,
    #[serde(default)]
    provider: String,
    #[serde(default)]
    #[allow(dead_code)]
    custom_token: Option<String>,
}

/// Start the Google sign-in flow.
///
/// 1. Spawn a tiny local HTTP server to receive the OAuth code callback
/// 2. Open system browser to Backend-Rust /v1/auth/authorize
/// 3. Backend handles Google OAuth, redirects back with a code
/// 4. We exchange the code for a Firebase token
pub async fn start_google_sign_in(
    auth_status: &mut Signal<AuthStatus>,
    config: &mut Signal<AppConfig>,
) {
    auth_status.set(AuthStatus::Pending);

    let backend_url = config.read().backend_url.clone();
    let redirect_uri = format!("http://localhost:{AUTH_CALLBACK_PORT}/callback");

    // Build the authorize URL
    let authorize_url = format!(
        "{backend_url}/v1/auth/authorize?provider=google&redirect_uri={}",
        urlencoding::encode(&redirect_uri)
    );

    // Open system browser
    if let Err(e) = webbrowser::open(&authorize_url) {
        auth_status.set(AuthStatus::Error(format!("Failed to open browser: {e}")));
        return;
    }

    // Listen for the callback
    match listen_for_callback().await {
        Ok(code) => {
            // Exchange code for token
            match exchange_code(&backend_url, &code, &redirect_uri).await {
                Ok(token_resp) => {
                    let mut cfg = config.write();
                    cfg.firebase_id_token = token_resp.id_token;
                    cfg.user_email = token_resp.provider_id.clone();
                    cfg.user_display_name = token_resp.provider.clone();

                    if let Err(e) = cfg.save() {
                        tracing::warn!("Failed to save config after sign-in: {e}");
                    }

                    let email = cfg.user_email.clone();
                    let name = cfg.user_display_name.clone();
                    drop(cfg);

                    auth_status.set(AuthStatus::SignedIn { email, name });
                    tracing::info!("Sign-in complete");
                }
                Err(e) => {
                    auth_status.set(AuthStatus::Error(format!("Token exchange failed: {e}")));
                }
            }
        }
        Err(e) => {
            auth_status.set(AuthStatus::Error(format!("Callback listener failed: {e}")));
        }
    }
}

/// Listen on a local port for the OAuth callback redirect.
async fn listen_for_callback() -> anyhow::Result<String> {
    let listener = tokio::net::TcpListener::bind(format!("127.0.0.1:{AUTH_CALLBACK_PORT}")).await?;
    tracing::info!("Auth callback listener on port {AUTH_CALLBACK_PORT}");

    // Accept one connection with a timeout
    let (stream, _) = tokio::time::timeout(
        std::time::Duration::from_secs(120),
        listener.accept(),
    )
    .await
    .map_err(|_| anyhow::anyhow!("Auth callback timed out after 120s"))??;

    let mut buf = vec![0u8; 4096];
    let n = {
        stream.readable().await?;
        stream.try_read(&mut buf).unwrap_or(0)
    };
    let request = String::from_utf8_lossy(&buf[..n]);

    // Extract code from GET /callback?code=...
    let code = extract_query_param(&request, "code")
        .ok_or_else(|| anyhow::anyhow!("No 'code' param in callback"))?;

    // Send a simple HTML response
    let response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n\
        <html><body style='font-family:sans-serif;text-align:center;padding:60px'>\
        <h1>Signed in!</h1><p>You can close this tab and return to Omi.</p>\
        </body></html>";
    stream.writable().await?;
    let _ = stream.try_write(response.as_bytes());

    Ok(code)
}

/// Extract a query parameter from a raw HTTP request string.
fn extract_query_param(request: &str, param: &str) -> Option<String> {
    let first_line = request.lines().next()?;
    let path = first_line.split_whitespace().nth(1)?;
    let query_start = path.find('?')?;
    let query = &path[query_start + 1..];

    for pair in query.split('&') {
        let mut kv = pair.splitn(2, '=');
        if let (Some(key), Some(value)) = (kv.next(), kv.next()) {
            if key == param {
                return Some(urlencoding::decode(value).unwrap_or_default().into_owned());
            }
        }
    }
    None
}

/// Exchange an auth code for tokens via Backend-Rust.
async fn exchange_code(
    backend_url: &str,
    code: &str,
    redirect_uri: &str,
) -> anyhow::Result<TokenResponse> {
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{backend_url}/v1/auth/token"))
        .form(&[
            ("grant_type", "authorization_code"),
            ("code", code),
            ("redirect_uri", redirect_uri),
        ])
        .send()
        .await?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        anyhow::bail!("Token endpoint returned {status}: {body}");
    }

    let token: TokenResponse = resp.json().await?;
    Ok(token)
}
