// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod feature_flags;

use std::sync::Arc;

use tauri::{AppHandle, Emitter, Manager, Runtime};
use tauri_plugin_deep_link::DeepLinkExt;
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt};

/// Adapter that lets the embedded Backend-Rust emit Tauri events to the
/// renderer without taking on a Tauri dependency itself. Backend-Rust knows
/// nothing about `AppHandle` — it just calls `EventEmitter::emit`.
struct TauriEventEmitter<R: Runtime> {
    handle: AppHandle<R>,
}

impl<R: Runtime> nooto_desktop_backend::EventEmitter for TauriEventEmitter<R> {
    fn emit(&self, event: &str, payload: serde_json::Value) {
        if let Err(e) = self.handle.emit(event, payload) {
            tracing::warn!("backend event emit ({}) failed: {}", event, e);
        }
    }
}

/// Spawn the embedded Axum backend on a background Tokio task.
///
/// The backend listens on 127.0.0.1:{port} and serves the same REST API
/// as the standalone `Backend-Rust` server.
async fn start_backend<R: Runtime>(handle: AppHandle<R>) {
    let port: u16 = std::env::var("OMI_BACKEND_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(10201);

    match nooto_desktop_backend::init_services().await {
        Ok((mut state, firebase_auth)) => {
            // Wire the UI event sink so route handlers (e.g. the
            // app-result persistence path) can emit Tauri events.
            state.events = Some(Arc::new(TauriEventEmitter { handle }));

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

    // Dedicated runtime for the embedded Backend-Rust so its workers don't
    // contend with the Tauri/audio runtime. Leaked so it lives for the
    // process lifetime — we'll spawn `start_backend` from inside `setup`
    // once we have an `AppHandle` to thread into the event emitter.
    let backend_runtime: &'static tokio::runtime::Runtime = Box::leak(Box::new(
        tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .thread_name("backend-worker")
            .build()
            .expect("Failed to create Tokio runtime"),
    ));

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
                            if feature_flags::COMPANION_CUTOVER_ENABLED {
                                // Tap Cmd+Ctrl+\ — toggle the companion buddy
                                // (show if hidden, hide if visible).
                                if let Some(w) = app.get_webview_window("companion-buddy") {
                                    let visible = w.is_visible().unwrap_or(false);
                                    if visible {
                                        if let Err(e) = commands::companion::companion_hide_buddy(app).await {
                                            tracing::warn!("companion_hide_buddy: {}", e);
                                        }
                                    } else if let Err(e) = commands::companion::companion_show_buddy(app).await {
                                        tracing::warn!("companion_show_buddy: {}", e);
                                    }
                                }
                            } else {
                                // Legacy: toggle the Ask Nooto floating bar.
                                if let Err(e) =
                                    commands::floating::toggle_floating_bar(app).await
                                {
                                    tracing::warn!("toggle_floating_bar: {}", e);
                                }
                            }
                        });
                    }
                })
                .build(),
        )
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, None))
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_audio_capture::init())
        .plugin(tauri_plugin_screen_capture::init())
        .plugin(tauri_plugin_tts::init())
        .setup(|app| {
            // Spawn the embedded Backend-Rust now that we have an AppHandle
            // — the handle is wrapped in a `TauriEventEmitter` and injected
            // into AppState so route handlers can push UI events back to
            // the renderer (e.g. `conversation:updated` when an app result
            // is persisted async after a recording finishes).
            backend_runtime.spawn(start_backend(app.handle().clone()));

            // Register the omi:// URL scheme so the OS routes it to this app.
            #[cfg(any(target_os = "linux", target_os = "windows"))]
            {
                if let Err(e) = app.deep_link().register("nooto") {
                    tracing::warn!("Failed to register nooto:// deep link: {}", e);
                }
            }

            let deep_link_handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                use tauri::{Emitter, Manager};
                for url in &event.urls() {
                    let raw = url.as_str();
                    tracing::info!("Deep link received: {}", raw);
                    // Clicking a notification opens `nooto://notification-click`
                    // (see `/Applications/Nooto.app/Contents/MacOS/Nooto`). Match
                    // on the raw string because `url::Url::host_str()` returns
                    // None for custom schemes on some parser versions. Bring the
                    // main window forward and emit an event so the frontend can
                    // route to /chat and seed the notification body.
                    if url.scheme() == "nooto" && raw.contains("notification-click") {
                        tracing::info!("Deep link: dispatching notification:click");
                        if let Some(window) = deep_link_handle.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                        let _ = deep_link_handle.emit("notification:click", ());
                    }
                    // Plugin OAuth handoff: when a plugin's setup page redirects
                    // to `nooto://app-setup-complete?app_id=<id>&status=success`,
                    // bring the window back, parse `app_id`, and notify the
                    // frontend so it can re-attempt enable.
                    if url.scheme() == "nooto" && raw.contains("app-setup-complete") {
                        let mut app_id = String::new();
                        let mut status = String::from("success");
                        for (k, v) in url.query_pairs() {
                            match k.as_ref() {
                                "app_id" => app_id = v.into_owned(),
                                "status" => status = v.into_owned(),
                                _ => {}
                            }
                        }
                        tracing::info!(
                            "Deep link: dispatching apps:setup-complete app_id={} status={}",
                            app_id,
                            status
                        );
                        if let Some(window) = deep_link_handle.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                        let _ = deep_link_handle.emit(
                            "apps:setup-complete",
                            serde_json::json!({ "app_id": app_id, "status": status }),
                        );
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

            // PTT global key listener is opt-in, not auto-started. Starting
            // rdev here can crash the app silently on macOS when Input
            // Monitoring / Accessibility aren't granted (rdev's C shim calls
            // `exit(-1)` on the first event). The onboarding Accessibility
            // step calls `ensure_ptt_listener` after granting, and the
            // Settings page can too — so real users get PTT exactly when
            // the OS will cooperate.

            // Coding agent: running Pi child processes keyed by session_id.
            app.manage(commands::coding_agent::CodingAgentState::default());

            // Onboarding file-scan state (snapshot + running flag).
            app.manage(commands::onboarding::ScanState {
                snapshot: std::sync::Arc::new(std::sync::Mutex::new(
                    commands::onboarding::ScanSnapshot::default(),
                )),
                running: std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false)),
            });

            // Companion cutover: retire the legacy "floating" Ask-Nooto bar so
            // it never appears in this release. We keep the Whispr window
            // alive — Companion is for AI Q&A, Whispr is for dictation; they
            // serve different purposes and the user explicitly wants both.
            if feature_flags::COMPANION_CUTOVER_ENABLED {
                if let Some(w) = app.get_webview_window("floating") {
                    if let Err(e) = w.close() {
                        tracing::warn!("cutover: failed to close floating window: {}", e);
                    }
                }
            }

            // Tray / menu-bar icon with quick toggles.
            if let Err(e) = commands::tray::build(app.handle()) {
                tracing::warn!("Failed to build tray icon: {}", e);
            }

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
            commands::debug::backend_chat_stream,
            commands::insight_sql::execute_insight_sql,
            commands::system::get_active_app,
            commands::system::get_dock_icons,
            commands::system::get_memory_usage,
            commands::system::read_file_bytes,
            commands::system::term_log,
            commands::system::relaunch_app,
            commands::system::suspend_global_shortcuts,
            commands::system::restore_global_shortcuts,
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
            // Companion buddy + overlays
            commands::companion::companion_show_buddy,
            commands::companion::companion_hide_buddy,
            commands::companion::companion_ensure_overlays,
            commands::companion::companion_set_overlays_visible,
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
            // OS-native notification (delegates to tauri-plugin-notification)
            commands::notifications::show_notification_alert,
            commands::notifications::take_last_notification,
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
            commands::ptt::ensure_ptt_listener,
            commands::ptt::set_ptt_key,
            commands::ptt::get_ptt_key,
            commands::ptt::set_companion_key,
            commands::ptt::get_companion_key,
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
            // Tray menu updates (check marks + label changes)
            commands::tray::update_tray_menu,
            commands::tray::set_tray_ask_label,
            // Coding agent
            commands::coding_agent::coding_agent_pick_folder,
            commands::coding_agent::coding_agent_start_session,
            commands::coding_agent::coding_agent_send_message,
            commands::coding_agent::coding_agent_send_raw_rpc,
            commands::coding_agent::coding_agent_stop_session,
            // Coding agent sessions
            commands::coding_agent_sessions::coding_agent_list_sessions,
            commands::coding_agent_sessions::coding_agent_delete_session,
            commands::coding_agent_sessions::coding_agent_rename_session,
            commands::coding_agent_sessions::coding_agent_load_session_messages,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
