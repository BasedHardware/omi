use std::process::ExitCode;

use omi_edge::config::Config;
use omi_edge::metrics::Metrics;
use tracing_subscriber::EnvFilter;

fn main() -> ExitCode {
    let filter = EnvFilter::try_from_env("EDGE_LOG").unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(filter)
        .with_current_span(false)
        .init();

    let cfg = match Config::from_env() {
        Ok(cfg) => cfg,
        Err(err) => {
            tracing::error!(error = %err, "invalid configuration");
            return ExitCode::from(2);
        }
    };

    match &cfg.vad_model_path {
        Some(path) => {
            if let Err(err) = omi_edge::silero::init(path) {
                tracing::error!(error = %err, "failed to load the VAD model");
                return ExitCode::from(2);
            }
        }
        None => tracing::info!("EDGE_VAD_MODEL_PATH unset; shadow ingest disabled"),
    }

    let mut builder = tokio::runtime::Builder::new_multi_thread();
    builder.enable_all();
    if let Some(n) = cfg.worker_threads {
        builder.worker_threads(n);
    }
    let rt = match builder.build() {
        Ok(rt) => rt,
        Err(err) => {
            tracing::error!(error = %err, "failed to build runtime");
            return ExitCode::from(1);
        }
    };

    rt.block_on(async move {
        let metrics = Metrics::new(&cfg.release_sha);
        let edge = match omi_edge::server::start(cfg, metrics).await {
            Ok(edge) => edge,
            Err(err) => {
                tracing::error!(error = %err, "failed to bind");
                return ExitCode::from(1);
            }
        };
        tracing::info!(addr = %edge.local_addr(), "listen-edge serving");
        wait_for_shutdown_signal().await;
        tracing::info!("shutdown signal received; draining");
        edge.drain().await;
        tracing::info!("drain complete");
        ExitCode::SUCCESS
    })
}

async fn wait_for_shutdown_signal() {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{signal, SignalKind};
        let mut term = match signal(SignalKind::terminate()) {
            Ok(s) => s,
            Err(_) => {
                let _ = tokio::signal::ctrl_c().await;
                return;
            }
        };
        tokio::select! {
            _ = term.recv() => {}
            _ = tokio::signal::ctrl_c() => {}
        }
    }
    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }
}
