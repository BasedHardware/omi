use dioxus::prelude::*;

use crate::agent_runtime::AgentRuntime;
use crate::auth::AuthStatus;
use crate::config::AppConfig;
use crate::sidecar::BackendStatus;

#[component]
pub fn SettingsPage() -> Element {
    let backend_status: Signal<BackendStatus> = use_context();
    let mut config: Signal<AppConfig> = use_context();
    let mut auth_status: Signal<AuthStatus> = use_context();
    let runtime: Signal<AgentRuntime> = use_context();
    let input_devices = use_signal(|| {
        omi_audio::mic::list_input_devices().unwrap_or_default()
    });

    let backend_display = match &*backend_status.read() {
        BackendStatus::Starting => "Starting...".to_string(),
        BackendStatus::Connected => format!("Connected ({})", config.read().backend_url),
        BackendStatus::Error(e) => format!("Error: {e}"),
    };

    let auth_display = match &*auth_status.read() {
        AuthStatus::SignedOut => "Not signed in".to_string(),
        AuthStatus::Pending => "Signing in...".to_string(),
        AuthStatus::SignedIn { email, name } => {
            if name.is_empty() {
                email.clone()
            } else {
                format!("{name} ({email})")
            }
        }
        AuthStatus::Error(e) => format!("Error: {e}"),
    };

    let is_signed_in = matches!(*auth_status.read(), AuthStatus::SignedIn { .. });
    let is_pending = matches!(*auth_status.read(), AuthStatus::Pending);

    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Settings" }

            // Account section
            section { class: "settings-section",
                h2 { "Account" }
                div { class: "settings-row",
                    span { class: "settings-label", "Status" }
                    span { class: "settings-value", "{auth_display}" }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "" }
                    if is_signed_in {
                        button {
                            class: "btn btn-secondary",
                            onclick: move |_| {
                                config.write().sign_out();
                                let _ = config.read().save();
                                auth_status.set(AuthStatus::SignedOut);
                            },
                            "Sign Out"
                        }
                    } else {
                        button {
                            class: "btn btn-primary",
                            disabled: is_pending,
                            onclick: move |_| {
                                let mut auth = auth_status.clone();
                                let mut cfg = config.clone();
                                spawn(async move {
                                    crate::auth::start_google_sign_in(&mut auth, &mut cfg).await;
                                });
                            },
                            if is_pending { "Signing in..." } else { "Sign in with Google" }
                        }
                    }
                }
            }

            // Backend section
            section { class: "settings-section",
                h2 { "Backend" }
                div { class: "settings-row",
                    span { class: "settings-label", "Rust Sidecar" }
                    span { class: "settings-value", "{backend_display}" }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Sidecar URL" }
                    input {
                        class: "settings-input",
                        r#type: "text",
                        value: "{config.read().backend_url}",
                        onchange: move |e| {
                            config.write().backend_url = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Python Backend URL" }
                    input {
                        class: "settings-input",
                        r#type: "text",
                        value: "{config.read().python_backend_url}",
                        onchange: move |e| {
                            config.write().python_backend_url = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
            }

            // API Keys section
            section { class: "settings-section",
                h2 { "API Keys" }
                div { class: "settings-row",
                    label { class: "settings-label", "Deepgram" }
                    input {
                        class: "settings-input",
                        r#type: "password",
                        placeholder: "dg-...",
                        value: "{config.read().deepgram_api_key}",
                        onchange: move |e| {
                            config.write().deepgram_api_key = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Gemini" }
                    input {
                        class: "settings-input",
                        r#type: "password",
                        placeholder: "AIza...",
                        value: "{config.read().gemini_api_key}",
                        onchange: move |e| {
                            config.write().gemini_api_key = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Groq" }
                    input {
                        class: "settings-input",
                        r#type: "password",
                        placeholder: "gsk_...",
                        value: "{config.read().groq_api_key}",
                        onchange: move |e| {
                            config.write().groq_api_key = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "OpenAI / Azure Key" }
                    input {
                        class: "settings-input",
                        r#type: "password",
                        placeholder: "sk-... or Azure api-key",
                        value: "{config.read().openai_api_key}",
                        onchange: move |e| {
                            config.write().openai_api_key = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Anthropic Key" }
                    input {
                        class: "settings-input",
                        r#type: "password",
                        placeholder: "sk-ant-...",
                        value: "{config.read().anthropic_api_key}",
                        onchange: move |e| {
                            config.write().anthropic_api_key = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Anthropic Model" }
                    input {
                        class: "settings-input",
                        r#type: "text",
                        placeholder: "claude-3-5-sonnet-20241022",
                        value: "{config.read().anthropic_model}",
                        onchange: move |e| {
                            config.write().anthropic_model = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "OpenAI Base URL" }
                    input {
                        class: "settings-input",
                        r#type: "text",
                        placeholder: "https://api.openai.com/v1",
                        value: "{config.read().openai_base_url}",
                        onchange: move |e| {
                            config.write().openai_base_url = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "OpenAI Model" }
                    input {
                        class: "settings-input",
                        r#type: "text",
                        placeholder: "gpt-4o-mini",
                        value: "{config.read().openai_model}",
                        onchange: move |e| {
                            config.write().openai_model = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
            }
            
            // LLM Routing section
            section { class: "settings-section",
                h2 { "LLM Routing" }
                div { class: "settings-row",
                    label { class: "settings-label", "Primary Provider (Chat)" }
                    select {
                        class: "settings-input",
                        value: "{config.read().primary_provider}",
                        onchange: move |e| {
                            config.write().primary_provider = e.value();
                            let _ = config.read().save();
                        },
                        option { value: "auto", "Auto Fallback" }
                        option { value: "openai", "OpenAI / Azure" }
                        option { value: "anthropic", "Anthropic" }
                        option { value: "groq", "Groq" }
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Background Provider" }
                    select {
                        class: "settings-input",
                        value: "{config.read().background_provider}",
                        onchange: move |e| {
                            config.write().background_provider = e.value();
                            let _ = config.read().save();
                        },
                        option { value: "auto", "Auto Fallback" }
                        option { value: "openai", "OpenAI / Azure" }
                        option { value: "anthropic", "Anthropic" }
                        option { value: "groq", "Groq" }
                    }
                }
            }

            // Audio section
            section { class: "settings-section",
                h2 { "Audio" }
                div { class: "settings-row",
                    span { class: "settings-label", "Microphone" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().mic_enabled,
                            onchange: move |e| {
                                config.write().mic_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Mic Device" }
                    select {
                        class: "settings-input",
                        value: "{config.read().mic_device_name}",
                        onchange: move |e| {
                            config.write().mic_device_name = e.value();
                            let _ = config.read().save();
                        },
                        option { value: "", "Default System Microphone" }
                        for dev in input_devices.read().iter() {
                            option { value: "{dev}", "{dev}" }
                        }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "System Audio" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().system_audio_enabled,
                            onchange: move |e| {
                                config.write().system_audio_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "Speaker Diarization" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().diarize_speakers,
                            onchange: move |e| {
                                config.write().diarize_speakers = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "" }
                    span { class: "settings-hint",
                        "Enable only for multi-speaker conversations. Off = all speech treated as one speaker."
                    }
                }
            }

            // Screen capture section
            section { class: "settings-section",
                h2 { "Screen Capture" }
                div { class: "settings-row",
                    span { class: "settings-label", "Enabled" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().screen_capture_enabled,
                            onchange: move |e| {
                                config.write().screen_capture_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "Auto Extract" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().screenshot_auto_extract_enabled,
                            onchange: move |e| {
                                config.write().screenshot_auto_extract_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "Save Summary as Memory" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().screenshot_auto_save_memory,
                            onchange: move |e| {
                                config.write().screenshot_auto_save_memory = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "Save Action Items" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().screenshot_auto_save_action_items,
                            onchange: move |e| {
                                config.write().screenshot_auto_save_action_items = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "OCR" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().ocr_enabled,
                            onchange: move |e| {
                                config.write().ocr_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Capture Interval (sec)" }
                    input {
                        class: "settings-input settings-input-sm",
                        r#type: "number",
                        min: "1",
                        max: "60",
                        value: "{config.read().capture_interval_secs}",
                        onchange: move |e| {
                            if let Ok(v) = e.value().parse::<u64>() {
                                config.write().capture_interval_secs = v.max(1).min(60);
                                let _ = config.read().save();
                            }
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Screen Context Count" }
                    input {
                        class: "settings-input settings-input-sm",
                        r#type: "number",
                        min: "1",
                        max: "20",
                        value: "{config.read().screen_context_count}",
                        onchange: move |e| {
                            if let Ok(v) = e.value().parse::<usize>() {
                                config.write().screen_context_count = v.min(20).max(1);
                                let _ = config.read().save();
                            }
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "OCR Snippet Max Chars" }
                    input {
                        class: "settings-input settings-input-sm",
                        r#type: "number",
                        min: "64",
                        max: "5000",
                        value: "{config.read().ocr_summary_max_chars}",
                        onchange: move |e| {
                            if let Ok(v) = e.value().parse::<usize>() {
                                config.write().ocr_summary_max_chars = v.min(5000).max(64);
                                let _ = config.read().save();
                            }
                        },
                    }
                }
            }

            // Wearable section
            section { class: "settings-section",
                h2 { "Wearable" }
                div { class: "settings-row",
                    span { class: "settings-label", "Omi Device" }
                    span { class: "settings-value text-muted", "Not connected" }
                }
            }

            // Agent / M9 section
            section { class: "settings-section",
                h2 { "Agent Runtime" }

                // ── Auto-detect status ────────────────────────────────────
                {
                    let node_found = {
                        let cfg = config.read();
                        if !cfg.node_path.is_empty() {
                            std::path::Path::new(&cfg.node_path).exists()
                        } else {
                            crate::agent_runtime::find_node().is_some()
                        }
                    };
                    let script_found = {
                        let cfg = config.read();
                        if !cfg.agent_script_path.is_empty() {
                            std::path::Path::new(&cfg.agent_script_path).exists()
                        } else {
                            crate::agent_runtime::find_agent_script().is_some()
                        }
                    };
                    rsx! {
                        div { class: "agent-setup-status",
                            div { class: if node_found { "agent-setup-row ok" } else { "agent-setup-row warn" },
                                span { class: "setup-icon", if node_found { "✓" } else { "✗" } }
                                span { if node_found { "Node.js found" } else { "Node.js not found — install from nodejs.org or via Volta/nvm" } }
                            }
                            div { class: if script_found { "agent-setup-row ok" } else { "agent-setup-row warn" },
                                span { class: "setup-icon", if script_found { "✓" } else { "✗" } }
                                span { if script_found { "Agent script found" } else { "Agent not built — run: cd C:\\omi\\desktop\\agent && npm run build" } }
                            }
                        }
                    }
                }

                div { class: "settings-row",
                    span { class: "settings-label", "Enable Agent" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().agent_enabled,
                            onchange: move |e| {
                                let enabled = e.checked();
                                config.write().agent_enabled = enabled;
                                let _ = config.read().save();
                                // If turning on, try to start the runtime immediately
                                if enabled {
                                    let rt = runtime.read().clone();
                                    let cfg = config.read().clone();
                                    spawn(async move {
                                        match crate::agent_runtime::try_start_from_config(&rt, &cfg).await {
                                            Ok(true)  => tracing::info!("[SETTINGS] Agent started"),
                                            Ok(false) => tracing::warn!("[SETTINGS] Agent not found after enable"),
                                            Err(e)    => tracing::error!("[SETTINGS] Agent start failed: {e}"),
                                        }
                                    });
                                } else {
                                    let rt = runtime.read().clone();
                                    spawn(async move { rt.shutdown().await; });
                                }
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "" }
                    span { class: "settings-hint",
                        "Powers the Agent page and proactive suggestions. Requires Node.js and the built agent script."
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Node.js Path" }
                    input {
                        class: "settings-input",
                        r#type: "text",
                        placeholder: "Auto-detect (e.g. C:\\Program Files\\Volta\\node.exe)",
                        value: "{config.read().node_path}",
                        onchange: move |e| {
                            config.write().node_path = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Agent Script" }
                    input {
                        class: "settings-input",
                        r#type: "text",
                        placeholder: "Auto-detect (e.g. C:\\omi\\desktop\\agent\\dist\\index.js)",
                        value: "{config.read().agent_script_path}",
                        onchange: move |e| {
                            config.write().agent_script_path = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "Proactive Suggestions" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().proactive_agent_enabled,
                            onchange: move |e| {
                                config.write().proactive_agent_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Suggestion Interval (min)" }
                    input {
                        class: "settings-input settings-input-sm",
                        r#type: "number",
                        min: "1",
                        max: "60",
                        value: "{config.read().proactive_tick_mins}",
                        onchange: move |e| {
                            if let Ok(v) = e.value().parse::<u64>() {
                                config.write().proactive_tick_mins = v.max(1).min(60);
                                let _ = config.read().save();
                            }
                        },
                    }
                }
            }
        }
    }
}
