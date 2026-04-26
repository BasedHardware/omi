//! Shared localhost OAuth callback server.
//!
//! Both the Firebase sign-in flow (`commands::auth`) and the Claude OAuth flow
//! (`commands::claude_oauth`) need the same scaffolding: bind a TCP listener on
//! a random loopback port, serve a single `/callback` route, open the authorize
//! URL in the user's browser, and wait for the redirect. This module centralises
//! that so the caller only specifies the timeout and how to build the authorize
//! URL given the bound `redirect_uri`.

use serde::Deserialize;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri_plugin_opener::OpenerExt;
use tokio::sync::oneshot;

const SUCCESS_HTML: &str = r#"<!DOCTYPE html>
<html><head><title>Nooto</title>
<style>body{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#111;color:#fff}
.card{text-align:center;padding:2rem}h1{font-size:1.5rem;margin-bottom:.5rem}p{color:#888;font-size:.9rem}</style>
</head><body><div class="card"><h1>Signed in successfully</h1><p>You can close this tab and return to Nooto.</p></div></body></html>"#;

// Second/stale callback hits after the code was already delivered must not
// claim success — a confused user or a replay probe shouldn't see the same UI.
const ALREADY_COMPLETED_HTML: &str = r#"<!DOCTYPE html>
<html><head><title>Nooto</title>
<style>body{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#111;color:#fff}
.card{text-align:center;padding:2rem}h1{font-size:1.5rem;margin-bottom:.5rem}p{color:#888;font-size:.9rem}</style>
</head><body><div class="card"><h1>Sign-in already completed</h1><p>You can close this tab.</p></div></body></html>"#;

#[derive(Deserialize)]
struct CallbackParams {
    #[serde(default)]
    code: String,
    #[serde(default)]
    state: String,
}

/// RAII guard that aborts the background axum task on every exit path —
/// including failures after the callback has been received (token exchange,
/// JWT decode, store writes). Without this, those error paths leaked the
/// server task until the process exits.
struct AbortOnDrop(tokio::task::JoinHandle<()>);
impl Drop for AbortOnDrop {
    fn drop(&mut self) {
        self.0.abort();
    }
}

pub struct CallbackResult {
    pub code: String,
    pub redirect_uri: String,
}

/// Run the localhost OAuth callback flow.
///
/// 1. Binds `127.0.0.1:0` and serves `GET /callback`.
/// 2. Calls `build_authorize_url(redirect_uri)` and opens the returned URL in
///    the user's browser.
/// 3. Waits up to `timeout` for the browser to hit `/callback`.
/// 4. Verifies the returned `state` matches `expected_state` (CSRF).
/// 5. Returns the `code` plus the `redirect_uri` used (callers need the latter
///    for the subsequent token-exchange call).
pub async fn run<F>(
    app: &tauri::AppHandle,
    timeout: Duration,
    expected_state: &str,
    build_authorize_url: F,
) -> Result<CallbackResult, String>
where
    F: FnOnce(&str) -> String,
{
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .map_err(|e| format!("Failed to bind callback server: {}", e))?;
    let port = listener
        .local_addr()
        .map_err(|e| format!("Failed to get local addr: {}", e))?
        .port();
    let redirect_uri = format!("http://127.0.0.1:{}/callback", port);
    tracing::info!("OAuth callback server listening on {}", redirect_uri);

    let (tx, rx) = oneshot::channel::<(String, String)>();
    let tx = Arc::new(Mutex::new(Some(tx)));

    let callback_tx = tx.clone();
    let router = axum::Router::new().route(
        "/callback",
        axum::routing::get(
            move |axum::extract::Query(params): axum::extract::Query<CallbackParams>| {
                let tx = callback_tx.clone();
                async move {
                    let delivered = match tx.lock().unwrap().take() {
                        Some(sender) => sender.send((params.code, params.state)).is_ok(),
                        None => false,
                    };
                    if delivered {
                        axum::response::Html(SUCCESS_HTML)
                    } else {
                        axum::response::Html(ALREADY_COMPLETED_HTML)
                    }
                }
            },
        ),
    );

    let _server = AbortOnDrop(tokio::spawn(async move {
        let _ = axum::serve(listener, router).await;
    }));

    let authorize_url = build_authorize_url(&redirect_uri);
    tracing::info!("Opening OAuth URL in browser");
    app.opener()
        .open_url(&authorize_url, None::<&str>)
        .map_err(|e| format!("Failed to open browser: {}", e))?;

    let (code, returned_state) = tokio::time::timeout(timeout, rx)
        .await
        .map_err(|_| "Sign-in timed out — no response from browser.".to_string())?
        .map_err(|_| "Callback channel closed unexpectedly.".to_string())?;

    if code.is_empty() {
        return Err("OAuth callback did not include an auth code.".to_string());
    }

    if returned_state != expected_state {
        tracing::warn!("State mismatch: expected={}, got={}", expected_state, returned_state);
        return Err("OAuth state mismatch — possible CSRF. Please try again.".to_string());
    }

    Ok(CallbackResult { code, redirect_uri })
}
