/// Floating control bar overlay.
///
/// This component renders as a CSS `position: fixed` bar at the bottom-centre
/// of the Dioxus webview.  It is always present in the DOM and shown/hidden by
/// toggling the `.fbar-visible` class.
///
/// Actions available in the bar:
///   • Start / Stop recording (same logic as the Dashboard page)
///   • Quick AI prompt — typed text is sent to the LLM and the response is
///     appended to the live transcript panel so the user can see it inline
///   • Status pill showing the current recording state

use dioxus::prelude::*;
use crate::app::{Db, Route};
use crate::config::AppConfig;
use crate::proactive::Suggestion;
use crate::recording::{LiveTranscript, RecordingStatus, StopRecording};

#[component]
pub fn FloatingBar() -> Element {
    let visible: Signal<bool> = use_context();
    let config: Signal<AppConfig> = use_context();
    let db: Signal<Option<Db>> = use_context();
    let recording_status: Signal<RecordingStatus> = use_context();
    let live_transcript: Signal<LiveTranscript> = use_context();
    let mut stop_handle: Signal<Option<StopRecording>> = use_context();

    // Agent suggestions (pills)
    let suggestions: Signal<Vec<Suggestion>> = use_context();
    let suggestion_prompt: Signal<Option<String>> = use_context();
    let mut continuous_voice_mode: Signal<bool> = use_context();
    let nav = use_navigator();

    let is_recording = matches!(*recording_status.read(), RecordingStatus::Recording { .. });
    let is_idle = matches!(*recording_status.read(), RecordingStatus::Idle);
    let is_error = matches!(*recording_status.read(), RecordingStatus::Error(_));

    let has_api_key = !config.read().deepgram_api_key.is_empty();

    // Quick AI prompt state
    let mut prompt_text = use_signal(String::new);
    let mut ai_response = use_signal(String::new);
    let ai_loading = use_signal(|| false);

    let bar_class = if *visible.read() {
        "fbar fbar-visible"
    } else {
        "fbar"
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
            let short = if device.len() > 18 { format!("{}…", &device[..18]) } else { device.clone() };
            format!("● {short}")
        }
        RecordingStatus::Error(_) => "Error".to_string(),
    };

    rsx! {
        div { class: "{bar_class}",
            // ── Status pill ───────────────────────────────────────────────────
            div { class: "{status_class}",
                span { "{status_label}" }
            }

            // ── Record / Stop ─────────────────────────────────────────────────
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
                                api_key,
                                diarize,
                                db_val,
                                cfg,
                                stop_rx,
                                &mut status,
                                &mut transcript,
                            )
                            .await;
                        });
                    },
                    "● Rec"
                }
            }

            button {
                class: if *continuous_voice_mode.read() { "fbar-btn fbar-btn-active" } else { "fbar-btn" },
                title: "Voice Chat Mode (Ctrl+Shift+V)\nOmi will auto-reply and restart recording.",
                onclick: move |_| {
                    let cur = *continuous_voice_mode.read();
                    continuous_voice_mode.set(!cur);
                },
                "Chat"
            }

            // ── Quick AI prompt ───────────────────────────────────────────────
            input {
                class: "fbar-input",
                r#type: "text",
                placeholder: "Ask Omi anything…",
                value: "{prompt_text}",
                oninput: move |e| prompt_text.set(e.value()),
                onkeypress: move |e| {
                    if e.key() == Key::Enter {
                        let text = prompt_text.read().trim().to_string();
                        if !text.is_empty() && !*ai_loading.read() {
                            let cfg = config.read().clone();
                            let mut resp = ai_response.clone();
                            let mut loading = ai_loading.clone();
                            let mut pt = prompt_text.clone();
                            spawn(async move {
                                loading.set(true);
                                pt.set(String::new());
                                let (api_key, url, model) = crate::llm::resolve_llm_endpoint(&cfg);
                                let result = crate::llm::complete(
                                    &api_key,
                                    &url,
                                    &model,
                                    vec![crate::llm::LlmMessage { role: "user".into(), content: text }],
                                    Some(300),
                                )
                                .await;
                                loading.set(false);
                                match result {
                                    Ok(answer) => resp.set(answer),
                                    Err(e) => resp.set(format!("Error: {e}")),
                                }
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

            // ── AI response popup ─────────────────────────────────────────────
            if !ai_response.read().is_empty() {
                div { class: "fbar-response",
                    div { class: "fbar-response-text", "{ai_response}" }
                    button {
                        class: "fbar-btn fbar-btn-close",
                        onclick: move |_| ai_response.set(String::new()),
                        "✕"
                    }
                }
            }

            // ── Proactive suggestion pills ─────────────────────────────────────
            if !suggestions.read().is_empty() {
                div { class: "fbar-pills",
                    for sug in suggestions.read().clone() {
                        {
                            let sug_id_action = sug.id.clone();
                            let sug_id_dismiss = sug.id.clone();
                            let sug_text = sug.text.clone();
                            let sug_action = sug.action_label.clone();
                            let sug_prompt = sug.agent_prompt.clone();
                            let mut sug_sig_action = suggestions.clone();
                            let mut sug_sig_dismiss = suggestions.clone();
                            let mut sp = suggestion_prompt.clone();
                            let nav2 = nav.clone();
                            rsx! {
                                div { class: "fbar-pill", key: "{sug_id_action}",
                                    span { class: "fbar-pill-text", title: "{sug_text}", "{sug_text}" }
                                    button {
                                        class: "fbar-pill-action",
                                        onclick: move |_| {
                                            if let Some(ref p) = sug_prompt {
                                                sp.set(Some(p.clone()));
                                            }
                                            nav2.push(Route::Agent {});
                                            let mut list = sug_sig_action.read().clone();
                                            list.retain(|x: &crate::proactive::Suggestion| x.id != sug_id_action);
                                            sug_sig_action.set(list);
                                        },
                                        "{sug_action}"
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
