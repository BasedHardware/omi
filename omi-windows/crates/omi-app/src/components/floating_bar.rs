use dioxus::prelude::*;

use crate::app::{Db, Route};
use crate::config::AppConfig;
use crate::proactive::Suggestion;
use crate::recording::{LiveTranscript, RecordingStatus, StopRecording};

#[derive(Clone, Debug)]
struct ChatEntry {
    role: String,
    content: String,
}

#[component]
pub fn FloatingBar() -> Element {
    let visible: Signal<bool> = use_context();
    let mut config: Signal<AppConfig> = use_context();
    let db: Signal<Option<Db>> = use_context();
    let recording_status: Signal<RecordingStatus> = use_context();
    let live_transcript: Signal<LiveTranscript> = use_context();
    let mut stop_handle: Signal<Option<StopRecording>> = use_context();
    let suggestions: Signal<Vec<Suggestion>> = use_context();
    let suggestion_prompt: Signal<Option<String>> = use_context();
    let mut continuous_voice_mode: Signal<bool> = use_context();
    let ptt_active: Signal<bool> = use_context();
    let voice_history: Signal<Vec<(String, String)>> = use_context();
    let nav = use_navigator();

    let is_recording = matches!(*recording_status.read(), RecordingStatus::Recording { .. });
    let is_idle = matches!(*recording_status.read(), RecordingStatus::Idle);
    let is_error = matches!(*recording_status.read(), RecordingStatus::Error(_));
    let has_api_key = !config.read().deepgram_api_key.is_empty();

    let mut prompt_text = use_signal(String::new);
    let mut chat_history = use_signal(Vec::<ChatEntry>::new);
    let ai_loading = use_signal(|| false);
    let mut is_expanded = use_signal(|| false);
    let mut dragging = use_signal(|| false);
    let mut drag_offset = use_signal(|| (0i32, 0i32));
    let mut expanded_pill = use_signal(|| Option::<String>::None);

    // Sync voice history into chat_history
    use_effect(move || {
        let vh = voice_history.read();
        if !vh.is_empty() {
            let mut entries = chat_history.read().clone();
            for (q, a) in vh.iter() {
                entries.push(ChatEntry { role: "user".into(), content: q.clone() });
                if !a.is_empty() {
                    entries.push(ChatEntry { role: "assistant".into(), content: a.clone() });
                }
            }
            if entries.len() > 40 {
                entries.drain(0..entries.len() - 40);
            }
            chat_history.set(entries);
        }
    });

    let bar_class = if !*visible.read() {
        "fbar"
    } else if *is_expanded.read() || !chat_history.read().is_empty() {
        "fbar fbar-visible fbar-expanded"
    } else {
        "fbar fbar-visible fbar-compact"
    };

    let status_class = if is_recording {
        "fbar-status fbar-status-recording"
    } else if is_error {
        "fbar-status fbar-status-error"
    } else {
        "fbar-status fbar-status-idle"
    };

    let status_label = match &*recording_status.read() {
        RecordingStatus::Idle => "Idle".to_string(),
        RecordingStatus::Recording { device } => {
            let short = if device.len() > 18 {
                format!("{}…", &device[..18])
            } else {
                device.clone()
            };
            format!("● {short}")
        }
        RecordingStatus::Error(_) => "Error".to_string(),
    };

    let position_style = {
        let cfg = config.read();
        if let Some((x, y)) = cfg.floating_bar_position {
            format!("left: {x}px; bottom: auto; top: {y}px; transform: none;")
        } else {
            String::new()
        }
    };

    rsx! {
        div {
            class: "{bar_class}",
            style: "{position_style}",
            onmouseenter: move |_| is_expanded.set(true),
            onmouseleave: move |_| {
                if prompt_text.read().is_empty() && !*ai_loading.read() {
                    is_expanded.set(false);
                }
            },
            onmousedown: move |e: MouseEvent| {
                let coords = e.client_coordinates();
                let cfg = config.read();
                let (cur_x, cur_y) = cfg.floating_bar_position.unwrap_or((0, 0));
                drag_offset.set((coords.x as i32 - cur_x, coords.y as i32 - cur_y));
                dragging.set(true);
            },
            onmousemove: move |e: MouseEvent| {
                if *dragging.read() {
                    let coords = e.client_coordinates();
                    let (ox, oy) = *drag_offset.read();
                    let new_x = coords.x as i32 - ox;
                    let new_y = coords.y as i32 - oy;
                    config.write().floating_bar_position = Some((new_x, new_y));
                }
            },
            onmouseup: move |_| {
                if *dragging.read() {
                    dragging.set(false);
                    let _ = config.read().save();
                }
            },

            // ── PTT indicator ────────────────────────────────────────────────
            if *ptt_active.read() {
                div { class: "fbar-ptt-indicator",
                    span { class: "fbar-ptt-dot" }
                    span { "Listening..." }
                }
            }

            // ── Status pill ──────────────────────────────────────────────────
            div { class: "{status_class}",
                span { "{status_label}" }
            }

            // ── Record / Stop ────────────────────────────────────────────────
            if is_recording {
                button {
                    class: "fbar-btn fbar-btn-stop",
                    title: "Stop recording (Ctrl+Shift+R)",
                    onclick: move |_| {
                        if let Some(handle) = stop_handle.write().take() {
                            handle.stop();
                        }
                    },
                    "■ Stop"
                }
            } else {
                button {
                    class: "fbar-btn fbar-btn-record",
                    disabled: (!is_idle && !is_error) || !has_api_key,
                    title: if has_api_key { "Start recording (Ctrl+Shift+R)" } else { "Set Deepgram API key in Settings" },
                    onclick: move |_| {
                        let api_key = config.read().deepgram_api_key.clone();
                        let diarize = config.read().diarize_speakers;
                        let cfg = config.read().clone();
                        let db_val = db.read().clone();
                        let mut status = recording_status.clone();
                        let mut transcript = live_transcript.clone();
                        let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
                        stop_handle.set(Some(StopRecording::new(stop_tx)));
                        spawn(async move {
                            crate::recording::start_recording(
                                api_key, diarize, db_val, cfg, stop_rx,
                                &mut status, &mut transcript,
                            )
                            .await;
                        });
                    },
                    "● Rec"
                }
            }

            button {
                class: if *continuous_voice_mode.read() { "fbar-btn fbar-btn-active" } else { "fbar-btn" },
                title: "Voice Chat Mode (Ctrl+Shift+V)",
                onclick: move |_| {
                    let cur = *continuous_voice_mode.read();
                    continuous_voice_mode.set(!cur);
                },
                "Chat"
            }

            // ── Quick AI prompt ──────────────────────────────────────────────
            input {
                class: "fbar-input",
                r#type: "text",
                placeholder: "Ask Omi anything…",
                value: "{prompt_text}",
                onfocus: move |_| is_expanded.set(true),
                oninput: move |e| prompt_text.set(e.value()),
                onkeydown: move |e| {
                    if e.key() == Key::Enter {
                        e.prevent_default();
                        let text = prompt_text.read().trim().to_string();
                        if !text.is_empty() && !*ai_loading.read() {
                            let cfg = config.read().clone();
                            let mut loading = ai_loading.clone();
                            let mut pt = prompt_text.clone();
                            let mut history = chat_history.clone();

                            // Push user entry immediately
                            let mut entries = history.read().clone();
                            entries.push(ChatEntry { role: "user".into(), content: text.clone() });
                            history.set(entries);
                            pt.set(String::new());

                            spawn(async move {
                                loading.set(true);

                                // Web search augmentation
                                let web_ctx = if cfg.web_search_enabled
                                    && !cfg.tavily_api_key.is_empty()
                                    && crate::web_search::needs_web_search(&text, &cfg).await
                                {
                                    match crate::web_search::search(&text, &cfg).await {
                                        Ok(resp) => Some(crate::web_search::format_search_context(&resp)),
                                        Err(e) => {
                                            tracing::warn!("[FBAR] Web search failed: {e:#}");
                                            None
                                        }
                                    }
                                } else {
                                    None
                                };

                                let mut messages = Vec::new();
                                if let Some(ref ctx) = web_ctx {
                                    messages.push(crate::llm::LlmMessage {
                                        role: "system".into(),
                                        content: format!("{ctx}\n\nUse the above web search results to answer accurately. Cite sources when possible."),
                                    });
                                }
                                messages.push(crate::llm::LlmMessage { role: "user".into(), content: text });

                                let (api_key, url, model) = crate::llm::resolve_llm_endpoint(&cfg);
                                let result = crate::llm::complete(
                                    &api_key, &url, &model,
                                    messages,
                                    Some(300),
                                )
                                .await;
                                loading.set(false);
                                let answer = match result {
                                    Ok(a) => a,
                                    Err(e) => format!("Error: {e}"),
                                };
                                let mut entries = history.read().clone();
                                entries.push(ChatEntry { role: "assistant".into(), content: answer });
                                if entries.len() > 40 {
                                    entries.drain(0..entries.len() - 40);
                                }
                                history.set(entries);
                            });
                        }
                    }
                },
            }

            if *ai_loading.read() {
                span { class: "fbar-ai-loading", "⏳" }
            }

            // ── Close button ─────────────────────────────────────────────────
            button {
                class: "fbar-btn fbar-btn-close",
                title: "Hide bar (Ctrl+Shift+Space)",
                onclick: move |_| {
                    let mut vis = visible.clone();
                    vis.set(false);
                },
                "✕"
            }

            // ── Chat history log ─────────────────────────────────────────────
            if !chat_history.read().is_empty() {
                div { class: "fbar-chat-log",
                    for entry in chat_history.read().iter() {
                        div {
                            class: if entry.role == "user" { "fbar-chat-msg fbar-chat-user" } else { "fbar-chat-msg fbar-chat-assistant" },
                            span { class: "fbar-chat-role",
                                if entry.role == "user" { "You" } else { "Omi" }
                            }
                            span { "{entry.content}" }
                        }
                    }
                    button {
                        class: "fbar-btn fbar-btn-clear",
                        onclick: move |_| chat_history.set(Vec::new()),
                        "Clear"
                    }
                }
            }

            // ── Proactive suggestion pills ───────────────────────────────────
            if !suggestions.read().is_empty() {
                div { class: "fbar-pills",
                    for sug in suggestions.read().clone() {
                        {
                            let sug_id = sug.id.clone();
                            let sug_id_expand = sug.id.clone();
                            let sug_id_dismiss = sug.id.clone();
                            let sug_text = sug.text.clone();
                            let is_detail_open = *expanded_pill.read() == Some(sug_id.clone());

                            if is_detail_open {
                                let sug_id_run = sug.id.clone();
                                let sug_id_close = sug.id.clone();
                                let sug_id_open = sug.id.clone();
                                let sug_prompt_run = sug.agent_prompt.clone();
                                let sug_prompt_open = sug.agent_prompt.clone();
                                let sug_detail_text = sug.text.clone();
                                let mut sug_sig_run = suggestions.clone();
                                let mut sug_sig_open = suggestions.clone();
                                let mut sp_run = suggestion_prompt.clone();
                                let mut sp_open = suggestion_prompt.clone();
                                let nav_run = nav.clone();
                                rsx! {
                                    div { class: "fbar-pill-detail", key: "{sug_id}",
                                        p { class: "fbar-pill-detail-text", "{sug_detail_text}" }
                                        div { class: "fbar-pill-detail-actions",
                                            button {
                                                class: "fbar-pill-action",
                                                onclick: move |_| {
                                                    if let Some(ref p) = sug_prompt_run {
                                                        sp_run.set(Some(p.clone()));
                                                    }
                                                    let prompt = sug_prompt_run.clone().unwrap_or_default();
                                                    if !prompt.is_empty() {
                                                        let cfg = config.read().clone();
                                                        let mut history = chat_history.clone();
                                                        let mut loading = ai_loading.clone();
                                                        let mut entries = history.read().clone();
                                                        entries.push(ChatEntry { role: "user".into(), content: prompt.clone() });
                                                        history.set(entries);
                                                        spawn(async move {
                                                            loading.set(true);
                                                            let (api_key, url, model) = crate::llm::resolve_llm_endpoint(&cfg);
                                                            let result = crate::llm::complete(
                                                                &api_key, &url, &model,
                                                                vec![crate::llm::LlmMessage { role: "user".into(), content: prompt }],
                                                                Some(300),
                                                            ).await;
                                                            loading.set(false);
                                                            let answer = match result {
                                                                Ok(a) => a,
                                                                Err(e) => format!("Error: {e}"),
                                                            };
                                                            let mut entries = history.read().clone();
                                                            entries.push(ChatEntry { role: "assistant".into(), content: answer });
                                                            if entries.len() > 40 { entries.drain(0..entries.len() - 40); }
                                                            history.set(entries);
                                                        });
                                                    }
                                                    let mut list = sug_sig_run.read().clone();
                                                    list.retain(|x: &crate::proactive::Suggestion| x.id != sug_id_run);
                                                    sug_sig_run.set(list);
                                                    expanded_pill.set(None);
                                                },
                                                "Run"
                                            }
                                            button {
                                                class: "fbar-btn fbar-btn-close",
                                                onclick: move |_| {
                                                    expanded_pill.set(None);
                                                },
                                                "Dismiss"
                                            }
                                            button {
                                                class: "fbar-pill-action",
                                                onclick: move |_| {
                                                    if let Some(ref p) = sug_prompt_open {
                                                        sp_open.set(Some(p.clone()));
                                                    }
                                                    nav_run.push(Route::Agent {});
                                                    let mut list = sug_sig_open.read().clone();
                                                    list.retain(|x: &crate::proactive::Suggestion| x.id != sug_id_open);
                                                    sug_sig_open.set(list);
                                                    expanded_pill.set(None);
                                                },
                                                "Open in Agent"
                                            }
                                        }
                                    }
                                }
                            } else {
                                let mut sug_sig_dismiss = suggestions.clone();
                                rsx! {
                                    div { class: "fbar-pill", key: "{sug_id_expand}",
                                        span {
                                            class: "fbar-pill-text",
                                            title: "{sug_text}",
                                            onclick: move |_| {
                                                expanded_pill.set(Some(sug_id_expand.clone()));
                                            },
                                            "{sug_text}"
                                        }
                                        button {
                                            class: "fbar-pill-dismiss",
                                            onclick: move |_| {
                                                let mut list = sug_sig_dismiss.read().clone();
                                                list.retain(|x: &crate::proactive::Suggestion| x.id != sug_id_dismiss);
                                                sug_sig_dismiss.set(list);
                                            },
                                            "✕"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
