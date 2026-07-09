use std::sync::Arc;

use dioxus::prelude::*;

use crate::app::Db;
use crate::config::AppConfig;
use crate::proactive::ProactiveEngine;
use crate::recording::{LiveTranscript, RecordingStatus, StopRecording};
use omi_db::schema::{Conversation, Memory};

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

    let mut stats_conversations = use_signal(|| 0i64);
    let mut stats_memories = use_signal(|| 0i64);
    let mut stats_screenshots = use_signal(|| 0i64);
    let mut stats_tasks = use_signal(|| 0i64);
    let mut stats_clipboard = use_signal(|| 0i64);
    let mut stats_apps = use_signal(|| 0usize);
    let mut recent_conversations = use_signal(Vec::<Conversation>::new);
    let mut recent_memories = use_signal(Vec::<Memory>::new);

    let mut refresh_tick = use_signal(|| 0u64);

    // Periodic refresh: bump tick every 10 seconds
    use_effect(move || {
        spawn(async move {
            loop {
                tokio::time::sleep(std::time::Duration::from_secs(10)).await;
                refresh_tick.set(refresh_tick() + 1);
            }
        });
    });

    use_effect(move || {
        let _tick = *refresh_tick.read();
        let db_snap = db.read().clone();
        if let Some(Db(d)) = db_snap {
            if let Ok(s) = d.get_today_stats() {
                stats_conversations.set(s.conversations);
                stats_memories.set(s.memories);
                stats_screenshots.set(s.screenshots);
                stats_tasks.set(s.tasks_completed);
                stats_clipboard.set(s.clipboard_items);
                stats_apps.set(s.apps_used.len());
            }
            if let Ok(convos) = d.list_conversations(5) {
                recent_conversations.set(convos);
            }
            if let Ok(mems) = d.list_memories(5) {
                recent_memories.set(mems);
            }
        }
    });

    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Dashboard" }
            p { class: if is_error { "page-subtitle text-error" } else { "page-subtitle" },
                "{status_text}"
            }

            // ── Today's Stats ────────────────────────────────────────────
            div { class: "stats-grid",
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_conversations}" }
                    span { class: "stat-label text-muted", "Conversations" }
                }
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_memories}" }
                    span { class: "stat-label text-muted", "Memories" }
                }
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_screenshots}" }
                    span { class: "stat-label text-muted", "Screenshots" }
                }
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_tasks}" }
                    span { class: "stat-label text-muted", "Tasks Done" }
                }
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_clipboard}" }
                    span { class: "stat-label text-muted", "Clipboard" }
                }
                div { class: "stat-card",
                    span { class: "stat-value", "{stats_apps}" }
                    span { class: "stat-label text-muted", "Apps Used" }
                }
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
                            let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
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
                        let segments = live_transcript.read().segments.clone();
                        if segments.is_empty() {
                            rsx! {
                                p { class: "text-muted transcript-empty",
                                    "Transcript will appear here when you start recording."
                                }
                            }
                        } else {
                            rsx! {
                                for seg in segments {
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

            // ── Recent Conversations ─────────────────────────────────────
            if !recent_conversations.read().is_empty() {
                div { class: "section",
                    h2 { class: "section-title", "Recent Conversations" }
                    div { class: "recent-list",
                        for convo in recent_conversations.read().iter() {
                            {
                                let title = convo.title.as_deref().unwrap_or("Untitled");
                                let time = convo.started_at.format("%b %d %H:%M").to_string();
                                let dur_min = (convo.duration_secs / 60.0) as i64;
                                let summary_short = convo.summary.as_deref().unwrap_or("").chars().take(120).collect::<String>();
                                rsx! {
                                    div { class: "recent-card",
                                        div { class: "recent-card-header",
                                            span { class: "recent-card-title", "{title}" }
                                            span { class: "text-muted", "{time} · {dur_min}m" }
                                        }
                                        if !summary_short.is_empty() {
                                            p { class: "recent-card-summary text-muted", "{summary_short}" }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── Recent Memories ──────────────────────────────────────────
            if !recent_memories.read().is_empty() {
                div { class: "section",
                    h2 { class: "section-title", "Recent Memories" }
                    div { class: "recent-list",
                        for mem in recent_memories.read().iter() {
                            {
                                let time = mem.created_at.format("%b %d %H:%M").to_string();
                                let cat = mem.category.as_deref().unwrap_or("general");
                                let preview = mem.content.chars().take(160).collect::<String>();
                                rsx! {
                                    div { class: "recent-card",
                                        div { class: "recent-card-header",
                                            span { class: "badge", "{cat}" }
                                            span { class: "text-muted", "{time}" }
                                        }
                                        p { class: "recent-card-summary", "{preview}" }
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
                        {
                            let n = live_transcript.read().segments.iter().filter(|s| s.is_final).count();
                            format!("{n}")
                        }
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
