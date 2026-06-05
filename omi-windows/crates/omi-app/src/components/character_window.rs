use dioxus::prelude::*;
use dioxus::prelude::document::eval;
use std::time::Duration;
use crate::proactive::Suggestion;
use crate::recording::RecordingStatus;
use crate::agent_runtime::{AgentEvent, AgentRuntime};
use crate::config::AppConfig;

pub const CHARACTER_CSS: &str = r#"
body {
    background: transparent !important;
    overflow: hidden;
    margin: 0;
    padding: 0;
    user-select: none;
    font-family: 'Segoe UI', sans-serif;
}

.pixel-character-container {
    width: 180px;
    height: 180px;
    display: flex;
    justify-content: center;
    align-items: center;
    background: transparent;
    cursor: grab;
    -webkit-app-region: drag;
    position: relative;
}

.character-non-drag {
    -webkit-app-region: no-drag;
}

/* Animations */
@keyframes bounce {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-4px); }
}

@keyframes blink {
    0%, 90%, 100% { transform: scaleY(1); }
    95% { transform: scaleY(0.1); }
}

@keyframes glow-antenna {
    0%, 100% { fill: #6c5ce7; filter: drop-shadow(0 0 1px #6c5ce7); }
    50% { fill: #a29bfe; filter: drop-shadow(0 0 5px #a29bfe); }
}

@keyframes eye-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

@keyframes mouth-speak {
    0%, 100% { transform: scaleY(1); }
    50% { transform: scaleY(3.0); }
}

.animated-head {
    animation: bounce 3s ease-in-out infinite;
    transform-origin: bottom center;
}

.antenna-bulb {
    animation: glow-antenna 1.5s ease-in-out infinite;
}

.eye-left, .eye-right {
    transform-origin: center;
}

.pixel-avatar {
    width: 100px;
    height: 100px;
}

.pixel-avatar.state-idle .eye-left, 
.pixel-avatar.state-idle .eye-right {
    animation: blink 4s infinite;
}

.pixel-avatar.state-listening .eye-left, 
.pixel-avatar.state-listening .eye-right {
    fill: #00cec9 !important;
    animation: eye-pulse 0.6s ease-in-out infinite;
}

.pixel-avatar.state-listening .antenna-bulb {
    fill: #00cec9;
}

.pixel-avatar.state-thinking .eye-left, 
.pixel-avatar.state-thinking .eye-right {
    fill: #fdcb6e !important;
    animation: eye-pulse 0.3s ease-in-out infinite;
}

.pixel-avatar.state-thinking .antenna-bulb {
    fill: #fdcb6e;
}

.pixel-avatar.state-speaking .eye-left, 
.pixel-avatar.state-speaking .eye-right {
    fill: #e84393 !important;
}

.pixel-avatar.state-speaking .mouth {
    animation: mouth-speak 0.12s ease-in-out infinite;
    transform-origin: 15px 16px;
    stroke: #e84393 !important;
}

.pixel-avatar.state-speaking .antenna-bulb {
    fill: #e84393;
}

/* Speech bubble styling */
.speech-bubble {
    position: absolute;
    bottom: 150px;
    left: 10px;
    width: 160px;
    background: #1e1e2e;
    border: 2px solid #6c5ce7;
    border-radius: 8px;
    padding: 8px;
    color: #cdd6f4;
    font-size: 11px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    z-index: 1000;
    animation: pop-in 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.speech-bubble::after {
    content: '';
    position: absolute;
    bottom: -8px;
    left: 80px;
    border-width: 8px 8px 0;
    border-style: solid;
    border-color: #6c5ce7 transparent;
    display: block;
    width: 0;
}

.speech-bubble-inner {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.bubble-text {
    line-height: 1.3;
    font-weight: 500;
}

.bubble-actions {
    display: flex;
    justify-content: flex-end;
    gap: 4px;
}

.action-btn {
    background: #6c5ce7;
    border: none;
    color: white;
    padding: 3px 6px;
    border-radius: 4px;
    font-size: 9px;
    font-weight: bold;
    cursor: pointer;
}

.action-btn:hover {
    background: #7c6ef7;
}

.dismiss-btn {
    background: #313244;
    border: none;
    color: #a6adc8;
    padding: 3px 6px;
    border-radius: 4px;
    font-size: 9px;
    cursor: pointer;
}

.dismiss-btn:hover {
    background: #45475a;
    color: white;
}

@keyframes pop-in {
    from { transform: scale(0.8); opacity: 0; }
    to { transform: scale(1); opacity: 1; }
}
"#;

#[derive(Props, Clone, PartialEq)]
pub struct CharacterOverlayProps {
    pub suggestions: Signal<Vec<Suggestion>>,
    pub recording_status: Signal<RecordingStatus>,
    pub live_transcript: Signal<crate::recording::LiveTranscript>,
    pub db: Signal<Option<crate::app::Db>>,
    pub runtime: Signal<AgentRuntime>,
    pub config: Signal<AppConfig>,
    pub suggestion_prompt: Signal<Option<String>>,
}

#[component]
pub fn CharacterOverlay(props: CharacterOverlayProps) -> Element {
    let mut avatar_state = use_signal(|| "state-idle".to_string());
    let mut active_suggestion: Signal<Option<Suggestion>> = use_signal(|| None);
    let mut dismiss_trigger = use_signal(|| 0);
    let mut stop_handle: Signal<Option<crate::recording::StopRecording>> = use_context();

    // Subscribe to recording status signals to change character visual state
    use_effect(move || {
        let rec = props.recording_status.read();
        match *rec {
            RecordingStatus::Recording { .. } => {
                avatar_state.set("state-listening".to_string());
            }
            _ => {
                avatar_state.set("state-idle".to_string());
            }
        }
    });

    // Subscribe to LLM agent events for thinking and speaking states
    use_hook(move || {
        let rt = props.runtime.clone();
        let cfg = props.config.clone();
        let mut av_state = avatar_state.clone();
        
        spawn(async move {
            let mut rx = rt.read().subscribe();
            loop {
                match rx.recv().await {
                    Ok(AgentEvent::Init { .. }) => {
                        av_state.set("state-thinking".to_string());
                    }
                    Ok(AgentEvent::Result { text, .. }) => {
                        av_state.set("state-idle".to_string());
                        
                        // Speak response via JavaScript fetch + Audio API
                        let url = cfg.read().python_backend_url.clone();
                        let token = cfg.read().firebase_id_token.clone();
                        
                        if !text.is_empty() && !token.is_empty() {
                            let js_speak = format!(r#"
                                if (window.speak) {{
                                    window.speak({:?}, {:?}, {:?});
                                }}
                            "#, text, url, token);
                            
                            eval(&js_speak);
                        }
                    }
                    Ok(AgentEvent::Error { .. }) => {
                        av_state.set("state-idle".to_string());
                    }
                    Err(_) => {
                        tokio::time::sleep(Duration::from_millis(200)).await;
                        rx = rt.read().subscribe();
                    }
                    _ => {}
                }
            }
        });
    });

    // Handle suggestion notification display with a 10-second timeout
    use_effect(move || {
        let list = props.suggestions.read();
        if let Some(sug) = list.first() {
            active_suggestion.set(Some(sug.clone()));
            
            // Increment dismiss trigger to cancel previous timer
            let current_trigger = *dismiss_trigger.peek() + 1;
            dismiss_trigger.set(current_trigger);
            
            // Set 10-second timeout to auto-dismiss suggestion bubble
            let mut active_sig = active_suggestion.clone();
            let mut sug_list = props.suggestions.clone();
            let target_sug_id = sug.id.clone();
            
            spawn(async move {
                tokio::time::sleep(Duration::from_secs(10)).await;
                if *dismiss_trigger.peek() == current_trigger {
                    active_sig.set(None);
                    // Also remove it from the list
                    let mut list = sug_list.read().clone();
                    list.retain(|x| x.id != target_sug_id);
                    sug_list.set(list);
                }
            });
        } else {
            active_suggestion.set(None);
        }
    });

    // Injected JavaScript code to implement speak() and voice control
    use_effect(move || {
        let js_init = r#"
            window.speak = async function(text, backendUrl, token) {
                const avatar = document.getElementById("robot-avatar");
                if (avatar) avatar.setAttribute("class", "pixel-avatar state-thinking");
                
                try {
                    const response = await fetch(`${backendUrl}/v2/tts/synthesize`, {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${token}`,
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            voice_id: "21m00Tcm4TlvDq8ikWAM",
                            text: text
                        })
                    });
                    if (!response.ok) throw new Error("TTS failed");
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    const audio = new Audio(url);
                    
                    if (avatar) avatar.setAttribute("class", "pixel-avatar state-speaking");
                    
                    audio.onended = () => {
                        if (avatar) avatar.setAttribute("class", "pixel-avatar state-idle");
                    };
                    
                    await audio.play();
                } catch (e) {
                    console.error("Speech synthesis failed", e);
                    if (avatar) avatar.setAttribute("class", "pixel-avatar state-idle");
                }
            };
        "#;
        eval(js_init);
    });

    rsx! {
        style { "{CHARACTER_CSS}" }
        
        div { class: "pixel-character-container",
            // ── Speech bubble suggestion popup ────────────────────────────────
            if let Some(ref sug) = *active_suggestion.read() {
                {
                    let sug_id = sug.id.clone();
                    let sug_text = sug.text.clone();
                    let sug_action = sug.action_label.clone();
                    let sug_prompt = sug.agent_prompt.clone();
                    let mut sug_list = props.suggestions.clone();
                    let mut sp = props.suggestion_prompt.clone();
                    let mut active_sig = active_suggestion.clone();
                    
                    let sug_id_action = sug_id.clone();
                    let sug_id_dismiss = sug_id.clone();
                    
                    rsx! {
                        div { class: "speech-bubble character-non-drag",
                            div { class: "speech-bubble-inner",
                                div { class: "bubble-text", "{sug_text}" }
                                div { class: "bubble-actions",
                                    button {
                                        class: "action-btn",
                                        onclick: move |_| {
                                            if let Some(ref p) = sug_prompt {
                                                sp.set(Some(p.clone()));
                                            }
                                            // Clear suggestion on action click
                                            active_sig.set(None);
                                            let mut list = sug_list.read().clone();
                                            list.retain(|x| x.id != sug_id_action);
                                            sug_list.set(list);
                                        },
                                        "{sug_action}"
                                    }
                                    button {
                                        class: "dismiss-btn",
                                        onclick: move |_| {
                                            active_sig.set(None);
                                            let mut list = sug_list.read().clone();
                                            list.retain(|x| x.id != sug_id_dismiss);
                                            sug_list.set(list);
                                        },
                                        "✕"
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── 2D Pixel-Art SVG Avatar ───────────────────────────────────────
            div {
                class: "character-non-drag",
                // Toggle recording on click
                onclick: move |_| {
                    let is_recording = matches!(*props.recording_status.peek(), RecordingStatus::Recording { .. });
                    if is_recording {
                        if let Some(handle) = stop_handle.write().take() {
                            handle.stop();
                        }
                    } else {
                        let api_key = props.config.read().deepgram_api_key.clone();
                        let diarize = props.config.read().diarize_speakers;
                        let cfg = props.config.read().clone();
                        let db_val = props.db.read().clone();
                        let mut status = props.recording_status.clone();
                        let mut transcript = props.live_transcript.clone();
                        let mut stop_h = stop_handle.clone();
                        let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
                        stop_h.set(Some(crate::recording::StopRecording::new(stop_tx)));
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
                    }
                },
                
                svg {
                    id: "robot-avatar",
                    class: "pixel-avatar {avatar_state}",
                    view_box: "0 0 30 30",
                    
                    // Head Outline & Body
                    rect { x: "5", y: "5", width: "20", height: "20", fill: "#1e1e2e", stroke: "#6c5ce7", stroke_width: "1.5", rx: "2" }
                    
                    // Face plate screen
                    rect { x: "7", y: "7", width: "16", height: "11", fill: "#11111b", rx: "1" }
                    
                    // Antenna
                    rect { x: "14", y: "2", width: "2", height: "3", fill: "#6c5ce7" }
                    circle { class: "antenna-bulb", cx: "15", cy: "1", r: "1.5", fill: "#6c5ce7" }

                    // Eyes
                    rect { class: "eye-left", x: "9", y: "10", width: "3", height: "3", fill: "#a6e3a1" }
                    rect { class: "eye-right", x: "18", y: "10", width: "3", height: "3", fill: "#a6e3a1" }
                    
                    // Mouth
                    line { class: "mouth", x1: "11", y1: "15", x2: "19", y2: "15", stroke: "#a6e3a1", stroke_width: "1.5" }
                }
            }
        }
    }
}
