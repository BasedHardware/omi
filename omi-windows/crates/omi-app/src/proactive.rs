/// Proactive assistant engine — monitors context signals and generates
/// time-aware, context-aware suggestions that appear as pills in the
/// floating control bar.
///
/// Trigger sources (checked in priority order):
///   1. Conversation just ended  → suggest summary review, related tasks
///   2. Idle time (no keystrokes/audio for N minutes) → surface pending tasks
///   3. Screen OCR delta         → if new meaningful content appears
///   4. Scheduled (every M min) → generic "you have N pending tasks" reminder
///
/// Each suggestion has a priority score, dedup key (so the same tip is
/// never shown twice in a row), and a TTL after which it is removed.

use std::time::{Duration, Instant};

use tokio::sync::broadcast;
use uuid::Uuid;

use crate::agent_runtime::AgentRuntime;
use crate::config::AppConfig;

// ── Public types ──────────────────────────────────────────────────────────────

/// A single proactive suggestion shown in the floating bar / pill strip.
#[derive(Debug, Clone)]
pub struct Suggestion {
    pub id: String,
    pub text: String,
    /// Short action label shown on the pill button ("Review", "Ask", "Open Tasks"…)
    pub action_label: String,
    /// What to send to the agent when the user taps the pill.
    pub agent_prompt: Option<String>,
    /// Priority 0–100; higher floats to front.
    pub priority: u8,
    pub created_at: Instant,
    pub ttl: Duration,
}

impl Suggestion {
    pub fn is_expired(&self) -> bool {
        self.created_at.elapsed() > self.ttl
    }
}

/// The event channel type sent by the engine.
#[derive(Debug, Clone)]
#[allow(dead_code)]
pub enum ProactiveEvent {
    NewSuggestion(Suggestion),
    /// Remove a suggestion by id (e.g. user dismissed, or TTL expired).
    Dismiss(String),
    /// Clear all suggestions.
    ClearAll,
}

// ── Engine ────────────────────────────────────────────────────────────────────

pub struct ProactiveEngine {
    pub tx: broadcast::Sender<ProactiveEvent>,
}

impl ProactiveEngine {
    pub fn new() -> (Self, broadcast::Receiver<ProactiveEvent>) {
        let (tx, rx) = broadcast::channel(64);
        (Self { tx }, rx)
    }

    /// Notify that a recording session just ended.
    /// Triggers immediate context-based suggestions.
    pub async fn on_conversation_ended(
        &self,
        db: &omi_db::Database,
        conversation_id: &str,
        cfg: &AppConfig,
        runtime: &AgentRuntime,
    ) {
        tracing::info!("[PROACTIVE] Conversation ended: {conversation_id}");

        // 1. Action-item reminder
        if let Ok(items) = db.list_action_items(100) {
            let pending = items.iter().filter(|i| !i.completed).count();
            if pending > 0 {
                let s = self.make_suggestion(
                    format!("You have {pending} pending task{}.", if pending == 1 { "" } else { "s" }),
                    "Review Tasks",
                    Some("Show me my pending action items and help me prioritize them.".into()),
                    70,
                    Duration::from_secs(300),
                );
                let _ = self.tx.send(ProactiveEvent::NewSuggestion(s));
            }
        }

        // 2. Summary suggestion
        let s = self.make_suggestion(
            "Conversation recorded. Want a smart summary?".into(),
            "Summarize",
            Some(format!(
                "I just finished a conversation (id: {conversation_id}). \
                Please give me a concise, insightful summary of the key points, decisions made, \
                and any follow-ups I should track."
            )),
            80,
            Duration::from_secs(600),
        );
        let _ = self.tx.send(ProactiveEvent::NewSuggestion(s));

        // 3. Ask the agent to proactively surface anything relevant from memories
        if cfg.proactive_agent_enabled {
            if let Ok(memories_text) = db.get_memories_text(10) {
                if !memories_text.is_empty() {
                    let prompt = format!(
                        "Based on recent conversation (id: {conversation_id}) and these long-term memories:\n\
                        {memories_text}\n\n\
                        Surface ONE short proactive insight or reminder that would be immediately useful. \
                        Be specific. If nothing actionable, respond with exactly: NOTHING"
                    );
                    // Fire-and-forget: runtime will send events to its own broadcast
                    let runtime = runtime.clone();
                    let (api_key, url, model) = crate::llm::resolve_llm_endpoint(cfg);
                    if !api_key.is_empty() {
                        tokio::spawn(async move {
                            match crate::llm::complete(
                                &api_key,
                                &url,
                                &model,
                                vec![crate::llm::LlmMessage { role: "user".into(), content: prompt }],
                                Some(150),
                            ).await {
                                Ok(text) => {
                                    let text = text.trim();
                                    if !text.is_empty() && text != "NOTHING" {
                                        tracing::info!("[PROACTIVE] Memory-based insight: {text}");
                                        // Surface as a query to the agent so the user can follow up
                                        let _ = runtime.query(text, None, None).await;
                                    }
                                }
                                Err(e) => tracing::warn!("[PROACTIVE] LLM insight failed: {e}"),
                            }
                        });
                    }
                }
            }
        }
    }

    /// Called periodically (every few minutes) to surface idle reminders.
    pub async fn on_tick(&self, db: &omi_db::Database, _cfg: &AppConfig) {
        // Pending tasks reminder (only if any)
        if let Ok(items) = db.list_action_items(100) {
            let now = chrono::Utc::now();
            let overdue: Vec<_> = items.iter()
                .filter(|i| !i.completed)
                .filter(|i| {
                    (now - i.created_at).num_seconds() > 3600
                })
                .collect();

            if !overdue.is_empty() {
                let s = self.make_suggestion(
                    format!("{} tasks have been waiting over an hour.", overdue.len()),
                    "Work on Tasks",
                    Some("Show me overdue tasks and suggest which to tackle first.".into()),
                    50,
                    Duration::from_secs(900),
                );
                let _ = self.tx.send(ProactiveEvent::NewSuggestion(s));
            }
        }
    }

    /// Called when new OCR text is captured (significant content detected).
    #[allow(dead_code)]
    pub fn on_screen_content(&self, window_title: &str, ocr_summary: &str) {
        // Only surface if the OCR summary mentions something actionable
        let triggers = ["deadline", "todo", "follow up", "remind", "meeting", "error", "urgent"];
        let lower = ocr_summary.to_lowercase();
        if triggers.iter().any(|t| lower.contains(t)) {
            let s = self.make_suggestion(
                format!("Noticed something in '{}' — want to capture it?", window_title),
                "Capture",
                Some(format!(
                    "I was just looking at {window_title}. The screen showed: {ocr_summary}\n\
                    Extract any important information, tasks, or deadlines and help me capture them."
                )),
                60,
                Duration::from_secs(120),
            );
            let _ = self.tx.send(ProactiveEvent::NewSuggestion(s));
        }
    }

    fn make_suggestion(
        &self,
        text: String,
        action_label: &str,
        agent_prompt: Option<String>,
        priority: u8,
        ttl: Duration,
    ) -> Suggestion {
        Suggestion {
            id: Uuid::new_v4().to_string(),
            text,
            action_label: action_label.to_string(),
            agent_prompt,
            priority,
            created_at: Instant::now(),
            ttl,
        }
    }
}

// ── Background ticker task ────────────────────────────────────────────────────

/// Spawn the background idle-tick task (runs every `tick_mins` minutes).
pub fn spawn_tick_task(
    engine: std::sync::Arc<ProactiveEngine>,
    db: omi_db::Database,
    _cfg: AppConfig,
    tick_mins: u64,
) {
    tokio::spawn(async move {
        let interval = Duration::from_secs(tick_mins * 60);
        loop {
            tokio::time::sleep(interval).await;
            // Reload config each tick so Settings changes take effect
            let current_cfg = AppConfig::load();
            if current_cfg.proactive_agent_enabled {
                engine.on_tick(&db, &current_cfg).await;
            }
        }
    });
}
