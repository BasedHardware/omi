use dioxus::prelude::*;

mod agent_runtime;
mod app;
mod auth;
mod capture;
mod components;
mod config;
mod hooks;
mod hotkey;
mod llm;
mod pages;
mod proactive;
mod recording;
mod sidecar;
mod tray;

pub const MAIN_CSS: &str = include_str!("assets/main.css");

fn main() {
    // Load .env from working directory (omi-windows/.env)
    dotenvy::dotenv().ok();

    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".into()),
        )
        .with_target(false)
        .init();

    tracing::info!("Starting Omi Windows");

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
