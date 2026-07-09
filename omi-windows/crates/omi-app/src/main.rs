use dioxus::prelude::*;

mod agent_runtime;
mod app;
mod app_tracker;
mod auth;
mod capture;
mod clipboard_watcher;
mod components;
mod config;
mod context_watcher;
mod daily_recap;
mod file_indexer;
mod google_calendar;
mod hooks;
mod hotkey;
mod knowledge;
mod llm;
mod mcp_bridge;
mod notification_history;
mod notifications;
mod pages;
mod proactive;
mod recording;
mod sidecar;
mod sync;
mod tts_engine;
mod tray;
mod web_search;


pub const MAIN_CSS: &str = include_str!("assets/main.css");

fn main() {
    // Load .env from working directory (omi-windows/.env)
    dotenvy::dotenv().ok();

    // Write logs to %APPDATA%\omi\debug.log so they're visible even without a console
    let log_dir = std::path::PathBuf::from(
        std::env::var("APPDATA").unwrap_or_else(|_| ".".into()),
    ).join("omi");
    std::fs::create_dir_all(&log_dir).ok();
    let log_path = log_dir.join("debug.log");
    // Truncate (overwrite) log on each launch for a clean read
    let log_file = std::fs::OpenOptions::new()
        .create(true).write(true).truncate(true).open(&log_path)
        .expect("open log file");
    let log_writer = std::sync::Mutex::new(log_file);

    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "omi=debug,omi_transcription=debug,omi_audio=debug".into()),
        )
        .with_target(false)
        .with_ansi(false)
        .with_writer(log_writer)
        .init();

    eprintln!("Logging to: {}", log_path.display());

    tracing::info!("Starting Omi Windows");

    match omi_audio::mic::list_input_devices() {
        Ok(devices) => tracing::info!("[AUDIO] Available input devices: {:?}", devices),
        Err(e) => tracing::warn!("[AUDIO] Failed to list input devices: {e}"),
    }

    // ── Global hotkeys (Ctrl+Shift+Space / Ctrl+Shift+R) ──────────────────────
    let _hotkey_manager = match hotkey::init() {
        Ok(m) => {
            tracing::info!("[HOTKEY] Registered global hotkeys");
            Some(m)
        }
        Err(e) => {
            tracing::warn!("[HOTKEY] Failed to register hotkeys: {e} (running without hotkeys)");
            None
        }
    };

    // ── System tray ────────────────────────────────────────────────────────────
    let _tray = match tray::init() {
        Ok(t) => {
            tracing::info!("[TRAY] System tray created");
            Some(t)
        }
        Err(e) => {
            tracing::warn!("[TRAY] Failed to create tray: {e} (running without tray)");
            None
        }
    };

    let window_cfg = dioxus::desktop::Config::new()
        .with_window(
            dioxus::desktop::tao::window::WindowBuilder::new()
                .with_title("Omi")
                .with_inner_size(dioxus::desktop::tao::dpi::LogicalSize::new(1100.0, 720.0))
                .with_min_inner_size(dioxus::desktop::tao::dpi::LogicalSize::new(800.0, 500.0)),
        )
        .with_custom_head(format!(r#"<style>{MAIN_CSS}</style>"#));

    LaunchBuilder::desktop().with_cfg(window_cfg).launch(app::App);
}
