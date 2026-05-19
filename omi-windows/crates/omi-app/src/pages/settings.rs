use dioxus::prelude::*;

use crate::auth::AuthStatus;
use crate::config::AppConfig;
use crate::sidecar::BackendStatus;

#[component]
pub fn SettingsPage() -> Element {
    let backend_status: Signal<BackendStatus> = use_context();
    let mut config: Signal<AppConfig> = use_context();
    let mut auth_status: Signal<AuthStatus> = use_context();

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
            }

            // Wearable section
            section { class: "settings-section",
                h2 { "Wearable" }
                div { class: "settings-row",
                    span { class: "settings-label", "Omi Device" }
                    span { class: "settings-value text-muted", "Not connected" }
                }
            }
        }
    }
}
