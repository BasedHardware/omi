/// Agent runtime — manages the Node.js agent process and bidirectional JSON-lines IPC.
///
/// Architecture:
///   Rust app  ──stdin──►  Node.js agent  ──stdout──►  Rust app
///
/// The protocol is the same JSON-lines wire format used by the macOS swift app
/// (defined in desktop/agent/src/protocol.ts).  We speak a simplified subset:
///
///   Outbound (Rust → Node):
///     {"type":"query", "id":"<uuid>", "prompt":"...", "systemPrompt":"...", "sessionKey":"default"}
///     {"type":"warmup", "sessions":[{"key":"default","model":"<model>"}]}
///     {"type":"stop"}
///
///   Inbound (Node → Rust):
///     {"type":"init",       "sessionId":"..."}
///     {"type":"text_delta", "text":"..."}
///     {"type":"tool_use",   "callId":"...", "name":"...", "input":{}}
///     {"type":"result",     "text":"...", "sessionId":"...", "inputTokens":N, "outputTokens":N}
///     {"type":"error",      "message":"..."}

use std::process::Stdio;
use std::sync::Arc;

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, Command};
use tokio::sync::{broadcast, Mutex, RwLock};

// ── Wire types ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum AgentRequest {
    Query {
        id: String,
        prompt: String,
        #[serde(rename = "systemPrompt")]
        system_prompt: String,
        #[serde(rename = "sessionKey")]
        session_key: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        model: Option<String>,
    },
    Warmup {
        sessions: Vec<WarmupSession>,
    },
    Stop,
}

#[derive(Debug, Clone, Serialize)]
pub struct WarmupSession {
    pub key: String,
    pub model: String,
    #[serde(rename = "systemPrompt", skip_serializing_if = "Option::is_none")]
    pub system_prompt: Option<String>,
}

/// Events flowing from the agent back to the Rust app.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum AgentEvent {
    Init {
        #[serde(rename = "sessionId")]
        session_id: String,
    },
    TextDelta {
        text: String,
    },
    ToolUse {
        #[serde(rename = "callId")]
        call_id: String,
        name: String,
        input: serde_json::Value,
    },
    Result {
        text: String,
        #[serde(rename = "sessionId")]
        session_id: String,
        #[serde(rename = "inputTokens", default)]
        input_tokens: u32,
        #[serde(rename = "outputTokens", default)]
        output_tokens: u32,
    },
    Error {
        message: String,
    },
    AuthRequired {
        methods: Vec<serde_json::Value>,
    },
    HitlRequest {
        #[serde(rename = "threadId")]
        thread_id: String,
        message: String,
    },
}

// ── Process state ─────────────────────────────────────────────────────────────

#[derive(Clone, PartialEq, Debug)]
pub enum AgentStatus {
    /// No Node.js found or agent disabled.
    Unavailable,
    /// Process is starting / warming up.
    Starting,
    /// Process running, session warmed.
    Ready,
    /// An error occurred; message included.
    Error(String),
}

struct AgentProcess {
    child: Child,
    stdin: Arc<Mutex<ChildStdin>>,
}

/// Shared, cloneable handle to the agent runtime.
#[derive(Clone)]
pub struct AgentRuntime {
    inner: Arc<AgentRuntimeInner>,
}

struct AgentRuntimeInner {
    /// Broadcast all agent events to any subscriber (UI, proactive engine…).
    pub event_tx: broadcast::Sender<AgentEvent>,
    pub status: RwLock<AgentStatus>,
    process: Mutex<Option<AgentProcess>>,
}

impl AgentRuntime {
    pub fn new() -> Self {
        let (event_tx, _) = broadcast::channel(256);
        Self {
            inner: Arc::new(AgentRuntimeInner {
                event_tx,
                status: RwLock::new(AgentStatus::Unavailable),
                process: Mutex::new(None),
            }),
        }
    }

    pub fn subscribe(&self) -> broadcast::Receiver<AgentEvent> {
        self.inner.event_tx.subscribe()
    }

    /// Run a query using the **native LLM HTTP backend** — no Node.js required.
    ///
    /// This is the primary path for the Windows app: it calls the configured
    /// LLM endpoint directly and emits `AgentEvent`s on the broadcast channel
    /// so the UI reacts identically to the Node.js path.
    ///
    /// The conversation `history` is passed in as `(role, content)` pairs so
    /// the model has full context.
    pub async fn query_native(
        &self,
        messages: Vec<(String, String)>, // (role, content) — full history
        system_prompt: &str,
        cfg: &crate::config::AppConfig,
    ) -> Result<()> {
        let session_id = uuid::Uuid::new_v4().to_string();
        let _ = self.inner.event_tx.send(AgentEvent::Init { session_id: session_id.clone() });

        // ── MCP bridge: delegate Google-intent queries to the MCP backend ────────
        let user_query = messages.last().map(|(_, c)| c.as_str()).unwrap_or("");
        let mcp_context_text = if cfg.mcp_enabled && crate::mcp_bridge::is_google_query(user_query) {
            tracing::info!("[AGENT] Detected Google intent — routing to MCP backend");
            match crate::mcp_bridge::query_mcp(user_query, cfg).await {
                Some(crate::mcp_bridge::McpResponse::HitlRequest { thread_id, message }) => {
                    // It requires confirmation. Emit event and yield early.
                    let _ = self.inner.event_tx.send(AgentEvent::HitlRequest { thread_id, message });
                    return Ok(());
                }
                Some(crate::mcp_bridge::McpResponse::Text(text)) => Some(text),
                None => None,
            }
        } else {
            None
        };

        // ── Knowledge base: always query when MCP is enabled (cheap localhost call) ──
        let knowledge_context = if cfg.mcp_enabled {
            tracing::info!("[AGENT] Searching knowledge base for context");
            match crate::knowledge::search_knowledge(user_query, cfg).await {
                Ok(results) if !results.is_empty() => {
                    let mut kb = String::from("## Relevant Knowledge Base Documents\n");
                    for r in &results {
                        let src = r.source.as_deref().unwrap_or("unknown");
                        kb.push_str(&format!("- [from {src}] {}\n", r.content));
                    }
                    Some(kb)
                }
                Ok(_) => None,
                Err(e) => {
                    tracing::debug!("[AGENT] KB search unavailable: {e}");
                    None
                }
            }
        } else {
            None
        };

        // ── Web search via Tavily ───────────────────────────────────────────────
        let web_context = if cfg.web_search_enabled
            && !cfg.tavily_api_key.is_empty()
            && crate::web_search::needs_web_search(user_query, cfg).await
        {
            tracing::info!("[AGENT] LLM decided web search needed — querying Tavily");
            match crate::web_search::search(user_query, cfg).await {
                Ok(resp) => Some(crate::web_search::format_search_context(&resp)),
                Err(e) => {
                    tracing::warn!("[AGENT] Web search failed: {e:#}");
                    None
                }
            }
        } else {
            None
        };

        // Extend the system prompt with MCP + knowledge + web context
        let mut extended_system_prompt = system_prompt.to_string();
        if let Some(ref mcp_result) = mcp_context_text {
            extended_system_prompt.push_str(&format!(
                "\n\n## Google Workspace Data (just retrieved)\n{mcp_result}\n\nUse the above data to answer the user's question naturally and concisely."
            ));
        }
        if let Some(ref kb) = knowledge_context {
            extended_system_prompt.push_str(&format!("\n\n{kb}\n\nUse the above knowledge base results to answer accurately."));
        }
        if let Some(ref web) = web_context {
            extended_system_prompt.push_str(&format!("\n\n{web}\n\nUse the above web search results to provide an accurate, up-to-date answer. Cite sources when possible."));
        }

        // Build message list: system prompt first, then conversation history
        let mut llm_messages = vec![crate::llm::LlmMessage {
            role: "system".into(),
            content: extended_system_prompt,
        }];
        for (role, content) in &messages {
            llm_messages.push(crate::llm::LlmMessage { role: role.clone(), content: content.clone() });
        }

        tracing::info!("[AGENT native] Calling LLM streaming: turns={}", llm_messages.len());

        // Real SSE streaming — tokens arrive as they are generated
        let event_tx = self.inner.event_tx.clone();
        let response = match crate::llm::complete_streaming(
            cfg,
            crate::llm::LlmUseCase::Chat,
            llm_messages,
            Some(1200),
            move |token| {
                let _ = event_tx.send(AgentEvent::TextDelta { text: token });
            },
        ).await {
            Ok(res) => res,
            Err(e) => {
                let err_msg = format!("LLM failed: {e}");
                let _ = self.inner.event_tx.send(AgentEvent::Error { message: err_msg.clone() });
                return Err(anyhow::anyhow!(err_msg));
            }
        };

        let output_tokens = response.split_whitespace().count() as u32;
        let _ = self.inner.event_tx.send(AgentEvent::Result {
            text: response,
            session_id,
            input_tokens: 0,
            output_tokens,
        });

        Ok(())
    }

    /// Complete an ongoing HITL confirmation
    pub async fn confirm_mcp_hitl(&self, thread_id: &str, user_response: &str, cfg: &crate::config::AppConfig) -> Result<()> {
        let session_id = uuid::Uuid::new_v4().to_string();
        let _ = self.inner.event_tx.send(AgentEvent::Init { session_id: session_id.clone() });

        match crate::mcp_bridge::confirm_mcp(thread_id, user_response, cfg).await {
            Some(crate::mcp_bridge::McpResponse::HitlRequest { thread_id, message }) => {
                let _ = self.inner.event_tx.send(AgentEvent::HitlRequest { thread_id, message });
            }
            Some(crate::mcp_bridge::McpResponse::Text(text)) => {
                // Return result to the UI
                let _ = self.inner.event_tx.send(AgentEvent::Result {
                    text,
                    session_id,
                    input_tokens: 0,
                    output_tokens: 0,
                });
            }
            None => {
                let _ = self.inner.event_tx.send(AgentEvent::Error {
                    message: "Failed to confirm action via MCP.".to_string(),
                });
            }
        }
        Ok(())
    }

    /// Start the Node.js agent process.  Idempotent — returns early if already running.
    pub async fn start(&self, node_path: &str, agent_script: &str, model: Option<&str>) -> Result<()> {
        let mut proc_guard = self.inner.process.lock().await;
        if proc_guard.is_some() {
            return Ok(());
        }

        tracing::info!("[AGENT] Starting Node.js agent: {node_path} {agent_script}");
        *self.inner.status.write().await = AgentStatus::Starting;

        let mut child = Command::new(node_path)
            .arg(agent_script)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .with_context(|| format!("Failed to spawn agent: {node_path} {agent_script}"))?;

        let stdin = child.stdin.take().context("No stdin")?;
        let stdout = child.stdout.take().context("No stdout")?;
        let stderr = child.stderr.take().context("No stderr")?;

        let stdin = Arc::new(Mutex::new(stdin));

        // Stderr logger
        let stderr_task = {
            let mut reader = BufReader::new(stderr).lines();
            tokio::spawn(async move {
                while let Ok(Some(line)) = reader.next_line().await {
                    tracing::debug!("[AGENT stderr] {line}");
                }
            })
        };

        // Stdout event reader — broadcasts to all subscribers
        let event_tx = self.inner.event_tx.clone();
        // Clone the inner Arc so the reader task can update status
        let status_outer = Arc::clone(&self.inner);
        let reader_task = {
            let mut reader = BufReader::new(stdout).lines();
            tokio::spawn(async move {
                while let Ok(Some(line)) = reader.next_line().await {
                    if line.trim().is_empty() {
                        continue;
                    }
                    match serde_json::from_str::<AgentEvent>(&line) {
                        Ok(event) => {
                            tracing::debug!("[AGENT ←] {line}");
                            // When agent is ready (first result or init), mark status
                            if matches!(event, AgentEvent::Init { .. }) {
                                *status_outer.status.write().await = AgentStatus::Ready;
                            }
                            let _ = event_tx.send(event);
                        }
                        Err(e) => {
                            tracing::warn!("[AGENT] Unknown line (parse error: {e}): {}", &line[..line.len().min(200)]);
                        }
                    }
                }
                tracing::warn!("[AGENT] stdout reader ended — process likely exited");
                *status_outer.status.write().await = AgentStatus::Error("Agent process exited".into());
            })
        };

        // Warmup signal
        {
            let stdin_ref = Arc::clone(&stdin);
            let model_str = model.unwrap_or("gpt-4o-mini").to_string();
            let warmup = AgentRequest::Warmup {
                sessions: vec![WarmupSession {
                    key: "default".into(),
                    model: model_str,
                    system_prompt: Some(build_system_prompt()),
                }],
            };
            self.write_json(&stdin_ref, &warmup).await.ok();
        }

        *proc_guard = Some(AgentProcess {
            child,
            stdin: Arc::clone(&stdin),
        });

        // Keep stderr task alive by storing handle (drop silently on stop)
        drop(stderr_task);
        drop(reader_task);

        Ok(())
    }

    /// Send a query to the agent and return the query ID.
    pub async fn query(
        &self,
        prompt: &str,
        system_prompt: Option<&str>,
        model: Option<&str>,
    ) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string();
        let req = AgentRequest::Query {
            id: id.clone(),
            prompt: prompt.to_string(),
            system_prompt: system_prompt
                .unwrap_or_default()
                .to_string(),
            session_key: "default".into(),
            model: model.map(str::to_string),
        };

        let proc_guard = self.inner.process.lock().await;
        if let Some(ref proc) = *proc_guard {
            self.write_json(&proc.stdin, &req).await?;
            tracing::info!("[AGENT →] query id={id}");
        } else {
            anyhow::bail!("Agent process not running");
        }
        Ok(id)
    }

    /// Stop the active query.
    pub async fn stop_query(&self) {
        let proc_guard = self.inner.process.lock().await;
        if let Some(ref proc) = *proc_guard {
            let _ = self.write_json(&proc.stdin, &AgentRequest::Stop).await;
        }
    }

    /// Kill the agent process entirely.
    pub async fn shutdown(&self) {
        let mut proc_guard = self.inner.process.lock().await;
        if let Some(mut p) = proc_guard.take() {
            let _ = p.child.kill().await;
            tracing::info!("[AGENT] Process killed");
        }
        *self.inner.status.write().await = AgentStatus::Unavailable;
    }

    async fn write_json<T: Serialize>(&self, stdin: &Arc<Mutex<ChildStdin>>, msg: &T) -> Result<()> {
        let mut line = serde_json::to_string(msg).context("serialize")?;
        line.push('\n');
        let mut guard = stdin.lock().await;
        guard.write_all(line.as_bytes()).await.context("write stdin")?;
        guard.flush().await.context("flush stdin")?;
        Ok(())
    }
}

/// Build the Omi system prompt that tells the agent about available context.
fn build_system_prompt() -> String {
    "You are Omi, a proactive AI assistant running on the user's Windows computer. \
    You have access to the user's conversation history, memories, action items, and \
    recent screen activity. Be concise, helpful, and proactive. \
    When the user asks something, use your context knowledge before asking clarifying questions. \
    Always format action items as clear, actionable tasks."
        .to_string()
}

// ── Convenience launcher ──────────────────────────────────────────────────────

/// Try to start the agent using `cfg`.  Returns `Ok(true)` if the agent was
/// started (or was already running), `Ok(false)` if Node/script not found.
pub async fn try_start_from_config(
    runtime: &AgentRuntime,
    cfg: &crate::config::AppConfig,
) -> anyhow::Result<bool> {
    // Already running — nothing to do
    if matches!(runtime.inner.status.read().await.clone(), AgentStatus::Starting | AgentStatus::Ready) {
        return Ok(true);
    }

    let node = if cfg.node_path.is_empty() {
        find_node()
    } else {
        Some(cfg.node_path.clone())
    };
    let script = if cfg.agent_script_path.is_empty() {
        find_agent_script()
    } else {
        Some(cfg.agent_script_path.clone())
    };

    let (Some(n), Some(s)) = (node, script) else {
        tracing::warn!("[AGENT] Cannot start: Node.js or agent script not found");
        return Ok(false);
    };

    let (_, _, model) = crate::llm::resolve_llm_endpoint(cfg);
    runtime.start(&n, &s, Some(&model)).await?;
    Ok(true)
}

// ── Node.js discovery ─────────────────────────────────────────────────────────

/// Find the Node.js executable on PATH or well-known install locations.
///
/// Search order:
/// 1. `where.exe node` — respects the user's full PATH including Volta, nvm, fnm, asdf
/// 2. Hard-coded common Windows install paths
pub fn find_node() -> Option<String> {
    // 1. Ask Windows where.exe — it sees the real user PATH even if we started without it
    if let Ok(out) = std::process::Command::new("where.exe").arg("node").output() {
        if out.status.success() {
            let stdout = String::from_utf8_lossy(&out.stdout);
            if let Some(first) = stdout.lines().next() {
                let path = first.trim().to_string();
                if !path.is_empty() {
                    tracing::info!("[AGENT] Found Node.js via where.exe: {path}");
                    return Some(path);
                }
            }
        }
    }

    // 2. Hard-coded common paths (Volta, nvm-windows, official installer, nvs, fnm)
    let appdata  = std::env::var("APPDATA").unwrap_or_default();
    let localapp = std::env::var("LOCALAPPDATA").unwrap_or_default();
    let progfiles = std::env::var("ProgramFiles").unwrap_or_default();

    let candidates = [
        // Volta (most common on developer machines)
        format!("{progfiles}\\Volta\\node.exe"),
        format!("{localapp}\\Volta\\node.exe"),
        // nvm-windows
        format!("{appdata}\\nvm\\current\\node.exe"),
        // Official MSI installer
        format!("{progfiles}\\nodejs\\node.exe"),
        r"C:\Program Files\nodejs\node.exe".to_string(),
        r"C:\Program Files (x86)\nodejs\node.exe".to_string(),
        // nvs
        format!("{localapp}\\nvs\\default\\node.exe"),
        // fnm
        format!("{localapp}\\fnm\\aliases\\default\\node.exe"),
        // Scoop
        format!("{}\\scoop\\shims\\node.exe", std::env::var("USERPROFILE").unwrap_or_default()),
        // Chocolatey
        r"C:\ProgramData\chocolatey\bin\node.exe".to_string(),
        // Bare name — last resort
        "node".to_string(),
    ];

    for candidate in &candidates {
        if candidate.is_empty() { continue; }
        if let Ok(out) = std::process::Command::new(candidate).arg("--version").output() {
            if out.status.success() {
                tracing::info!("[AGENT] Found Node.js at: {candidate}");
                return Some(candidate.clone());
            }
        }
    }

    tracing::warn!("[AGENT] Node.js not found. Set the path in Settings → Agent Runtime");
    None
}

/// Find the agent entry point (dist/index.js relative to the binary or workspace).
pub fn find_agent_script() -> Option<String> {
    let exe = std::env::current_exe().ok();
    let exe_dir = exe.as_ref().and_then(|p| p.parent());

    // Common repo root patterns (dev builds)
    let userprofile = std::env::var("USERPROFILE").unwrap_or_default();

    let mut candidates: Vec<std::path::PathBuf> = vec![
        // Next to binary
        exe_dir.map(|d| d.join("agent").join("dist").join("index.js"))
               .unwrap_or_default(),
        // Workspace-relative (cargo run from omi-windows/)
        std::path::PathBuf::from(r"C:\omi\desktop\agent\dist\index.js"),
        std::path::PathBuf::from(r"C:\omi\omi-windows\agent\dist\index.js"),
        // Home dir
        std::path::PathBuf::from(&userprofile).join("omi").join("agent").join("dist").join("index.js"),
    ];

    // Also scan env var OMI_AGENT_SCRIPT for CI / custom setups
    if let Ok(env_path) = std::env::var("OMI_AGENT_SCRIPT") {
        candidates.insert(0, std::path::PathBuf::from(env_path));
    }

    for c in &candidates {
        if c.as_os_str().is_empty() { continue; }
        if c.exists() {
            tracing::info!("[AGENT] Found agent script at: {}", c.display());
            return Some(c.to_string_lossy().into_owned());
        }
    }

    tracing::warn!(
        "[AGENT] Agent script not found. Build it: cd c:\\omi\\desktop\\agent && npm run build. \
        Then set the path in Settings → Agent Runtime."
    );
    None
}
