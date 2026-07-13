/// Agent page — full streaming conversation UI with the Omi agent runtime.
///
/// Features:
///   • Streaming token-by-token text output (text_delta events)
///   • Tool-call display with expandable JSON input
///   • Token usage summary per turn
///   • Agent status indicator (Unavailable / Starting / Ready / Error)
///   • System prompt / model configurable from this page
///   • Full conversation history within the session

use dioxus::prelude::*;

use crate::agent_runtime::{AgentEvent, AgentRuntime, AgentStatus};
use crate::app::Db;
use crate::config::AppConfig;
use crate::recording::LiveTranscript;

// ── Message types ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
enum MessageRole {
    User,
    Agent,
    Tool { name: String, input: String },
    SystemEvent(String),
}

#[derive(Debug, Clone)]
struct ChatMessage {
    id: String,
    role: MessageRole,
    text: String,
    /// For agent turns: cumulative tokens used
    tokens: Option<(u32, u32)>,
    is_streaming: bool,
}

impl ChatMessage {
    fn user(text: String) -> Self {
        Self { id: uuid::Uuid::new_v4().to_string(), role: MessageRole::User, text, tokens: None, is_streaming: false }
    }
    fn agent_streaming() -> Self {
        Self { id: uuid::Uuid::new_v4().to_string(), role: MessageRole::Agent, text: String::new(), tokens: None, is_streaming: true }
    }
    fn tool(name: String, input: String) -> Self {
        Self { id: uuid::Uuid::new_v4().to_string(), role: MessageRole::Tool { name, input: input.clone() }, text: input, tokens: None, is_streaming: false }
    }
    fn system(text: String) -> Self {
        Self { id: uuid::Uuid::new_v4().to_string(), role: MessageRole::SystemEvent(text.clone()), text, tokens: None, is_streaming: false }
    }
}

// ── Component ─────────────────────────────────────────────────────────────────

#[component]
pub fn AgentPage() -> Element {
    let config: Signal<AppConfig> = use_context();
    let db: Signal<Option<Db>> = use_context();
    let runtime: Signal<AgentRuntime> = use_context();
    let live_transcript: Signal<LiveTranscript> = use_context();
    let mut messages: Signal<Vec<ChatMessage>> = use_signal(Vec::new);
    // Flat history for the LLM: (role, content) pairs — kept in sync with messages
    let mut history: Signal<Vec<(String, String)>> = use_signal(Vec::new);
    let mut input_text = use_signal(String::new);
    let is_loading = use_signal(|| false);
    let mut pending_hitl: Signal<Option<String>> = use_signal(|| None);

    // Pre-fill from a tapped suggestion (if one exists in context)
    let mut suggestion_prompt: Signal<Option<String>> = use_context();

    // Native mode: agent is "Ready" as long as an LLM key is configured.
    let (api_key, _, _) = crate::llm::resolve_llm_endpoint(&config.read());
    let has_llm_key = !api_key.is_empty();
    // Use a simple derived status — no async polling needed
    let agent_status = if has_llm_key {
        AgentStatus::Ready
    } else {
        AgentStatus::Unavailable
    };

    // Consume AgentEvent broadcast → update messages (streaming text deltas)
    use_hook(move || {
        let runtime_ref = runtime.clone();
        let mut msgs = messages.clone();
        let mut hist = history.clone();
        let mut loading = is_loading.clone();
        let mut hitl_state = pending_hitl.clone();

        spawn(async move {
            let mut rx = runtime_ref.read().subscribe();
            let mut streaming_id: Option<String> = None;

            loop {
                match rx.recv().await {
                    Ok(AgentEvent::Init { .. }) => {}
                    Ok(AgentEvent::TextDelta { text }) => {
                        let mut list = msgs.read().clone();
                        if let Some(ref id) = streaming_id {
                            if let Some(msg) = list.iter_mut().find(|m| &m.id == id) {
                                msg.text.push_str(&text);
                            }
                        } else {
                            let mut m = ChatMessage::agent_streaming();
                            m.text.push_str(&text);
                            streaming_id = Some(m.id.clone());
                            list.push(m);
                        }
                        msgs.set(list);
                    }
                    Ok(AgentEvent::Result { text, input_tokens, output_tokens, .. }) => {
                        let mut list = msgs.read().clone();
                        let final_text = if let Some(ref id) = streaming_id.take() {
                            if let Some(msg) = list.iter_mut().find(|m| &m.id == id) {
                                msg.is_streaming = false;
                                msg.tokens = Some((input_tokens, output_tokens));
                                if msg.text.is_empty() { msg.text = text.clone(); }
                                msg.text.clone()
                            } else { text.clone() }
                        } else {
                            let mut m = ChatMessage::agent_streaming();
                            m.text = text.clone();
                            m.is_streaming = false;
                            m.tokens = Some((input_tokens, output_tokens));
                            list.push(m);
                            text.clone()
                        };
                        msgs.set(list);
                        // Append assistant turn to history
                        let mut h = hist.read().clone();
                        h.push(("assistant".into(), final_text));
                        hist.set(h);
                        loading.set(false);
                    }
                    Ok(AgentEvent::Error { message }) => {
                        let mut list = msgs.read().clone();
                        list.push(ChatMessage::system(format!("⚠ {message}")));
                        msgs.set(list);
                        loading.set(false);
                    }
                    Ok(AgentEvent::HitlRequest { thread_id, message }) => {
                        let mut list = msgs.read().clone();
                        list.push(ChatMessage::system(format!("🔒 Action Required: {message}\n(Type 'yes' or 'no' below)")));
                        msgs.set(list);
                        hitl_state.set(Some(thread_id));
                        loading.set(false);
                    }
                    Ok(_) => {}
                    Err(_) => {
                        tokio::time::sleep(tokio::time::Duration::from_millis(200)).await;
                        rx = runtime_ref.read().subscribe();
                    }
                }
            }
        });
    });

    // Auto-fill from tapped suggestion pill
    use_effect(move || {
        if let Some(prompt) = suggestion_prompt.read().clone() {
            input_text.set(prompt);
        }
    });

    // Build context for agent queries from DB + live transcript + persona
    let build_context = move || -> String {
        let db_val = db.read().clone();
        let cfg = config.read().clone();
        let mut ctx = String::new();

        // Persona instructions
        if !cfg.persona_instructions.is_empty() {
            ctx.push_str("## Persona Instructions\n");
            ctx.push_str(&cfg.persona_instructions);
            ctx.push('\n');
        }

        // Live transcript (what you're saying right now)
        let transcript = live_transcript.read();
        if !transcript.segments.is_empty() {
            ctx.push_str("## Live Transcript\n");
            for seg in transcript.segments.iter().take(6) {
                ctx.push_str(&format!("S{}: {}\n", seg.speaker, seg.text));
            }
        }

        // DB context
        if let Some(crate::app::Db(ref d)) = db_val {
            let memories = d.get_memories_text(10).unwrap_or_default();
            let recent = d.get_recent_context(3).unwrap_or_default();
            if !recent.is_empty() {
                ctx.push_str("## Recent Conversations\n");
                for (ts, title, text) in &recent {
                    ctx.push_str(&format!("[{ts}] {title}: {text}\n"));
                }
            }
            if !memories.is_empty() {
                ctx.push_str("## Long-term Memories\n");
                ctx.push_str(&memories);
            }
            if let Ok(clips) = d.list_clipboard_entries(10) {
                if !clips.is_empty() {
                    ctx.push_str("\n## Recent Clipboard\n");
                    for c in &clips {
                        let preview = if c.content.len() > 120 { &c.content[..120] } else { &c.content };
                        ctx.push_str(&format!("[{}] ({}) {}\n", c.captured_at.format("%H:%M"), c.content_type, preview));
                    }
                }
            }
            if let Ok(files) = d.list_recent_files(15) {
                if !files.is_empty() {
                    ctx.push_str("\n## Recent Files\n");
                    for f in &files {
                        ctx.push_str(&format!("{} ({})\n", f.file_path, f.extension.as_deref().unwrap_or("?")));
                    }
                }
            }
        }

        ctx
    };

    let mut send_message = move |text: String| {
        if text.trim().is_empty() || *is_loading.read() {
            return;
        }

        let runtime_ref = runtime.clone();

        let mut msgs = messages.clone();
        let mut hist = history.clone();
        let mut loading = is_loading.clone();

        // Add user message to UI + history immediately
        let mut list = msgs.read().clone();
        list.push(ChatMessage::user(text.clone()));
        msgs.set(list);
        let mut h = hist.read().clone();
        h.push(("user".into(), text.clone()));
        // Keep last 12 turns to avoid token bloat
        if h.len() > 24 {
            h = h.split_off(h.len() - 24);
        }
        hist.set(h.clone());
        loading.set(true);
        input_text.set(String::new());

        let ctx = build_context();

        // Clear suggestion pill after use
        suggestion_prompt.set(None);

        let mut p_hitl = pending_hitl.clone();
        let thread_id_opt = p_hitl.read().clone();
        if let Some(thread_id) = thread_id_opt {
            p_hitl.set(None);
            let hitl_text = text.clone();
            spawn(async move {
                let cfg = config.read().clone();
                let rt = runtime_ref.read().clone();
                if let Err(e) = rt.confirm_mcp_hitl(&thread_id, &hitl_text, &cfg).await {
                    tracing::error!("[AGENT PAGE] MCP HITL confirm failed: {e}");
                    let mut list = msgs.read().clone();
                    list.push(ChatMessage::system(format!("⚠ {e}")));
                    msgs.set(list);
                    loading.set(false);
                }
            });
            return;
        }

        spawn(async move {
            let cfg = config.read().clone();
            let assistant_name = if cfg.persona_name.is_empty() { "Omi" } else { &cfg.persona_name };
            let user_name = if cfg.user_name.is_empty() { "the user" } else { &cfg.user_name };
            let system = format!(
                "You are {}, a proactive AI assistant running on {}'s Windows computer.\n\
                Be concise, precise, and helpful. Use context below when relevant.\n\
                When listing items use plain text, not markdown (the UI renders plain text).\n\
                Adapt your tone to be natural and conversational.\n\n\
                {ctx}",
                assistant_name, user_name, ctx = ctx
            );
            // Use native LLM path — no Node.js dependency
            let rt = runtime_ref.read().clone();
            if let Err(e) = rt.query_native(h, &system, false, &cfg).await {
                tracing::error!("[AGENT PAGE] Native query failed: {e}");
                let mut list = msgs.read().clone();
                list.push(ChatMessage::system(format!("⚠ {e}")));
                msgs.set(list);
                loading.set(false);
            }
        });
    };

    let (status_label, status_class) = match &agent_status {
        AgentStatus::Unavailable => ("No LLM key", "agent-status-unavailable"),
        AgentStatus::Starting    => ("Starting…",  "agent-status-starting"),
        AgentStatus::Ready       => ("Ready",       "agent-status-ready"),
        AgentStatus::Error(_)    => ("Error",       "agent-status-error"),
    };

    rsx! {
        div { class: "page page-agent",
            // ── Header ────────────────────────────────────────────────────────
            div { class: "agent-header",
                div { class: "agent-title-row",
                    h1 { class: "page-title", "Agent" }
                    span { class: "agent-status-badge {status_class}", "{status_label}" }
                }
                p { class: "page-subtitle",
                    "Omi AI agent with full context awareness — conversations, memories, screen activity."
                }
                if matches!(agent_status, AgentStatus::Unavailable) {
                    div { class: "agent-unavailable-hint",
                        "⚠ No LLM API key configured. Add an OpenAI or Groq key in Settings → API Keys to use the Agent."
                    }
                }
            }

            // ── Message list ──────────────────────────────────────────────────
            div { class: "agent-messages", id: "agent-messages",
                if messages.read().is_empty() {
                    div { class: "agent-empty",
                        div { class: "agent-empty-icon", "🤖" }
                        p { "Ask Omi anything. It knows your conversations, memories, and what's on your screen." }
                        div { class: "agent-starter-chips",
                            button {
                                class: "chip",
                                onclick: move |_| send_message("What should I focus on today based on my recent conversations?".into()),
                                "What to focus on today?"
                            }
                            button {
                                class: "chip",
                                onclick: move |_| send_message("Show me all pending action items and help me prioritize them.".into()),
                                "Prioritize my tasks"
                            }
                            button {
                                class: "chip",
                                onclick: move |_| send_message("Summarize everything I've talked about in the last 24 hours.".into()),
                                "Summarize last 24h"
                            }
                            button {
                                class: "chip",
                                onclick: move |_| send_message("What important things should I remember based on my memories?".into()),
                                "Key things to remember"
                            }
                        }
                    }
                } else {
                    for msg in messages.read().clone() {
                        {
                            let msg_id = msg.id.clone();
                            match &msg.role {
                                MessageRole::User => rsx! {
                                    div { class: "agent-msg agent-msg-user", key: "{msg_id}",
                                        div { class: "agent-bubble agent-bubble-user",
                                            "{msg.text}"
                                        }
                                    }
                                },
                                MessageRole::Agent => rsx! {
                                    div { class: "agent-msg agent-msg-agent", key: "{msg_id}",
                                        div { class: "agent-avatar", "Ω" }
                                        div { class: "agent-bubble-wrap",
                                            div {
                                                class: if msg.is_streaming {
                                                    "agent-bubble agent-bubble-agent streaming"
                                                } else {
                                                    "agent-bubble agent-bubble-agent"
                                                },
                                                "{msg.text}"
                                                if msg.is_streaming {
                                                    span { class: "agent-cursor", "▌" }
                                                }
                                            }
                                            if let Some((inp, out)) = msg.tokens {
                                                div { class: "agent-tokens",
                                                    "↑{inp} ↓{out} tokens"
                                                }
                                            }
                                        }
                                    }
                                },
                                MessageRole::Tool { name, .. } => rsx! {
                                    div { class: "agent-msg agent-msg-tool", key: "{msg_id}",
                                        details { class: "agent-tool-details",
                                            summary { class: "agent-tool-name",
                                                span { class: "tool-icon", "⚙" }
                                                " {name}"
                                            }
                                            pre { class: "agent-tool-input", "{msg.text}" }
                                        }
                                    }
                                },
                                MessageRole::SystemEvent(_) => rsx! {
                                    div { class: "agent-msg agent-msg-system", key: "{msg_id}",
                                        span { "{msg.text}" }
                                    }
                                },
                            }
                        }
                    }
                    if *is_loading.read() {
                        div { class: "agent-msg agent-msg-agent agent-thinking",
                            div { class: "agent-avatar", "Ω" }
                            div { class: "agent-thinking-dots",
                                span { class: "dot" }
                                span { class: "dot" }
                                span { class: "dot" }
                            }
                        }
                    }
                }
            }

            // ── Input bar ─────────────────────────────────────────────────────
            div { class: "agent-input-bar",
                if *is_loading.read() {
                    button {
                        class: "btn btn-secondary agent-stop-btn",
                        onclick: move |_| {
                            // For native mode: there is no running query to cancel (LLM calls
                            // are awaited to completion). Just mark as not loading.
                            is_loading.clone().set(false);
                        },
                        "■ Stop"
                    }
                }
                textarea {
                    class: "agent-input",
                    placeholder: "Ask Omi… (Enter to send, Shift+Enter for newline)",
                    value: "{input_text}",
                    rows: "1",
                    oninput: move |e| input_text.set(e.value()),
                    onkeydown: move |e| {
                        if e.key() == Key::Enter && !e.modifiers().shift() {
                            e.prevent_default();
                            let txt = input_text.read().trim().to_string();
                            send_message(txt);
                        }
                    },
                }
                button {
                    class: "btn btn-primary agent-send-btn",
                    disabled: *is_loading.read() || input_text.read().trim().is_empty(),
                    onclick: move |_| {
                        let txt = input_text.read().trim().to_string();
                        send_message(txt);
                    },
                    "Send"
                }
                button {
                    class: "btn btn-secondary",
                    title: "Clear conversation",
                    onclick: move |_| {
                        messages.set(Vec::new());
                        history.set(Vec::new());
                    },
                    "✕"
                }
            }
        }
    }
}
