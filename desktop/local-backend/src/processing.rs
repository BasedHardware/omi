use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::time;

use crate::{
    providers::{configured_openai_provider, ChatMessage},
    storage::{
        deterministic_id, NewActionItem, NewMemory, ProcessingJob, ProcessingJobStatus, Store,
        UpdateConversation,
    },
};

const TITLE_WORD_LIMIT: usize = 8;
const TITLE_CHAR_LIMIT: usize = 80;
const OVERVIEW_CHAR_LIMIT: usize = 240;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProcessingOutput {
    pub title: String,
    pub overview: String,
    pub action_items: Vec<ExtractedActionItem>,
    pub memories: Vec<ExtractedMemory>,
    pub provider: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExtractedActionItem {
    pub title: String,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExtractedMemory {
    pub content: String,
    pub category: Option<String>,
}

pub fn spawn_worker(store: Store) {
    tokio::spawn(async move {
        let mut interval = time::interval(Duration::from_secs(1));
        loop {
            interval.tick().await;
            if let Err(error) = process_next_job(&store).await {
                tracing::warn!(error = %error, "local processing worker iteration failed");
            }
        }
    });
}

pub async fn process_next_job(store: &Store) -> Result<Option<ProcessingJob>> {
    let Some(job) = store.processing_jobs().claim_next_queued()? else {
        return Ok(None);
    };

    match process_claimed_job(store, &job).await {
        Ok(result) => store
            .processing_jobs()
            .complete(&job.id, result)
            .with_context(|| format!("failed to complete job {}", job.id)),
        Err(error) => {
            let message = error.to_string();
            store
                .processing_jobs()
                .fail(&job.id, &message)
                .with_context(|| format!("failed to fail job {}", job.id))
        }
    }
}

async fn process_claimed_job(store: &Store, job: &ProcessingJob) -> Result<Value> {
    if job.status != ProcessingJobStatus::Running {
        return Err(anyhow!("processing job must be running before execution"));
    }

    match job.kind.as_str() {
        "finalize_transcript" | "process_conversation" => {
            process_conversation_job(store, job).await
        }
        other => Err(anyhow!("unsupported processing job kind: {other}")),
    }
}

async fn process_conversation_job(store: &Store, job: &ProcessingJob) -> Result<Value> {
    let conversation_id = job
        .target_conversation_id
        .as_ref()
        .ok_or_else(|| anyhow!("processing job missing target conversation id"))?;
    let segments = store.transcripts().list_for_conversation(conversation_id)?;
    let transcript = segments
        .iter()
        .map(|segment| segment.text.as_str())
        .collect::<Vec<_>>()
        .join(" ");
    let output = if let Some(provider) = configured_openai_provider(store)? {
        match provider
            .complete_json(processing_prompt(&transcript))
            .await
            .and_then(parse_provider_output)
        {
            Ok(mut output) => {
                output.provider = "openai_compatible".to_string();
                output
            }
            Err(error) => {
                tracing::warn!(error = %error, "provider processing failed; using deterministic fallback");
                fallback_output(&transcript)
            }
        }
    } else {
        fallback_output(&transcript)
    };

    persist_processing_output(store, conversation_id, &output)?;

    Ok(json!({
        "conversation_id": conversation_id,
        "title": output.title,
        "overview": output.overview,
        "action_items": output.action_items,
        "memories": output.memories,
        "provider": output.provider
    }))
}

fn processing_prompt(transcript: &str) -> Vec<ChatMessage> {
    vec![
        ChatMessage::system(
            "Return compact JSON with title, overview, action_items, and memories. \
             action_items must be an array of {title, description}. \
             memories must be an array of {content, category}.",
        ),
        ChatMessage::user(format!("Transcript:\n{transcript}")),
    ]
}

fn parse_provider_output(value: Value) -> Result<ProcessingOutput> {
    let title = value["title"]
        .as_str()
        .unwrap_or_default()
        .trim()
        .to_string();
    let overview = value["overview"]
        .as_str()
        .unwrap_or_default()
        .trim()
        .to_string();
    let action_items = value["action_items"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|item| {
            let title = item["title"].as_str()?.trim().to_string();
            if title.is_empty() {
                return None;
            }
            Some(ExtractedActionItem {
                title,
                description: item["description"]
                    .as_str()
                    .unwrap_or_default()
                    .trim()
                    .to_string(),
            })
        })
        .collect();
    let memories = value["memories"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|item| {
            let content = item["content"].as_str()?.trim().to_string();
            if content.is_empty() {
                return None;
            }
            Some(ExtractedMemory {
                content,
                category: item["category"]
                    .as_str()
                    .map(|category| category.to_string()),
            })
        })
        .collect();

    Ok(ProcessingOutput {
        title,
        overview,
        action_items,
        memories,
        provider: "openai_compatible".to_string(),
    })
}

pub fn fallback_output(transcript: &str) -> ProcessingOutput {
    let normalized = normalize_whitespace(transcript);
    ProcessingOutput {
        title: fallback_title(&normalized),
        overview: clip_chars(&normalized, OVERVIEW_CHAR_LIMIT),
        action_items: Vec::new(),
        memories: Vec::new(),
        provider: "fallback".to_string(),
    }
}

fn fallback_title(normalized_transcript: &str) -> String {
    if normalized_transcript.is_empty() {
        return "Untitled conversation".to_string();
    }
    let words = normalized_transcript
        .split_whitespace()
        .take(TITLE_WORD_LIMIT)
        .collect::<Vec<_>>()
        .join(" ");
    clip_chars(&words, TITLE_CHAR_LIMIT)
}

fn normalize_whitespace(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn clip_chars(value: &str, limit: usize) -> String {
    value.chars().take(limit).collect()
}

fn persist_processing_output(
    store: &Store,
    conversation_id: &str,
    output: &ProcessingOutput,
) -> Result<()> {
    store
        .conversations()
        .update(
            conversation_id,
            UpdateConversation {
                title: Some(output.title.clone()),
                overview: Some(output.overview.clone()),
                status: Some("processed".to_string()),
                ended_at: None,
                metadata: None,
                starred: None,
            },
        )?
        .ok_or_else(|| anyhow!("conversation missing while persisting processing output"))?;

    for (index, item) in output.action_items.iter().enumerate() {
        store.action_items().create(NewActionItem {
            id: deterministic_id("act", &[conversation_id, &index.to_string(), &item.title]),
            conversation_id: Some(conversation_id.to_string()),
            title: item.title.clone(),
            description: Some(item.description.clone()),
            status: Some("open".to_string()),
            due_at: None,
            metadata: Some(json!({"source": "local_processing"})),
        })?;
    }

    for (index, memory) in output.memories.iter().enumerate() {
        store.memories().create(NewMemory {
            id: deterministic_id(
                "mem",
                &[conversation_id, &index.to_string(), &memory.content],
            ),
            content: memory.content.clone(),
            category: memory.category.clone(),
            conversation_id: Some(conversation_id.to_string()),
            metadata: Some(json!({"source": "local_processing"})),
        })?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use crate::storage::{NewConversation, NewProcessingJob, NewTranscriptSegment};

    use super::*;

    #[test]
    fn fallback_processing_is_deterministic_and_empty_for_items_and_memories() {
        let output = fallback_output(
            "  Discuss launch planning.\nNext we assign owners and review the demo checklist.  ",
        );

        assert_eq!(
            output.title,
            "Discuss launch planning. Next we assign owners and"
        );
        assert_eq!(
            output.overview,
            "Discuss launch planning. Next we assign owners and review the demo checklist."
        );
        assert_eq!(output.action_items, Vec::new());
        assert_eq!(output.memories, Vec::new());
        assert_eq!(output.provider, "fallback");
    }

    #[tokio::test]
    async fn processing_job_lifecycle_persists_outputs() -> Result<()> {
        let store = Store::open_in_memory()?;
        let conversation_id = deterministic_id("conv", &["session-processing"]);

        store.conversations().create(NewConversation {
            id: conversation_id.clone(),
            session_id: "session-processing".to_string(),
            title: String::new(),
            overview: String::new(),
            started_at: None,
            metadata: None,
        })?;
        store.transcripts().append(NewTranscriptSegment {
            id: deterministic_id("seg", &[&conversation_id, "0"]),
            conversation_id: conversation_id.clone(),
            session_id: "session-processing".to_string(),
            speaker_id: None,
            speaker_label: None,
            text: "Plan the desktop local backend MVP and verify deterministic processing."
                .to_string(),
            start_ms: 0,
            end_ms: 2000,
            segment_index: 0,
            source: None,
            metadata: None,
        })?;
        store.processing_jobs().enqueue(NewProcessingJob {
            id: deterministic_id("job", &["process", &conversation_id]),
            kind: "finalize_transcript".to_string(),
            target_conversation_id: Some(conversation_id.clone()),
            max_retries: Some(3),
            payload: Some(json!({"conversation_id": conversation_id})),
        })?;

        let job = process_next_job(&store)
            .await?
            .expect("queued job should be processed");
        assert_eq!(job.status, ProcessingJobStatus::Completed);

        let conversation = store
            .conversations()
            .get(job.target_conversation_id.as_ref().unwrap())?
            .expect("conversation should exist");
        assert_eq!(
            conversation.title,
            "Plan the desktop local backend MVP and verify"
        );
        assert_eq!(conversation.status, "processed");
        assert!(conversation
            .overview
            .starts_with("Plan the desktop local backend MVP"));
        assert!(store.action_items().list()?.is_empty());
        assert!(store.memories().list()?.is_empty());

        let result: Value = serde_json::from_str(&job.result_json)?;
        assert_eq!(result["provider"], "fallback");

        Ok(())
    }
}
