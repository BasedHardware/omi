use chrono::Utc;
use tracing::{info, warn};

use crate::config::AppConfig;
use crate::llm::{LlmMessage, LlmUseCase};

pub async fn generate_daily_recap(db: &omi_db::Database, cfg: &AppConfig) -> Option<String> {
    let today = Utc::now().format("%Y-%m-%d").to_string();

    // Check if we already have a recap for today
    if let Ok(Some(_)) = db.get_recap_for_date(&today) {
        info!("[RECAP] Already have recap for {today}");
        return None;
    }

    let stats = match db.get_today_stats() {
        Ok(s) => s,
        Err(e) => {
            warn!("[RECAP] Failed to get today's stats: {e:#}");
            return None;
        }
    };

    // Get today's memories for context
    let memories_text = db.get_memories_text(20).unwrap_or_default();

    // Get recent clipboard items for context
    let clipboard_text = db.get_clipboard_text(10).unwrap_or_default();

    let apps_list = stats
        .apps_used
        .iter()
        .take(10)
        .map(|a| {
            let short = if a.len() > 40 {
                format!("{}…", &a[..40])
            } else {
                a.clone()
            };
            format!("  - {short}")
        })
        .collect::<Vec<_>>()
        .join("\n");

    let prompt = format!(
        r#"Generate a concise daily recap for today ({today}). Here's what happened:

**Stats:**
- {c} conversations recorded
- {m} new memories extracted
- {s} screenshots captured
- {t} tasks completed
- {cl} clipboard items captured

**Apps/windows used today:**
{apps}

**Memories created today:**
{memories}

**Recent clipboard items:**
{clipboard}

Write a 3-5 sentence summary of the day's activity in second person ("You...").
Focus on what was accomplished, patterns noticed, and any insights.
End with one forward-looking suggestion for tomorrow.
Keep it casual and brief."#,
        c = stats.conversations,
        m = stats.memories,
        s = stats.screenshots,
        t = stats.tasks_completed,
        cl = stats.clipboard_items,
        apps = if apps_list.is_empty() {
            "  (none tracked)".to_string()
        } else {
            apps_list
        },
        memories = if memories_text.is_empty() {
            "(none)".to_string()
        } else {
            memories_text
        },
        clipboard = if clipboard_text.is_empty() {
            "(none)".to_string()
        } else {
            clipboard_text
        },
    );

    let messages = vec![
        LlmMessage {
            role: "system".to_string(),
            content: "You are Omi, a personal AI companion. Generate brief, insightful daily recaps.".to_string(),
        },
        LlmMessage {
            role: "user".to_string(),
            content: prompt,
        },
    ];

    let collected = std::sync::Arc::new(std::sync::Mutex::new(String::new()));
    let collected_clone = collected.clone();

    match crate::llm::complete_streaming(cfg, LlmUseCase::Background, messages, Some(400), move |token| {
        if let Ok(mut s) = collected_clone.lock() {
            s.push_str(&token);
        }
    })
    .await
    {
        Ok(summary) => {
            let summary = summary.trim().to_string();

            let stats_json = serde_json::json!({
                "conversations": stats.conversations,
                "memories": stats.memories,
                "screenshots": stats.screenshots,
                "tasks_completed": stats.tasks_completed,
                "clipboard_items": stats.clipboard_items,
                "apps_used": stats.apps_used.len(),
            })
            .to_string();

            match db.insert_daily_recap(&today, &summary, Some(&stats_json)) {
                Ok(_) => {
                    info!("[RECAP] Generated daily recap for {today}");
                    Some(summary)
                }
                Err(e) => {
                    warn!("[RECAP] Failed to save recap: {e:#}");
                    Some(summary)
                }
            }
        }
        Err(e) => {
            warn!("[RECAP] LLM call failed: {e:#}");
            None
        }
    }
}

pub async fn run_daily_recap_scheduler(
    db: omi_db::Database,
    cfg_provider: impl Fn() -> AppConfig + Send + 'static,
) {
    info!("[RECAP] Daily recap scheduler started");

    loop {
        tokio::time::sleep(std::time::Duration::from_secs(300)).await; // Check every 5 min

        let cfg = cfg_provider();
        let now = chrono::Local::now();
        let target_hour = cfg.daily_recap_hour;

        if now.format("%H").to_string().parse::<u64>().unwrap_or(0) == target_hour {
            let today = Utc::now().format("%Y-%m-%d").to_string();
            if db.get_recap_for_date(&today).ok().flatten().is_none() {
                info!("[RECAP] Generating scheduled daily recap");
                generate_daily_recap(&db, &cfg).await;
                // Sleep an hour to avoid re-triggering within the same hour
                tokio::time::sleep(std::time::Duration::from_secs(3600)).await;
            }
        }
    }
}
