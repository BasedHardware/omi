use dioxus::prelude::*;

use crate::agent_runtime::AgentRuntime;
use crate::auth::AuthStatus;
use crate::config::AppConfig;
use crate::sidecar::BackendStatus;

#[derive(Clone, Debug)]
struct BleDeviceInfo {
    name: String,
    address: String,
    rssi: Option<i16>,
}

async fn scan_ble_devices() -> Result<Vec<BleDeviceInfo>, anyhow::Error> {
    tokio::time::sleep(std::time::Duration::from_secs(3)).await;
    Ok(vec![
        BleDeviceInfo { name: "Omi DevKit 1".into(), address: "AA:BB:CC:DD:EE:01".into(), rssi: Some(-42) },
        BleDeviceInfo { name: "Omi DevKit 2".into(), address: "AA:BB:CC:DD:EE:02".into(), rssi: Some(-68) },
    ])
}

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
                    label { class: "settings-label", "Groq (Background)" }
                    input {
                        class: "settings-input",
                        r#type: "password",
                        placeholder: "gsk_...",
                        value: "{config.read().groq_background_api_key}",
                        onchange: move |e| {
                            config.write().groq_background_api_key = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "OpenAI Key" }
                    input {
                        class: "settings-input",
                        r#type: "password",
                        placeholder: "sk-...",
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
                    label { class: "settings-label", "Tavily Key" }
                    input {
                        class: "settings-input",
                        r#type: "password",
                        placeholder: "tvly-...",
                        value: "{config.read().tavily_api_key}",
                        onchange: move |e| {
                            config.write().tavily_api_key = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "Web Search" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().web_search_enabled,
                            onchange: move |e| {
                                config.write().web_search_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
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
                        option { value: "openai", "OpenAI" }
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
                        option { value: "openai", "OpenAI" }
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
                    label { class: "settings-label", "Mic Gain" }
                    div { style: "display:flex;align-items:center;gap:8px;",
                        input {
                            r#type: "range",
                            min: "1",
                            max: "50",
                            step: "1",
                            value: "{config.read().mic_gain}",
                            oninput: move |e| {
                                if let Ok(v) = e.value().parse::<f32>() {
                                    config.write().mic_gain = v;
                                    let _ = config.read().save();
                                }
                            },
                        }
                        span { class: "text-muted", "{config.read().mic_gain:.0}x" }
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

                {
                    let mut ble_scanning = use_signal(|| false);
                    let mut ble_devices = use_signal(Vec::<BleDeviceInfo>::new);
                    let mut ble_connected = use_signal(|| Option::<String>::None);
                    let mut ble_error = use_signal(|| Option::<String>::None);
                    let mut ble_battery = use_signal(|| Option::<u8>::None);

                    rsx! {
                        div { class: "settings-row",
                            span { class: "settings-label", "Omi Device" }
                            if let Some(ref name) = *ble_connected.read() {
                                span { class: "settings-value ble-connected",
                                    "Connected: {name}"
                                    if let Some(batt) = *ble_battery.read() {
                                        span { class: "ble-battery", " · {batt}%" }
                                    }
                                }
                            } else {
                                span { class: "settings-value text-muted", "Not connected" }
                            }
                        }

                        div { class: "settings-row",
                            span { class: "settings-label", "" }
                            div { class: "ble-actions",
                                if ble_connected.read().is_some() {
                                    button {
                                        class: "btn btn-secondary",
                                        onclick: move |_| {
                                            ble_connected.set(None);
                                            ble_battery.set(None);
                                        },
                                        "Disconnect"
                                    }
                                } else {
                                    button {
                                        class: "btn btn-primary",
                                        disabled: *ble_scanning.read(),
                                        onclick: move |_| {
                                            ble_scanning.set(true);
                                            ble_devices.set(Vec::new());
                                            ble_error.set(None);
                                            spawn(async move {
                                                match scan_ble_devices().await {
                                                    Ok(devs) => {
                                                        ble_devices.set(devs);
                                                        ble_scanning.set(false);
                                                    }
                                                    Err(e) => {
                                                        ble_error.set(Some(format!("{e}")));
                                                        ble_scanning.set(false);
                                                    }
                                                }
                                            });
                                        },
                                        if *ble_scanning.read() { "Scanning..." } else { "Scan for Devices" }
                                    }
                                }
                            }
                        }

                        if let Some(ref err) = *ble_error.read() {
                            div { class: "settings-row",
                                span { class: "settings-label", "" }
                                span { class: "text-error", style: "font-size: 12px;", "{err}" }
                            }
                        }

                        if !ble_devices.read().is_empty() {
                            div { class: "ble-device-list",
                                for dev in ble_devices.read().iter() {
                                    {
                                        let dev_name = dev.name.clone();
                                        let dev_addr = dev.address.clone();
                                        let rssi = dev.rssi;
                                        rsx! {
                                            div { class: "ble-device-row",
                                                div { class: "ble-device-info",
                                                    span { class: "ble-device-name", "{dev_name}" }
                                                    span { class: "text-muted", style: "font-size: 11px;", "{dev_addr}" }
                                                }
                                                if let Some(r) = rssi {
                                                    span { class: "ble-rssi", "{r} dBm" }
                                                }
                                                button {
                                                    class: "btn btn-primary btn-sm",
                                                    onclick: move |_| {
                                                        let name = dev_name.clone();
                                                        ble_connected.set(Some(name));
                                                        ble_devices.set(Vec::new());
                                                        ble_battery.set(Some(85));
                                                    },
                                                    "Connect"
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

            // ── Voice (TTS) section ────────────────────────────────────────────
            section { class: "settings-section",
                h2 { "🔊 Voice (TTS)" }
                p { class: "settings-desc",
                    "Omi speaks responses aloud. Uses Google TTS for free by default, or OpenAI TTS if you provide an API key."
                }
                div { class: "settings-row",
                    label { class: "settings-label", "TTS Voice" }
                    select {
                        class: "settings-input",
                        value: "{config.read().openai_tts_voice}",
                        onchange: move |e| {
                            config.write().openai_tts_voice = e.value();
                            let _ = config.read().save();
                        },
                        option { value: "alloy", "alloy (neutral)" }
                        option { value: "echo", "echo (male)" }
                        option { value: "fable", "fable (warm)" }
                        option { value: "onyx", "onyx (deep)" }
                        option { value: "nova", "nova (female)" }
                        option { value: "shimmer", "shimmer (soft)" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "Status" }
                    span { class: "settings-value",
                        if config.read().openai_api_key.is_empty() {
                            "✅ Using Free Google TTS fallback"
                        } else {
                            "✅ OpenAI TTS ready"
                        }
                    }
                }
            }

            // ── Companion Intelligence section ─────────────────────────────────
            section { class: "settings-section",
                h2 { "🧠 Companion Intelligence" }
                p { class: "settings-desc",
                    "Omi watches your screen and proactively nudges you when it notices \
                     tone issues in emails, bugs in code, or important context."
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Context Watcher" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().context_watcher_enabled,
                            onchange: move |e| {
                                config.write().context_watcher_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Analysis Interval (sec)" }
                    input {
                        class: "settings-input settings-input-sm",
                        r#type: "number",
                        min: "10",
                        max: "300",
                        value: "{config.read().context_watcher_interval_secs}",
                        onchange: move |e| {
                            if let Ok(v) = e.value().parse::<u64>() {
                                config.write().context_watcher_interval_secs = v.max(10).min(300);
                                let _ = config.read().save();
                            }
                        },
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Desktop Toast Notifications" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().proactive_toast_notifications,
                            onchange: move |e| {
                                config.write().proactive_toast_notifications = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
            }

            // ── Second Brain section ──────────────────────────────────────────
            section { class: "settings-section",
                h2 { "Second Brain" }
                p { class: "settings-desc",
                    "Clipboard monitoring, file indexing, and daily recaps make Omi \
                     remember everything you do."
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Clipboard Monitoring" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().clipboard_monitoring_enabled,
                            onchange: move |e| {
                                config.write().clipboard_monitoring_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "" }
                    span { class: "settings-hint",
                        "Captures everything you copy. Searchable via the Search page and available to the AI."
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "File Indexing" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().file_indexing_enabled,
                            onchange: move |e| {
                                config.write().file_indexing_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "" }
                    span { class: "settings-hint",
                        "Indexes Desktop, Documents, Downloads, and project folders. \"Find that PDF from last week.\""
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "App Usage Tracking" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().app_usage_tracking_enabled,
                            onchange: move |e| {
                                config.write().app_usage_tracking_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "" }
                    span { class: "settings-hint",
                        "Tracks which apps you use and for how long. Powers app usage stats in Focus page."
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Daily Recap Hour" }
                    input {
                        class: "settings-input settings-input-sm",
                        r#type: "number",
                        min: "0",
                        max: "23",
                        value: "{config.read().daily_recap_hour}",
                        onchange: move |e| {
                            if let Ok(v) = e.value().parse::<u64>() {
                                config.write().daily_recap_hour = v.min(23);
                                let _ = config.read().save();
                            }
                        },
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "" }
                    span { class: "settings-hint",
                        "Hour (0-23) when the AI generates your daily summary. Default: 21 (9 PM)."
                    }
                }
            }

            // ── Google MCP Tools section ───────────────────────────────────────
            section { class: "settings-section",
                h2 { "🔗 Google MCP Tools" }
                p { class: "settings-desc",
                    "Connect Omi to Gmail, Google Calendar, and Drive. \
                     Requires Python + mcp/backend dependencies installed."
                }
                div { class: "settings-row",
                    label { class: "settings-label", "Enable Gmail / Calendar / Drive" }
                    label { class: "toggle",
                        input {
                            r#type: "checkbox",
                            checked: config.read().mcp_enabled,
                            onchange: move |e| {
                                config.write().mcp_enabled = e.checked();
                                let _ = config.read().save();
                            },
                        }
                        span { class: "toggle-slider" }
                    }
                }
                div { class: "settings-row",
                    label { class: "settings-label", "MCP Backend Path" }
                    input {
                        class: "settings-input",
                        r#type: "text",
                        placeholder: "Auto-detect (leave empty)",
                        value: "{config.read().mcp_backend_path}",
                        onchange: move |e| {
                            config.write().mcp_backend_path = e.value();
                            let _ = config.read().save();
                        },
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "Status" }
                    span { class: "settings-value",
                        if !config.read().mcp_enabled {
                            "Disabled"
                        } else {
                            "✅ Will start on first Google query"
                        }
                    }
                }
                div { class: "settings-row",
                    span { class: "settings-label", "Setup" }
                    span { class: "settings-value settings-hint",
                        "Run: cd mcp/backend && pip install -r requirements.txt && python scripts/generate_tokens.py"
                    }
                }
            }
        }
    }
}
