use std::sync::Arc;

use dioxus::prelude::*;

use crate::app::Db;
use crate::config::AppConfig;
use crate::proactive::ProactiveEngine;
use crate::recording::{LiveTranscript, RecordingStatus, StopRecording};

#[component]
pub fn DashboardPage() -> Element {
    let config: Signal<AppConfig> = use_context();
    let db: Signal<Option<Db>> = use_context();
    let recording_status: Signal<RecordingStatus> = use_context();
    let live_transcript: Signal<LiveTranscript> = use_context();
    let mut stop_handle: Signal<Option<StopRecording>> = use_context();
    let proactive_engine: Signal<Arc<ProactiveEngine>> = use_context();

    let is_recording = matches!(*recording_status.read(), RecordingStatus::Recording { .. });
    let is_idle = matches!(*recording_status.read(), RecordingStatus::Idle);
    let is_error = matches!(*recording_status.read(), RecordingStatus::Error(_));

    let status_text = match &*recording_status.read() {
        RecordingStatus::Idle => "Ready to record".to_string(),
        RecordingStatus::Recording { device } => format!("Recording from: {device}"),
        RecordingStatus::Error(e) => format!("Error: {e}"),
    };

    let has_api_key = !config.read().deepgram_api_key.is_empty();

    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Dashboard" }
            p { class: if is_error { "page-subtitle text-error" } else { "page-subtitle" },
                "{status_text}"
            }

            // Record controls
            div { class: "record-controls",
                if !has_api_key {
                    p { class: "text-warning", "Set your Deepgram API key in Settings to enable transcription." }
                }

                if is_recording {
                    button {
                        class: "btn btn-record btn-recording",
                        onclick: move |_| {
                            if let Some(handle) = stop_handle.write().take() {
                                handle.stop();
                            }
                        },
                        span { class: "record-dot recording" }
                        " Stop Recording"
                    }
                    button {
                        class: "btn btn-secondary",
                        onclick: move |_| {
                            // Restart: stop current recording then start again after a short delay
                            if let Some(handle) = stop_handle.write().take() {
                                handle.stop();
                            }
                            let api_key = config.read().deepgram_api_key.clone();
                            let diarize = config.read().diarize_speakers;
                            let cfg = config.read().clone();
                            let db_val = db.read().clone();
                            let mut status = recording_status.clone();
                            let mut transcript = live_transcript.clone();
                            let mut stop_handle_clone = stop_handle.clone();
                            let pe_restart = Some(proactive_engine.read().clone());
                            spawn(async move {
                                // small pause to allow resources to release
                                tokio::time::sleep(std::time::Duration::from_millis(400)).await;
                                let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
                                stop_handle_clone.set(Some(crate::recording::StopRecording::new(stop_tx)));
                                crate::recording::start_recording_with_proactive(
                                    api_key, diarize, db_val, cfg,
                                    stop_rx, &mut status, &mut transcript, pe_restart,
                                ).await;
                            });
                        },
                        " Restart"
                    }
                } else {
                    button {
                        class: "btn btn-record",
                        disabled: !is_idle && !is_error,
                        onclick: move |_| {
                            let api_key = config.read().deepgram_api_key.clone();
                            let diarize = config.read().diarize_speakers;
                            let cfg = config.read().clone();
                            let db_val = db.read().clone();
                            let mut status = recording_status.clone();
                            let mut transcript = live_transcript.clone();
                            // Create stop channel here so the sender is available immediately
                            let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
                            // Store stop handle in global app context so it survives tab changes
                            stop_handle.set(Some(crate::recording::StopRecording::new(stop_tx)));
                            let pe_start = Some(proactive_engine.read().clone());
                            spawn(async move {
                                crate::recording::start_recording_with_proactive(
                                    api_key, diarize, db_val, cfg,
                                    stop_rx, &mut status, &mut transcript, pe_start,
                                ).await;
                            });
                        },
                        span { class: "record-dot" }
                        if is_error { " Retry" } else { " Start Recording" }
                    }
                }
            }

            // Live transcript
            div { class: "transcript-panel",
                h2 { "Live Transcript" }
                div { class: "transcript-content",
                    {
                        let segments = &live_transcript.read().segments;
                        if segments.is_empty() {
                            rsx! {
                                p { class: "text-muted transcript-empty",
                                    "Transcript will appear here when you start recording."
                                }
                            }
                        } else {
                            rsx! {
                                for seg in segments.iter() {
                                    div {
                                        class: if seg.is_final { "transcript-segment final" } else { "transcript-segment interim" },
                                        span { class: "speaker-badge", "S{seg.speaker}" }
                                        span { class: "segment-text", "{seg.text}" }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Stats cards
            div { class: "card-grid",
                div { class: "card",
                    h3 { "Segments" }
                    p { class: "card-stat",
                        "{live_transcript.read().segments.iter().filter(|s| s.is_final).count()}"
                    }
                    p { class: "text-muted", "finalized" }
                }
                div { class: "card",
                    h3 { "Speakers" }
                    p { class: "card-stat",
                        {
                            let speakers: std::collections::HashSet<i32> = live_transcript
                                .read()
                                .segments
                                .iter()
                                .map(|s| s.speaker)
                                .collect();
                            format!("{}", speakers.len())
                        }
                    }
                    p { class: "text-muted", "detected" }
                }
            }
        }
    }
}
