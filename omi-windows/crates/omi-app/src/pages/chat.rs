use dioxus::prelude::*;
use serde::{Deserialize, Serialize};

use crate::app::Db;
use crate::config::AppConfig;
use crate::llm::{LlmMessage, resolve_llm_endpoint};

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
    let db: Signal<Option<Db>> = use_context();
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
        let (api_key, api_url, model) = resolve_llm_endpoint(&cfg);

        // Build system prompt from recent conversation context + memories + summarized screen OCR

            spawn(async move {
            loading.set(true);
            tracing::info!("[CHAT] Sending to: {api_url} (model: {model})");

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

            // Build system prompt (include recent convo summaries, memories, and summarized screen OCR)
            let mut parts: Vec<String> = vec![
                "You are Omi, a helpful AI assistant with access to the user's recent voice conversations and memories.".into(),
                "Answer concisely and helpfully. Reference specific things from the context when relevant.".into(),
            ];

            if let Some(Db(ref d)) = *db.read() {
                // Recent conversation summaries (last 5)
                if let Ok(ctx) = d.get_recent_context(5) {
                    if !ctx.is_empty() {
                        parts.push("\n## Recent Conversations".into());
                        for (_, title, summary) in &ctx {
                            if !summary.is_empty() {
                                parts.push(format!("**{title}**: {summary}"));
                            }
                        }
                    }
                }
                // Memories (last 20)
                if let Ok(mem_text) = d.get_memories_text(20) {
                    if !mem_text.is_empty() {
                        parts.push("\n## Remembered Facts".into());
                        parts.push(mem_text);
                    }
                }

                // Recent screenshots -> summarize via LLM to reduce tokens
                if let Ok(screens) = d.list_screenshots(cfg.screen_context_count) {
                    if !screens.is_empty() {
                        // Prepare tuples (ts, title, ocr)
                        let mut items: Vec<(String, String, String)> = Vec::new();
                        for s in screens.iter() {
                            let ts = s.captured_at.to_rfc3339();
                            let title = s.window_title.clone().unwrap_or_else(|| "(no title)".into());
                            let ocr = s.ocr_text.clone().unwrap_or_else(|| "".into());
                            items.push((ts, title, ocr));
                        }
                        // Ask the LLM to summarize the OCR snippets into short bullets
                        match crate::llm::summarize_ocr_snippets(&cfg, items).await {
                            Ok(summary) => {
                                if !summary.is_empty() {
                                    parts.push("\n## Recent Screen Activity".into());
                                    parts.push(summary);
                                }
                            }
                            Err(e) => tracing::error!("[CHAT] OCR summarization failed: {e}"),
                        }
                    }
                }
            }

            let system_prompt = parts.join("\n");

            // Build full message list: system + conversation history
            let mut llm_msgs: Vec<LlmMessage> = vec![LlmMessage { role: "system".into(), content: system_prompt }];
            llm_msgs.extend(messages.read().iter().map(|m| LlmMessage {
                role: m.role.clone(),
                content: m.content.clone(),
            }));

            let req = ChatRequest {
                model,
                messages: llm_msgs.iter().map(|m| ChatRequestMsg {
                    role: m.role.clone(),
                    content: m.content.clone(),
                }).collect(),
                stream: false,
            };

            tracing::info!("Chat URL: {api_url}");
            tracing::info!("Chat model: {}", req.model);

            let request = reqwest::Client::new()
                .post(&api_url)
                .header("Authorization", format!("Bearer {api_key}"));
            let result = request.json(&req).send().await;

            match result {
                Ok(resp) => {
                    let status = resp.status();
                    let body_text = resp.text().await.unwrap_or_default();
                    tracing::info!("Chat API response [{}]: {}", status, &body_text[..body_text.len().min(500)]);

                    if !status.is_success() {
                        let mut msgs = messages.read().clone();
                        msgs.push(ChatMessage {
                            role: "assistant".into(),
                            content: format!("API Error {status}: {body_text}"),
                        });
                        messages.set(msgs);
                    } else {
                        match serde_json::from_str::<ChatResponse>(&body_text) {
                            Ok(body) => {
                                if let Some(choice) = body.choices.first() {
                                    let mut msgs = messages.read().clone();
                                    msgs.push(ChatMessage {
                                        role: "assistant".into(),
                                        content: choice.message.content.clone(),
                                    });
                                    messages.set(msgs);
                                }
                            }
                            Err(e) => {
                                tracing::error!("Failed to parse chat response: {e}\nBody: {body_text}");
                                let mut msgs = messages.read().clone();
                                msgs.push(ChatMessage {
                                    role: "assistant".into(),
                                    content: format!("Parse error: {e}\nRaw: {}", &body_text[..body_text.len().min(200)]),
                                });
                                messages.set(msgs);
                            }
                        }
                    }
                }
                Err(e) => {
                    tracing::error!("Chat request failed: {e}");
                    let mut msgs = messages.read().clone();
                    msgs.push(ChatMessage {
                        role: "assistant".into(),
                        content: format!("Request failed: {e}"),
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
                    onkeydown: move |e| {
                        if e.key() == Key::Enter {
                            e.prevent_default();
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
