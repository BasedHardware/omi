/// Context Watcher — analyzes screen content and emits proactive suggestions.
///
/// Runs a background loop that:
///   1. Reads the latest screenshot + OCR text from the DB
///   2. Classifies the active context (email, code, document, browser, other)
///   3. Sends a targeted LLM prompt for that context type
///   4. If the LLM finds something noteworthy, emits a ProactiveEvent::NewSuggestion
///      AND sends a Windows Toast notification
///
/// Context types and their analysis:
///   Email   → Tone formality check (too casual? informal greeting? unclear ask?)
///   IDE     → Obvious bugs, TODOs, forgotten error handling
///   Browser → Summarize topic for memory (passive, low priority)
///   Doc     → Grammar, clarity, structural suggestions
///   Other   → Generic "what are you working on" every 5min
///
/// Cooldown: 60 seconds per context category to avoid spam.

use std::collections::HashMap;
use std::time::{Duration, Instant};

use tokio::time::interval;
use tracing::{info, warn};

use crate::config::AppConfig;
use crate::proactive::{ProactiveEngine, ProactiveEvent, Suggestion};

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum ContextKind {
    Email,
    Code,
    Browser,
    Document,
    Meeting,
    Other,
}

impl ContextKind {
    /// Classify based on window title + OCR text.
    pub fn classify(window_title: &str, ocr_text: &str) -> Self {
        let title_lower = window_title.to_lowercase();
        let ocr_lower = ocr_text.to_lowercase();

        // Email clients
        if title_lower.contains("gmail")
            || title_lower.contains("outlook")
            || title_lower.contains("mail")
            || title_lower.contains("thunderbird")
            || ocr_lower.contains("compose")
            || ocr_lower.contains("new message")
            || ocr_lower.contains("reply")
            || ocr_lower.contains("subject:")
            || ocr_lower.contains("to:")
        {
            return ContextKind::Email;
        }

        // Code editors / IDEs
        if title_lower.contains("visual studio code")
            || title_lower.contains("vs code")
            || title_lower.contains("vscode")
            || title_lower.contains("rider")
            || title_lower.contains("intellij")
            || title_lower.contains("pycharm")
            || title_lower.contains("webstorm")
            || title_lower.contains("android studio")
            || title_lower.contains(".rs")
            || title_lower.contains(".py")
            || title_lower.contains(".ts")
            || title_lower.contains(".js")
            || ocr_lower.contains("fn main")
            || ocr_lower.contains("def ")
            || ocr_lower.contains("import ")
            || ocr_lower.contains("function ")
        {
            return ContextKind::Code;
        }

        // Browsers
        if title_lower.contains("chrome")
            || title_lower.contains("firefox")
            || title_lower.contains("edge")
            || title_lower.contains("brave")
            || title_lower.contains("safari")
            || title_lower.contains("opera")
        {
            return ContextKind::Browser;
        }

        // Documents
        if title_lower.contains("word")
            || title_lower.contains("notion")
            || title_lower.contains("obsidian")
            || title_lower.contains("notepad")
            || title_lower.contains("docs")
            || title_lower.contains(".docx")
            || title_lower.contains(".txt")
            || title_lower.contains(".md")
        {
            return ContextKind::Document;
        }

        // Meeting apps
        if title_lower.contains("zoom")
            || title_lower.contains("teams")
            || title_lower.contains("meet")
            || title_lower.contains("webex")
        {
            return ContextKind::Meeting;
        }

        ContextKind::Other
    }

    pub fn display_name(&self) -> &str {
        match self {
            ContextKind::Email => "email",
            ContextKind::Code => "code",
            ContextKind::Browser => "browser",
            ContextKind::Document => "document",
            ContextKind::Meeting => "meeting",
            ContextKind::Other => "screen",
        }
    }
}

/// Build a targeted LLM prompt for the given context.
fn build_analysis_prompt(kind: &ContextKind, window_title: &str, ocr_text: &str) -> String {
    let content_preview = &ocr_text[..ocr_text.len().min(1200)];

    match kind {
        ContextKind::Email => format!(
            r#"You are Omi, an AI companion watching the user's screen.
The user appears to be composing or reading an email.

Window: "{window_title}"
Visible text on screen:
---
{content_preview}
---

Analyze the email content visible on screen. Check for:
1. Tone issues (too casual, too formal, aggressive, unclear)
2. Missing context or unclear requests
3. Grammar or spelling errors
4. Any red flags (e.g., about to send sensitive info)

If you find a meaningful issue, respond with a SHORT one-sentence observation starting with "⚠️ " or "💡 ".
If everything looks fine, respond with exactly: OK
Only respond with either "OK" or the one-sentence observation. Nothing else."#
        ),

        ContextKind::Code => format!(
            r#"You are Omi, an AI companion watching the user's screen.
The user is writing code.

Window: "{window_title}"
Visible code:
---
{content_preview}
---

Briefly scan the visible code. Check for:
1. Obvious bugs (unchecked errors, null dereferences, off-by-ones)
2. Large TODO/FIXME comments that seem important
3. Missing error handling in critical paths

If you spot something meaningful, respond with a SHORT one-sentence note starting with "💡 " or "⚠️ ".
If the code looks fine, respond with exactly: OK
Only respond with "OK" or the one-sentence note. Nothing else."#
        ),

        ContextKind::Document => format!(
            r#"You are Omi, an AI companion watching the user's screen.
The user is writing a document.

Window: "{window_title}"
Visible text:
---
{content_preview}
---

Check for:
1. Run-on sentences or unclear paragraphs
2. Structural issues (missing heading, abrupt ending)
3. Inconsistent tone

If you find a meaningful suggestion, respond with a SHORT one-sentence tip starting with "💡 ".
If everything looks good, respond with exactly: OK
Only respond with "OK" or the one-sentence tip. Nothing else."#
        ),

        ContextKind::Browser => format!(
            r#"You are Omi, an AI companion watching the user's screen.
The user is browsing the web.

Window: "{window_title}"
Page content snippet:
---
{content_preview}
---

In one very short phrase, describe what the user is currently looking at (e.g. "Reading about Rust async" or "Shopping on Amazon").
This will be saved as a memory for context. Keep it under 10 words. No punctuation at end."#
        ),

        ContextKind::Meeting => {
            // During meetings, don't suggest anything unless there's an obvious agenda
            "OK".to_string()
        }

        ContextKind::Other => {
            // For unknown contexts, just return OK — we don't want false positives
            "OK".to_string()
        }
    }
}

/// Main context watcher loop. Call this in a background tokio task.
pub async fn run_context_watcher(
    db: omi_db::Database,
    proactive: ProactiveEngine,
    cfg_provider: impl Fn() -> AppConfig + Send + 'static,
) {
    info!("[CTX] Context watcher started");

    let mut cooldowns: HashMap<ContextKind, Instant> = HashMap::new();
    let cooldown_duration = Duration::from_secs(60);

    // Wait a bit before first check so the app is settled
    tokio::time::sleep(Duration::from_secs(10)).await;

    let mut tick = interval(Duration::from_secs(15));

    loop {
        tick.tick().await;

        let cfg = cfg_provider();
        if !cfg.context_watcher_enabled {
            continue;
        }

        // Set the tick interval from config
        let interval_secs = cfg.context_watcher_interval_secs.max(10).min(300);

        // Fetch the latest screenshot from DB
        let screenshots = match db.list_screenshots(1) {
            Ok(s) => s,
            Err(e) => {
                warn!("[CTX] DB fetch error: {e:#}");
                continue;
            }
        };
        let screenshot = match screenshots.into_iter().next() {
            Some(s) => s,
            None => continue,
        };

        let window_title = screenshot.window_title.as_deref().unwrap_or("");
        let ocr_text = screenshot.ocr_text.as_deref().unwrap_or("");

        if ocr_text.len() < 50 {
            // Not enough content to analyze
            continue;
        }

        let kind = ContextKind::classify(window_title, ocr_text);

        // Check cooldown
        if let Some(last) = cooldowns.get(&kind) {
            if last.elapsed() < cooldown_duration {
                continue;
            }
        }

        info!("[CTX] Analyzing context: {:?} (window: {window_title})", kind);

        // Build and run the analysis prompt
        let prompt = build_analysis_prompt(&kind, window_title, ocr_text);

        // Skip pre-canned "OK" prompts (Meeting, Other)
        if prompt == "OK" {
            continue;
        }

        let analysis_result = run_analysis(&prompt, &cfg).await;

        match analysis_result {
            Some(result) if result.trim() == "OK" || result.trim().is_empty() => {
                info!("[CTX] No issue found in {:?} context", kind);
            }
            Some(result) => {
                info!("[CTX] Issue found: {result}");

                // Update cooldown
                cooldowns.insert(kind.clone(), Instant::now());

                let priority: u8 = if result.starts_with("⚠️") { 85 } else { 60 };

                // Emit proactive suggestion (speech bubble)
                let suggestion = Suggestion {
                    id: uuid::Uuid::new_v4().to_string(),
                    text: result.clone(),
                    action_label: match &kind {
                        ContextKind::Email => "Review Email",
                        ContextKind::Code => "Explain",
                        ContextKind::Document => "Improve",
                        _ => "Tell me more",
                    }
                    .to_string(),
                    agent_prompt: Some(format!(
                        "I'm currently working on a {} and I noticed: {}. Can you help me address this?",
                        kind.display_name(),
                        result
                    )),
                    priority,
                    created_at: std::time::Instant::now(),
                    ttl: Duration::from_secs(120),
                };

                let _ = proactive.tx.send(ProactiveEvent::NewSuggestion(suggestion));

                // Send Windows Toast notification
                if cfg.proactive_toast_notifications {
                    crate::notifications::send_suggestion(&result, priority);
                }

                // For browser context, save as memory (passive)
                if kind == ContextKind::Browser && !result.starts_with("⚠️") {
                    if let Err(e) = db.insert_memory(None, &result, Some("screen_context")) {
                        warn!("[CTX] Failed to save browser memory: {e:#}");
                    } else {
                        let backend_url = cfg.backend_url.clone();
                        let token = cfg.firebase_id_token.clone();
                        let c_content = result.clone();
                        let c_category = "screen_context".to_string();
                        tokio::spawn(async move {
                            crate::sync::upload_memory(backend_url, token, c_content, c_category).await;
                        });
                    }
                }
            }
            None => {
                warn!("[CTX] Analysis returned None — LLM call failed");
            }
        }

        // Adjust tick interval dynamically
        let _ = interval_secs; // used via cfg; tick already set at 15s default
    }
}

/// Call the local LLM to analyze the screen context.
async fn run_analysis(prompt: &str, cfg: &AppConfig) -> Option<String> {
    // Use the existing llm module's complete_streaming function
    let messages = vec![
        crate::llm::LlmMessage {
            role: "system".to_string(),
            content: "You are a brief screen-watching AI assistant. Follow the user's exact instructions about response format.".to_string(),
        },
        crate::llm::LlmMessage {
            role: "user".to_string(),
            content: prompt.to_string(),
        },
    ];

    // Accumulate all tokens
    let collected = std::sync::Arc::new(std::sync::Mutex::new(String::new()));
    let collected_clone = collected.clone();

    match crate::llm::complete_streaming(
        cfg,
        crate::llm::LlmUseCase::Background,
        messages,
        Some(150),
        move |token| {
            if let Ok(mut s) = collected_clone.lock() {
                s.push_str(&token);
            }
        },
    ).await {
        Ok(text) => Some(text.trim().to_string()),
        Err(e) => {
            warn!("[CTX] LLM analysis failed: {e:#}");
            None
        }
    }
}
