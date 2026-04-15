// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;

use tauri_plugin_deep_link::DeepLinkExt;
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt};

/// Spawn the embedded Axum backend on a background Tokio task.
///
/// The backend listens on 127.0.0.1:{port} and serves the same REST API
/// as the standalone `Backend-Rust` server.
async fn start_backend() {
    let port: u16 = std::env::var("OMI_BACKEND_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(10201);

    match nooto_desktop_backend::init_services().await {
        Ok((state, firebase_auth)) => {
            let app = nooto_desktop_backend::build_router(state, firebase_auth);
            let addr = format!("127.0.0.1:{}", port);
            tracing::info!("Embedded backend starting on {}", addr);

            match tokio::net::TcpListener::bind(&addr).await {
                Ok(listener) => {
                    if let Err(e) = axum::serve(listener, app).await {
                        tracing::error!("Backend server error: {}", e);
                    }
                }
                Err(e) => {
                    tracing::error!("Failed to bind backend to {}: {}", addr, e);
                }
            }
        }
        Err(e) => {
            tracing::warn!("Failed to initialize backend services: {} — running without embedded backend", e);
        }
    }
}

fn main() {
    // Load .env from the src-tauri directory (or parent) for local API keys
    dotenvy::dotenv().ok();

    // Initialize tracing (stdout only for Tauri)
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "nooto_desktop_v2=info,nooto_desktop_backend=info,tauri_plugin_screen_capture=info,tauri_plugin_audio_capture=debug,tower_http=info".into()),
        )
        .with(
            fmt::layer()
                .with_target(false)
                .with_level(true)
                .with_ansi(true),
        )
        .init();

    // Spawn the backend server in the background before Tauri starts
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .expect("Failed to create Tokio runtime");

    runtime.spawn(start_backend());

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_single_instance::init(|_app, _argv, _cwd| {
            // When a second instance is launched (e.g. via deep link), the
            // deep-link plugin will receive the URL through this callback
            // automatically — no extra handling needed here.
            tracing::info!("Single-instance: second launch detected");
        }))
        .plugin(tauri_plugin_store::Builder::default().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_global_shortcut::Builder::default().build())
        .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, None))
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_audio_capture::init())
        .plugin(tauri_plugin_screen_capture::init())
        .setup(|app| {
            // Register the omi:// URL scheme so the OS routes it to this app.
            #[cfg(any(target_os = "linux", target_os = "windows"))]
            {
                if let Err(e) = app.deep_link().register("nooto") {
                    tracing::warn!("Failed to register nooto:// deep link: {}", e);
                }
            }

            // Listen for deep-link events (omi://auth/callback?code=xxx&state=yyy)
            app.deep_link().on_open_url(|event| {
                let urls = event.urls();
                for url in &urls {
                    tracing::info!("Deep link received: {}", url);
                    if url.scheme() == "nooto"
                        && (url.path() == "/auth/callback" || url.host_str() == Some("auth"))
                    {
                        commands::auth::deliver_auth_callback(url);
                    }
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::auth::sign_in,
            commands::auth::sign_out,
            commands::auth::restore_session,
            commands::auth::force_refresh_token,
            commands::claude_oauth::claude_sign_in,
            commands::claude_oauth::claude_sign_out,
            commands::claude_oauth::claude_restore_session,
            commands::config::get_gemini_api_key,
            commands::debug::debug_backend_ping,
            commands::debug::backend_request,
            commands::system::get_memory_usage,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
