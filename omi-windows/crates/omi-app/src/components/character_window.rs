use dioxus::prelude::*;
use dioxus::prelude::document::eval;
use std::time::Duration;
use crate::proactive::Suggestion;
use crate::recording::RecordingStatus;
use crate::agent_runtime::AgentEvent;
use crate::config::AppConfig;

pub const CHARACTER_CSS: &str = r#"
html, body {
    background: transparent !important;
    background-color: transparent !important;
}

body {
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

.eye-left, .eye-right {
    transform-origin: center;
}

.mouth {
    display: none;
    transform-origin: center;
}

.pixel-avatar {
    width: 100px;
    height: 100px;
    animation: bounce 3s ease-in-out infinite;
    transform-origin: bottom center;
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

.pixel-avatar.state-thinking .eye-left, 
.pixel-avatar.state-thinking .eye-right {
    fill: #fdcb6e !important;
    animation: eye-pulse 0.3s ease-in-out infinite;
}

.pixel-avatar.state-speaking .eye-left, 
.pixel-avatar.state-speaking .eye-right {
    fill: #ffffff !important;
}

.pixel-avatar.state-speaking .mouth {
    display: block;
    animation: mouth-speak 0.12s ease-in-out infinite;
    fill: #ffffff !important;
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

#[derive(Clone, Debug)]
pub enum CharacterAction {
    ToggleRecord,
    SuggestionAction(String),
    SpeechFinished,
}

#[derive(Clone)]
pub struct CharacterOverlayProps {
    pub suggestions_rx: tokio::sync::watch::Receiver<Vec<Suggestion>>,
    pub recording_status_rx: tokio::sync::watch::Receiver<RecordingStatus>,
    pub config_rx: tokio::sync::watch::Receiver<AppConfig>,
    pub agent_event_tx: tokio::sync::broadcast::Sender<AgentEvent>,
    pub character_action_tx: tokio::sync::mpsc::UnboundedSender<CharacterAction>,
}

impl PartialEq for CharacterOverlayProps {
    fn eq(&self, _other: &Self) -> bool {
        true
    }
}

#[component]
pub fn CharacterOverlay(props: CharacterOverlayProps) -> Element {
    let mut avatar_state = use_signal(|| "state-idle".to_string());
    let mut active_suggestion: Signal<Option<Suggestion>> = use_signal(|| None);
    let mut dismiss_trigger = use_signal(|| 0);

    // Local signals to store state received from channels
    let recording_status = use_signal(|| RecordingStatus::Idle);
    let mut suggestions = use_signal(Vec::<Suggestion>::new);
    let config = use_signal(|| AppConfig::load());

    // 1. Synchronize recording_status from watch channel
    use_hook(move || {
        let mut rx = props.recording_status_rx.clone();
        let mut sig = recording_status.clone();
        spawn(async move {
            let val = rx.borrow().clone();
            sig.set(val);
            while rx.changed().await.is_ok() {
                let val = rx.borrow().clone();
                sig.set(val);
            }
        });
    });

    // 2. Synchronize suggestions from watch channel
    use_hook(move || {
        let mut rx = props.suggestions_rx.clone();
        let mut sig = suggestions.clone();
        spawn(async move {
            let val = rx.borrow().clone();
            sig.set(val);
            while rx.changed().await.is_ok() {
                let val = rx.borrow().clone();
                sig.set(val);
            }
        });
    });

    // 3. Synchronize config from watch channel
    use_hook(move || {
        let mut rx = props.config_rx.clone();
        let mut sig = config.clone();
        spawn(async move {
            let val = rx.borrow().clone();
            sig.set(val);
            while rx.changed().await.is_ok() {
                let val = rx.borrow().clone();
                sig.set(val);
            }
        });
    });

    // Subscribe to recording status signals to change character visual state
    use_effect(move || {
        let rec = recording_status.read();
        match *rec {
            RecordingStatus::Recording { .. } => {
                avatar_state.set("state-listening".to_string());
            }
            _ => {
                avatar_state.set("state-idle".to_string());
            }
        }
    });

    let agent_event_tx_for_hook = props.agent_event_tx.clone();
    let character_action_tx_for_hook = props.character_action_tx.clone();

    // Subscribe to LLM agent events for thinking and speaking states
    use_hook(move || {
        let agent_event_tx = agent_event_tx_for_hook.clone();
        let action_tx_inner = character_action_tx_for_hook.clone();
        let cfg = config.clone();
        let mut av_state = avatar_state.clone();
        
        spawn(async move {
            let mut rx = agent_event_tx.subscribe();
            loop {
                match rx.recv().await {
                    Ok(AgentEvent::Init { .. }) => {
                        av_state.set("state-thinking".to_string());
                    }
                    Ok(AgentEvent::Result { text, from_voice, .. }) => {
                        av_state.set("state-idle".to_string());

                        if text.is_empty() {
                            continue;
                        }

                        if !from_voice {
                            let _ = action_tx_inner.send(CharacterAction::SpeechFinished);
                            continue;
                        }

                        let current_cfg = cfg.read().clone();
                        let text_for_tts = text.clone();
                        let action_tx = action_tx_inner.clone();

                        // ── Tier 1: OpenAI TTS (no Firebase required) ────────────────
                        if crate::tts_engine::is_available(&current_cfg) {
                            av_state.set("state-speaking".to_string());
                            let cfg_tts = current_cfg.clone();
                            let mut av_clone = av_state.clone();
                            let action_tx2 = action_tx.clone();
                            spawn(async move {
                                let result = crate::tts_engine::speak_text(&text_for_tts, &cfg_tts).await;
                                av_clone.set("state-idle".to_string());
                                if result.is_err() {
                                    tracing::warn!("[TTS] OpenAI TTS failed: {:?}", result);
                                }
                                let _ = action_tx2.send(CharacterAction::SpeechFinished);
                            });
                        // ── Tier 2: Firebase-gated ElevenLabs JS path ────────────────
                        } else if !current_cfg.firebase_id_token.is_empty() {
                            let url = current_cfg.python_backend_url.clone();
                            let token = current_cfg.firebase_id_token.clone();
                            let js_speak = format!(r#"
                                (async () => {{
                                    if (window.speak) {{
                                        await window.speak({:?}, {:?}, {:?});
                                    }}
                                    dioxus.send("speech_ended");
                                }})();
                            "#, text, url, token);

                            let mut eval_handle = eval(&js_speak);
                            spawn(async move {
                                while let Ok(msg) = eval_handle.recv::<serde_json::Value>().await {
                                    if msg.as_str() == Some("speech_ended") {
                                        let _ = action_tx.send(CharacterAction::SpeechFinished);
                                        break;
                                    }
                                }
                            });
                        // ── Tier 3: No TTS available — show text bubble only ─────────
                        } else {
                            // Show reply as a suggestion bubble (silent mode)
                            let short_text = if text.len() > 120 {
                                format!("{}…", &text[..117])
                            } else {
                                text.clone()
                            };
                            let reply_sug = Suggestion {
                                id: uuid::Uuid::new_v4().to_string(),
                                text: short_text,
                                action_label: "Read".to_string(),
                                agent_prompt: None,
                                priority: 90,
                                created_at: std::time::Instant::now(),
                                ttl: std::time::Duration::from_secs(20),
                            };
                            let mut list = suggestions.read().clone();
                            list.insert(0, reply_sug);
                            suggestions.set(list);
                            let _ = action_tx.send(CharacterAction::SpeechFinished);
                        }
                    }
                    Ok(AgentEvent::HitlRequest { thread_id, message }) => {
                        av_state.set("state-idle".to_string());
                        let hitl_sug = Suggestion {
                            id: uuid::Uuid::new_v4().to_string(),
                            text: message.clone(),
                            action_label: "Confirm".to_string(),
                            agent_prompt: Some(format!("HITL_CONFIRM:{}", thread_id)),
                            priority: 100, // Highest priority
                            created_at: std::time::Instant::now(),
                            ttl: std::time::Duration::from_secs(60), // Wait longer for user
                        };
                        let mut list = suggestions.read().clone();
                        list.insert(0, hitl_sug);
                        suggestions.set(list);
                    }

                    Ok(AgentEvent::Error { .. }) => {
                        av_state.set("state-idle".to_string());
                    }
                    Err(_) => {
                        tokio::time::sleep(Duration::from_millis(200)).await;
                        rx = agent_event_tx.subscribe();
                    }
                    _ => {}
                }
            }
        });
    });

    // Handle suggestion notification display with a 10-second timeout
    use_effect(move || {
        let list = suggestions.read();
        if let Some(sug) = list.first() {
            active_suggestion.set(Some(sug.clone()));
            
            // Increment dismiss trigger to cancel previous timer
            let current_trigger = *dismiss_trigger.peek() + 1;
            dismiss_trigger.set(current_trigger);
            
            // Set 10-second timeout to auto-dismiss suggestion bubble
            let mut active_sig = active_suggestion.clone();
            let mut sug_list = suggestions.clone();
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
            window.cancelSpeech = function() {
                if (window.current_audio) {
                    window.current_audio.pause();
                    window.current_audio = null;
                }
                const avatar = document.getElementById("robot-avatar");
                if (avatar) avatar.setAttribute("class", "pixel-avatar state-idle");
            };
            window.speak = function(text, backendUrl, token) {
                return new Promise(async (resolve) => {
                    window.cancelSpeech();
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
                        window.current_audio = audio;
                        
                        if (avatar) avatar.setAttribute("class", "pixel-avatar state-speaking");
                        
                        audio.onended = () => {
                            window.current_audio = null;
                            if (avatar) avatar.setAttribute("class", "pixel-avatar state-idle");
                            resolve();
                        };
                        audio.onerror = () => {
                            window.current_audio = null;
                            if (avatar) avatar.setAttribute("class", "pixel-avatar state-idle");
                            resolve();
                        };
                        
                        await audio.play();
                    } catch (e) {
                        console.error("Speech synthesis failed", e);
                        window.current_audio = null;
                        if (avatar) avatar.setAttribute("class", "pixel-avatar state-idle");
                        resolve();
                    }
                });
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
                    let mut sug_list = suggestions.clone();
                    let mut active_sig = active_suggestion.clone();
                    
                    let sug_id_action = sug_id.clone();
                    let sug_id_dismiss = sug_id.clone();
                    
                    let tx_action = props.character_action_tx.clone();
                    let tx_dismiss = props.character_action_tx.clone();
                    
                    let sug_prompt_action = sug_prompt.clone();
                    let sug_prompt_dismiss = sug_prompt.clone();
                    
                    rsx! {
                        div { class: "speech-bubble character-non-drag",
                            div { class: "speech-bubble-inner",
                                div { class: "bubble-text", "{sug_text}" }
                                div { class: "bubble-actions",
                                    button {
                                        class: "action-btn",
                                        onclick: move |_| {
                                            if let Some(ref p) = sug_prompt_action {
                                                let _ = tx_action.send(CharacterAction::SuggestionAction(p.clone()));
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
                                            if let Some(ref p) = sug_prompt_dismiss {
                                                if p.starts_with("HITL_CONFIRM:") {
                                                    let thread_id = p.replace("HITL_CONFIRM:", "");
                                                    let _ = tx_dismiss.send(CharacterAction::SuggestionAction(format!("HITL_REJECT:{}", thread_id)));
                                                }
                                            }
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
                    let _ = props.character_action_tx.send(CharacterAction::ToggleRecord);
                },
                
                svg {
                    id: "robot-avatar",
                    class: "pixel-avatar {avatar_state}",
                    view_box: "0 0 30 30",
                    
                    // Invader Orange Body
                    rect { x: "7", y: "10", width: "16", height: "9", fill: "#e06c53" }
                    
                    // Side arms/ears
                    rect { x: "2", y: "13", width: "5", height: "2", fill: "#e06c53" }
                    rect { x: "23", y: "13", width: "5", height: "2", fill: "#e06c53" }
                    
                    // Legs (four vertical feet)
                    rect { x: "9", y: "19", width: "1.5", height: "4", fill: "#e06c53" }
                    rect { x: "12", y: "19", width: "1.5", height: "4", fill: "#e06c53" }
                    rect { x: "16.5", y: "19", width: "1.5", height: "4", fill: "#e06c53" }
                    rect { x: "19.5", y: "19", width: "1.5", height: "4", fill: "#e06c53" }
                    
                    // Eyes (vertical slits)
                    rect { class: "eye-left", x: "10.5", y: "12", width: "2", height: "4", fill: "#ffffff" }
                    rect { class: "eye-right", x: "17.5", y: "12", width: "2", height: "4", fill: "#ffffff" }
                    
                    // Mouth (appears only when speaking)
                    rect { class: "mouth", x: "13", y: "16", width: "4", height: "1.5", fill: "#ffffff" }
                }
            }
        }
    }
}
