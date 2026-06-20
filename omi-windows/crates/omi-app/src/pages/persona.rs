use dioxus::prelude::*;
use crate::app::Db;
use crate::config::AppConfig;

#[component]
pub fn PersonaPage() -> Element {
    let mut config: Signal<AppConfig> = use_context();
    let mut saving = use_signal(|| false);
    let mut saved = use_signal(|| false);

    let handle_save = move |_| {
        let cfg = config.read().clone();
        saving.set(true);
        spawn(async move {
            if let Err(e) = cfg.save() {
                tracing::error!("[PERSONA] Failed to save config: {e}");
            } else {
                saved.set(true);
                tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
                saved.set(false);
            }
            saving.set(false);
        });
    };

    rsx! {
        div { class: "page",
            div { class: "page-header",
                h1 { class: "page-title", "Persona" }
                p { class: "page-subtitle", "Customize your AI assistant's name, personality, and how it talks to you." }
            }

            // Assistant Identity
            div { class: "card",
                h3 { "Assistant Identity" }
                div { class: "form-row",
                    label { class: "form-label", "Assistant Name" }
                    input {
                        class: "form-input",
                        r#type: "text",
                        placeholder: "Omi",
                        value: "{config.read().persona_name}",
                        oninput: move |e| config.write().persona_name = e.value(),
                    }
                    p { class: "form-help", "What your AI calls itself. Leave empty for the default name." }
                }
            }

            // User Identity
            div { class: "card",
                h3 { "Your Identity" }
                div { class: "form-row",
                    label { class: "form-label", "Your Name" }
                    input {
                        class: "form-input",
                        r#type: "text",
                        placeholder: "How your AI should refer to you",
                        value: "{config.read().user_name}",
                        oninput: move |e| config.write().user_name = e.value(),
                    }
                    p { class: "form-help", "Your AI will use this name to personalize responses. Leave empty for generic references." }
                }
            }

            // Personality & Behavior
            div { class: "card",
                h3 { "Personality & Instructions" }
                div { class: "form-row",
                    label { class: "form-label", "Custom Instructions" }
                    textarea {
                        class: "form-textarea",
                        rows: "6",
                        placeholder: "Example:\n\n- Be encouraging and positive\n- Use simple, clear language\n- Ask follow-up questions when helpful\n- Avoid technical jargon unless asked",
                        value: "{config.read().persona_instructions}",
                        oninput: move |e| config.write().persona_instructions = e.value(),
                    }
                    p { class: "form-help", "Instructions that shape your AI's personality and response style. These are included in every conversation." }
                }
            }

            // Quick Presets
            div { class: "card",
                h3 { "Quick Presets" }
                div { class: "preset-grid",
                    button {
                        class: "preset-btn",
                        onclick: move |_| {
                            config.write().persona_instructions = "Be concise, direct, and to the point. Focus on efficiency and clarity.".to_string();
                        },
                        "Concise & Direct"
                    }
                    button {
                        class: "preset-btn",
                        onclick: move |_| {
                            config.write().persona_instructions = "Be friendly, warm, and conversational. Use encouraging language and show enthusiasm.".to_string();
                        },
                        "Friendly & Warm"
                    }
                    button {
                        class: "preset-btn",
                        onclick: move |_| {
                            config.write().persona_instructions = "Be analytical and thorough. Break down complex topics into simple steps. Provide detailed explanations.".to_string();
                        },
                        "Analytical & Detailed"
                    }
                    button {
                        class: "preset-btn",
                        onclick: move |_| {
                            config.write().persona_instructions = "Be creative and imaginative. Suggest alternative approaches and think outside the box.".to_string();
                        },
                        "Creative & Innovative"
                    }
                    button {
                        class: "preset-btn",
                        onclick: move |_| {
                            config.write().persona_instructions = "Be professional and formal. Use proper business etiquette and maintain a respectful tone.".to_string();
                        },
                        "Professional & Formal"
                    }
                    button {
                        class: "preset-btn",
                        onclick: move |_| {
                            config.write().persona_instructions = String::new();
                        },
                        "Clear Custom"
                    }
                }
            }

            // Save Actions
            div { class: "card actions-card",
                div { class: "actions-row",
                    button {
                        class: "btn btn-primary",
                        disabled: *saving.read(),
                        onclick: handle_save,
                        if *saving.read() { "Saving…" } else { "Save Changes" }
                    }
                    if *saved.read() {
                        span { class: "saved-indicator", "✓ Saved" }
                    }
                }
            }
        }
    }
}
