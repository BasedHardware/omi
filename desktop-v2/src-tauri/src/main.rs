// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;

use tauri::Manager;
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
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_shortcuts(["CommandOrControl+\\"])
                .expect("failed to parse global shortcut")
                .with_handler(|app, shortcut, event| {
                    use tauri_plugin_global_shortcut::{Shortcut, ShortcutState};
                    let target = Shortcut::try_from("CommandOrControl+\\").ok();
                    if event.state == ShortcutState::Pressed
                        && target.as_ref() == Some(shortcut)
                    {
                        let app = app.clone();
                        tauri::async_runtime::spawn(async move {
                            if let Err(e) =
                                commands::floating::toggle_floating_bar(app).await
                            {
                                tracing::warn!("toggle_floating_bar: {}", e);
                            }
                        });
                    }
                })
                .build(),
        )
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

            // Bluetooth state — shared Manager + Adapter + peripheral cache.
            // The adapter itself is created lazily on first scan/connect so we
            // don't touch the Bluetooth stack at startup.
            commands::bluetooth::init(app.handle());

            if let Err(e) = commands::goals_db::init_and_manage(app.handle()) {
                tracing::error!("Failed to init goals DB: {}", e);
            }
            if let Err(e) = commands::memories_db::init_and_manage(app.handle()) {
                tracing::error!("Failed to init memories DB: {}", e);
            }
            if let Err(e) = commands::staged_tasks_db::init_and_manage(app.handle()) {
                tracing::error!("Failed to init staged tasks DB: {}", e);
            }

            // Push-to-talk global key listener. Emits ptt:start / ptt:stop
            // events; the frontend handles the rest (show floating bar,
            // drive audio capture, paste transcript).
            commands::ptt::start_listener(app.handle().clone());

            // Onboarding file-scan state (snapshot + running flag).
            app.manage(commands::onboarding::ScanState {
                snapshot: std::sync::Arc::new(std::sync::Mutex::new(
                    commands::onboarding::ScanSnapshot::default(),
                )),
                running: std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false)),
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
            commands::insight_sql::execute_insight_sql,
            commands::system::get_memory_usage,
            commands::bluetooth::bluetooth_start_scan,
            commands::bluetooth::bluetooth_stop_scan,
            commands::bluetooth::bluetooth_connect,
            commands::bluetooth::bluetooth_disconnect,
            commands::bluetooth::bluetooth_list_connected,
            commands::goals_db::upsert_goal,
            commands::goals_db::get_goals,
            commands::goals_db::get_completed_goals,
            commands::goals_db::get_unsynced_goals,
            commands::goals_db::update_goal_progress,
            commands::goals_db::soft_delete_goal,
            commands::goals_db::mark_goal_completed,
            commands::goals_db::mark_goal_synced,
            commands::goals_db::sync_server_goals,
            commands::goals_db::insert_goal_progress_history,
            commands::goals_db::get_goal_progress_history,
            commands::goals_db::clear_goals_db,
            // Floating bar
            commands::floating::toggle_floating_bar,
            commands::floating::hide_floating_bar,
            commands::floating::resize_floating_bar,
            commands::floating::focus_floating_bar,
            commands::floating::show_floating_alert,
            commands::floating::show_main_window,
            commands::floating::show_whispr_hud,
            commands::floating::hide_whispr_hud,
            commands::floating::resize_whispr_hud,
            commands::floating::whispr_push_live,
            // Dedicated notification floating window
            commands::notifications::show_notification_alert,
            commands::notifications::hide_notification_bar,
            commands::notifications::resize_notification_bar,
            commands::notifications::notifications_poll,
            // Live-transcript floating window (shown during meetings)
            commands::live_transcript::show_live_transcript,
            commands::live_transcript::hide_live_transcript,
            commands::live_transcript::resize_live_transcript,
            commands::live_transcript::push_live_transcript_segment,
            commands::live_transcript::poll_live_transcript_segments,
            commands::live_transcript::clear_live_transcript_buffer,
            // Paste / clipboard
            commands::paste::paste_transcript,
            commands::paste::copy_to_clipboard,
            // PTT diagnostics
            commands::ptt::ptt_diagnostics,
            commands::ptt::ptt_fire_test,
            // Memories
            commands::memories_db::insert_memory,
            commands::memories_db::get_memories,
            commands::memories_db::get_memories_by_tag,
            commands::memories_db::get_memory_by_id,
            commands::memories_db::set_memory_backend_id,
            commands::memories_db::dismiss_memory,
            commands::memories_db::delete_memory,
            // Staged tasks
            commands::staged_tasks_db::upsert_staged_task,
            commands::staged_tasks_db::get_staged_tasks,
            commands::staged_tasks_db::get_recent_staged_tasks,
            commands::staged_tasks_db::delete_staged_task,
            commands::staged_tasks_db::set_staged_task_completed,
            commands::staged_tasks_db::set_staged_task_backend_id,
            commands::staged_tasks_db::save_staged_task_embedding,
            commands::staged_tasks_db::items_missing_embeddings,
            commands::staged_tasks_db::search_similar_staged_tasks,
            commands::staged_tasks_db::search_keywords_staged_tasks,
            commands::staged_tasks_db::insert_dedup_log,
            // Onboarding
            commands::onboarding::get_platform,
            commands::onboarding::get_permission_status,
            commands::onboarding::request_permission,
            commands::onboarding::start_file_scan,
            commands::onboarding::cancel_file_scan,
            commands::onboarding::get_file_scan_status,
            commands::onboarding::set_user_preferred_name,
            commands::onboarding::set_user_language,
            commands::onboarding::set_onboarding_goal,
            commands::onboarding::set_onboarding_completed,
            commands::onboarding::onboarding_web_research,
            commands::onboarding::onboarding_organization_hint,
            commands::onboarding::gemini_onboarding_research,
            // Shortcut capture (used by onboarding shortcut steps)
            commands::shortcut_capture::start_shortcut_capture,
            commands::shortcut_capture::stop_shortcut_capture,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
