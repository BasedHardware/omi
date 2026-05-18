use dioxus::prelude::*;

mod app;
mod auth;
mod components;
mod config;
mod hooks;
mod pages;
mod sidecar;

pub const MAIN_CSS: &str = include_str!("assets/main.css");

fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "omi_app=info".into()),
        )
        .init();

    tracing::info!("Starting Omi Windows");

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
