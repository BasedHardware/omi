use dioxus::prelude::*;
use serde::{Deserialize, Serialize};

use crate::config::AppConfig;

#[derive(Debug, Clone, PartialEq)]
struct ChatMessage {
    role: String, // "user" or "assistant"
    content: String,
}

#[derive(Serialize)]
struct ChatRequest {
    model: String,
    messages: Vec<ChatRequestMsg>,
    stream: bool,
}

#[derive(Serialize)]
struct ChatRequestMsg {
    role: String,
    content: String,
}

#[derive(Deserialize)]
struct ChatResponse {
    choices: Vec<ChatChoice>,
}

#[derive(Deserialize)]
struct ChatChoice {
    message: ChatResponseMsg,
}

#[derive(Deserialize)]
struct ChatResponseMsg {
    content: String,
}

#[component]
pub fn ChatPage() -> Element {
    let config: Signal<AppConfig> = use_context();
    let mut input = use_signal(String::new);
    let mut messages = use_signal(Vec::<ChatMessage>::new);
    let mut loading = use_signal(|| false);

    let mut do_send = move || {
        let text = input.read().trim().to_string();
        if text.is_empty() || *loading.read() {
            return;
        }

        input.set(String::new());

        // Add user message
        let mut msgs = messages.read().clone();
        msgs.push(ChatMessage {
            role: "user".into(),
            content: text.clone(),
        });
        messages.set(msgs);

        let cfg = config.read().clone();
        // Priority: env AZURE_* > Groq config > OpenAI config
        let azure_key = std::env::var("AZURE_API_KEY").unwrap_or_default();
        let azure_base = std::env::var("AZURE_BASE_URL").unwrap_or_default();
        let azure_model = std::env::var("AZURE_MODEL").unwrap_or_default();

        let (api_key, api_url, model) = if !azure_key.is_empty() && !azure_base.is_empty() {
            let base = azure_base.trim_end_matches('/').to_string();
            let url = format!("{base}/chat/completions?api-version=2024-02-15-preview");
            let mdl = if azure_model.is_empty() { "gpt-4o-mini".to_string() } else { azure_model };
            (azure_key, url, mdl)
        } else if !cfg.groq_api_key.is_empty() {
            (
                cfg.groq_api_key.clone(),
                "https://api.groq.com/openai/v1/chat/completions".to_string(),
                "llama-3.3-70b-versatile".to_string(),
            )
        } else if !cfg.openai_api_key.is_empty() {
            let base = cfg.openai_base_url.trim_end_matches('/').to_string();
            let is_azure = base.contains("azure.com");
            let url = if is_azure {
                format!("{base}/chat/completions?api-version=2024-02-15-preview")
            } else {
                format!("{base}/chat/completions")
            };
            (
                cfg.openai_api_key.clone(),
                url,
                cfg.openai_model.clone(),
            )
        } else {
            (String::new(), String::new(), String::new())
        };

        spawn(async move {
            loading.set(true);

            if api_key.is_empty() {
                let mut msgs = messages.read().clone();
                msgs.push(ChatMessage {
                    role: "assistant".into(),
                    content: "Please set your Groq or OpenAI API key in Settings to use chat.".into(),
                });
                messages.set(msgs);
                loading.set(false);
                return;
            }

            // Build request payload
            let history: Vec<ChatRequestMsg> = messages
                .read()
                .iter()
                .map(|m| ChatRequestMsg {
                    role: m.role.clone(),
                    content: m.content.clone(),
                })
                .collect();

            let req = ChatRequest {
                model,
                messages: history,
                stream: false,
            };

            let is_azure = api_url.contains("azure.com");
            let mut request = reqwest::Client::new().post(&api_url);
            if is_azure {
                request = request.header("api-key", &api_key);
            } else {
                request = request.header("Authorization", format!("Bearer {api_key}"));
            }
            let result = request.json(&req).send().await;

            match result {
                Ok(resp) => {
                    if let Ok(body) = resp.json::<ChatResponse>().await {
                        if let Some(choice) = body.choices.first() {
                            let mut msgs = messages.read().clone();
                            msgs.push(ChatMessage {
                                role: "assistant".into(),
                                content: choice.message.content.clone(),
                            });
                            messages.set(msgs);
                        }
                    } else {
                        let mut msgs = messages.read().clone();
                        msgs.push(ChatMessage {
                            role: "assistant".into(),
                            content: "Error: Failed to parse response".into(),
                        });
                        messages.set(msgs);
                    }
                }
                Err(e) => {
                    let mut msgs = messages.read().clone();
                    msgs.push(ChatMessage {
                        role: "assistant".into(),
                        content: format!("Error: {e}"),
                    });
                    messages.set(msgs);
                }
            }

            loading.set(false);
        });
    };

    rsx! {
        div { class: "page page-chat",
            h1 { class: "page-title", "Chat" }

            div { class: "chat-messages",
                if messages.read().is_empty() {
                    div { class: "chat-empty",
                        p { "Start a conversation. Your memories and context will be used automatically." }
                    }
                }
                for msg in messages.read().iter() {
                    div {
                        class: if msg.role == "user" { "chat-bubble user" } else { "chat-bubble assistant" },
                        p { "{msg.content}" }
                    }
                }
                if *loading.read() {
                    div { class: "chat-bubble assistant loading",
                        span { class: "typing-dots", "..." }
                    }
                }
            }

            div { class: "chat-input-bar",
                input {
                    class: "chat-input",
                    r#type: "text",
                    placeholder: "Ask anything...",
                    value: "{input}",
                    oninput: move |e| input.set(e.value()),
                    onkeypress: move |e| {
                        if e.key() == Key::Enter {
                            do_send();
                        }
                    },
                }
                button {
                    class: "btn btn-primary",
                    disabled: *loading.read(),
                    onclick: move |_| do_send(),
                    "Send"
                }
            }
        }
    }
}
