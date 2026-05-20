use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::time;

use crate::{
    providers::{
        configured_openai_provider_for_slot, post_transcript_slot_resolution, ChatMessage,
        ResolvedModelSlot, SLOT_POST_TRANSCRIPT,
    },
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
                .fail_or_requeue(&job.id, &message)
                .with_context(|| format!("failed to fail or requeue job {}", job.id))
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
    let resolution = post_transcript_slot_resolution(store)?;
    let (output, metadata) = if resolution.ok {
        let provider = configured_openai_provider_for_slot(store, SLOT_POST_TRANSCRIPT)?
            .ok_or_else(|| anyhow!("post_transcript slot resolved to an unsupported provider"))?;
        let mut output = provider
            .provider
            .complete_json(processing_prompt(&transcript))
            .await
            .and_then(parse_provider_output)?;
        let account = provider
            .slot
            .provider_account
            .as_ref()
            .ok_or_else(|| anyhow!("post_transcript slot missing provider account"))?;
        output.provider = account.kind.clone();
        (
            output,
            provider_metadata(job, conversation_id, &provider.slot),
        )
    } else {
        let output = fallback_output(&transcript);
        (
            output,
            fallback_metadata(job, conversation_id, &resolution.reason),
        )
    };

    persist_processing_output(store, conversation_id, &output, &metadata)?;

    Ok(json!({
        "conversation_id": conversation_id,
        "title": output.title,
        "overview": output.overview,
        "action_items": output.action_items,
        "memories": output.memories,
        "provider": output.provider,
        "metadata": metadata
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
    let title = required_string(&value, "title")?;
    let overview = required_string(&value, "overview")?;
    let action_items = value["action_items"]
        .as_array()
        .ok_or_else(|| anyhow!("provider output missing action_items array"))?
        .iter()
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
        .ok_or_else(|| anyhow!("provider output missing memories array"))?
        .iter()
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

fn required_string(value: &Value, key: &str) -> Result<String> {
    let value = value[key]
        .as_str()
        .ok_or_else(|| anyhow!("provider output missing {key}"))?
        .trim()
        .to_string();
    if value.is_empty() {
        return Err(anyhow!("provider output {key} was empty"));
    }
    Ok(value)
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
    processing_metadata: &Value,
) -> Result<()> {
    let conversation = store
        .conversations()
        .get(conversation_id)?
        .ok_or_else(|| anyhow!("conversation missing while persisting processing output"))?;
    let conversation_metadata =
        merge_processing_metadata(&conversation.metadata_json, processing_metadata);
    let status = if output.provider == "fallback" {
        "processed_fallback"
    } else {
        "processed"
    };
    store
        .conversations()
        .update(
            conversation_id,
            UpdateConversation {
                title: Some(output.title.clone()),
                overview: Some(output.overview.clone()),
                status: Some(status.to_string()),
                ended_at: None,
                metadata: Some(conversation_metadata),
                starred: None,
                folder_id: None,
            },
        )?
        .ok_or_else(|| anyhow!("conversation missing while persisting processing output"))?;

    let action_item_ids = output
        .action_items
        .iter()
        .enumerate()
        .map(|(index, item)| {
            deterministic_id("act", &[conversation_id, &index.to_string(), &item.title])
        })
        .collect::<Vec<_>>();
    store
        .action_items()
        .soft_delete_local_processing_except(conversation_id, &action_item_ids)?;

    for (index, item) in output.action_items.iter().enumerate() {
        store.action_items().upsert(NewActionItem {
            id: action_item_ids[index].clone(),
            conversation_id: Some(conversation_id.to_string()),
            title: item.title.clone(),
            description: Some(item.description.clone()),
            status: Some("open".to_string()),
            due_at: None,
            metadata: Some(row_processing_metadata(processing_metadata)),
        })?;
    }

    let memory_ids = output
        .memories
        .iter()
        .enumerate()
        .map(|(index, memory)| {
            deterministic_id(
                "mem",
                &[conversation_id, &index.to_string(), &memory.content],
            )
        })
        .collect::<Vec<_>>();
    store
        .memories()
        .soft_delete_local_processing_except(conversation_id, &memory_ids)?;

    for (index, memory) in output.memories.iter().enumerate() {
        store.memories().upsert(NewMemory {
            id: memory_ids[index].clone(),
            content: memory.content.clone(),
            category: memory.category.clone(),
            conversation_id: Some(conversation_id.to_string()),
            metadata: Some(row_processing_metadata(processing_metadata)),
        })?;
    }

    Ok(())
}

fn provider_metadata(
    job: &ProcessingJob,
    conversation_id: &str,
    slot: &ResolvedModelSlot,
) -> Value {
    let account = slot.provider_account.as_ref();
    json!({
        "source": "local_processing",
        "mode": "model",
        "conversation_id": conversation_id,
        "job_id": job.id,
        "job_kind": job.kind,
        "slot": slot.slot,
        "slot_source": slot.source,
        "model_id": slot.model_id,
        "provider_account_id": account.map(|account| account.id.clone()),
        "provider_kind": account.map(|account| account.kind.clone()),
        "options": slot.options.clone()
    })
}

fn fallback_metadata(job: &ProcessingJob, conversation_id: &str, reason: &str) -> Value {
    json!({
        "source": "local_processing",
        "mode": "fallback",
        "conversation_id": conversation_id,
        "job_id": job.id,
        "job_kind": job.kind,
        "slot": SLOT_POST_TRANSCRIPT,
        "fallback_reason": reason
    })
}

fn row_processing_metadata(processing_metadata: &Value) -> Value {
    json!({
        "source": "local_processing",
        "local_processing": processing_metadata
    })
}

fn merge_processing_metadata(existing_metadata_json: &str, processing_metadata: &Value) -> Value {
    let mut metadata =
        serde_json::from_str::<Value>(existing_metadata_json).unwrap_or_else(|_| json!({}));
    if !metadata.is_object() {
        metadata = json!({});
    }
    metadata["local_processing"] = processing_metadata.clone();
    metadata
}

#[cfg(test)]
mod tests {
    use crate::providers::{
        save_provider_policy, ModelSlotOptions, ModelSlotTarget, ProviderAccount,
        ProviderCapabilities, ProviderPolicy, PROVIDER_POLICY_VERSION,
    };
    use crate::storage::{NewConversation, NewProcessingJob, NewTranscriptSegment};

    use super::*;
    use axum::{routing::post, Json, Router};
    use serde_json::Map;
    use std::{collections::BTreeMap, net::TcpListener};
    use tokio::net::TcpListener as TokioTcpListener;

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
        assert_eq!(conversation.status, "processed_fallback");
        assert!(conversation
            .overview
            .starts_with("Plan the desktop local backend MVP"));
        assert!(store.action_items().list()?.is_empty());
        assert!(store.memories().list()?.is_empty());

        let result: Value = serde_json::from_str(&job.result_json)?;
        assert_eq!(result["provider"], "fallback");
        assert_eq!(result["metadata"]["mode"], "fallback");
        assert_eq!(result["metadata"]["slot"], SLOT_POST_TRANSCRIPT);

        let conversation_metadata: Value = serde_json::from_str(&conversation.metadata_json)?;
        assert_eq!(
            conversation_metadata["local_processing"]["mode"],
            "fallback"
        );

        Ok(())
    }

    #[tokio::test]
    async fn post_transcript_slot_provider_persists_model_outputs() -> Result<()> {
        let store = Store::open_in_memory()?;
        let conversation_id = deterministic_id("conv", &["session-slot-processing"]);
        configure_post_transcript_stub_provider(
            &store,
            &spawn_processing_stub(json!({
                "title": "Slot generated title",
                "overview": "Slot generated overview",
                "action_items": [{
                    "title": "Review slot wiring",
                    "description": "Confirm post transcript processing uses provider policy."
                }],
                "memories": [{
                    "content": "User wants local post transcript processing through slots.",
                    "category": "preference"
                }]
            }))
            .await?,
            "slot-model",
        )?;

        seed_conversation_with_segment(
            &store,
            &conversation_id,
            "session-slot-processing",
            "Use the configured slot provider for local processing.",
        )?;
        store.processing_jobs().enqueue(NewProcessingJob {
            id: deterministic_id("job", &["slot-processing", &conversation_id]),
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
        assert_eq!(conversation.title, "Slot generated title");
        assert_eq!(conversation.overview, "Slot generated overview");
        assert_eq!(conversation.status, "processed");

        let action_items = store.action_items().list()?;
        assert_eq!(action_items.len(), 1);
        assert_eq!(action_items[0].title, "Review slot wiring");
        let action_metadata: Value = serde_json::from_str(&action_items[0].metadata_json)?;
        assert_eq!(
            action_metadata["local_processing"]["model_id"],
            "slot-model"
        );

        let memories = store.memories().list()?;
        assert_eq!(memories.len(), 1);
        assert_eq!(
            memories[0].content,
            "User wants local post transcript processing through slots."
        );

        let result: Value = serde_json::from_str(&job.result_json)?;
        assert_eq!(result["metadata"]["mode"], "model");
        assert_eq!(result["metadata"]["slot"], SLOT_POST_TRANSCRIPT);
        assert_eq!(result["metadata"]["model_id"], "slot-model");
        assert_eq!(result["metadata"]["slot_source"], "provider_policy");

        Ok(())
    }

    #[tokio::test]
    async fn malformed_provider_json_fails_and_is_retry_safe() -> Result<()> {
        let store = Store::open_in_memory()?;
        let conversation_id = deterministic_id("conv", &["session-malformed-provider"]);
        configure_post_transcript_stub_provider(
            &store,
            &spawn_processing_stub(json!({
                "title": "Missing arrays",
                "overview": "This should not be accepted."
            }))
            .await?,
            "slot-model",
        )?;

        seed_conversation_with_segment(
            &store,
            &conversation_id,
            "session-malformed-provider",
            "Malformed model JSON should fail instead of empty-success processing.",
        )?;
        store.processing_jobs().enqueue(NewProcessingJob {
            id: deterministic_id("job", &["malformed-provider", &conversation_id]),
            kind: "finalize_transcript".to_string(),
            target_conversation_id: Some(conversation_id.clone()),
            max_retries: Some(1),
            payload: Some(json!({"conversation_id": conversation_id})),
        })?;

        let job = process_next_job(&store)
            .await?
            .expect("failed job should be returned");
        assert_eq!(job.status, ProcessingJobStatus::Failed);
        assert!(job
            .last_error
            .as_deref()
            .unwrap_or("")
            .contains("action_items array"));

        let conversation = store
            .conversations()
            .get(job.target_conversation_id.as_ref().unwrap())?
            .expect("conversation should exist");
        assert_eq!(conversation.status, "open");
        assert!(store.action_items().list()?.is_empty());
        assert!(store.memories().list()?.is_empty());

        Ok(())
    }

    #[tokio::test]
    async fn provider_failures_requeue_until_retry_limit() -> Result<()> {
        let store = Store::open_in_memory()?;
        let conversation_id = deterministic_id("conv", &["session-provider-failure"]);
        let listener = TcpListener::bind("127.0.0.1:0")?;
        let unused_addr = listener.local_addr()?;
        drop(listener);

        let mut settings = Map::new();
        settings.insert(
            "ai_provider".to_string(),
            json!({
                "kind": "openai_compatible",
                "base_url": format!("http://{unused_addr}/v1"),
                "model": "offline-model",
                "api_key": "local-test-key"
            }),
        );
        store.settings().upsert_many(settings)?;
        store.conversations().create(NewConversation {
            id: conversation_id.clone(),
            session_id: "session-provider-failure".to_string(),
            title: String::new(),
            overview: String::new(),
            started_at: None,
            metadata: None,
        })?;
        store.transcripts().append(NewTranscriptSegment {
            id: deterministic_id("seg", &[&conversation_id, "0"]),
            conversation_id: conversation_id.clone(),
            session_id: "session-provider-failure".to_string(),
            speaker_id: None,
            speaker_label: None,
            text: "Provider failures should retry instead of falling back.".to_string(),
            start_ms: 0,
            end_ms: 1000,
            segment_index: 0,
            source: None,
            metadata: None,
        })?;
        let enqueued = store.processing_jobs().enqueue(NewProcessingJob {
            id: deterministic_id("job", &["provider-failure", &conversation_id]),
            kind: "finalize_transcript".to_string(),
            target_conversation_id: Some(conversation_id.clone()),
            max_retries: Some(2),
            payload: Some(json!({"conversation_id": conversation_id})),
        })?;

        let first = process_next_job(&store)
            .await?
            .expect("failed job should be returned");
        assert_eq!(first.id, enqueued.id);
        assert_eq!(first.status, ProcessingJobStatus::Queued);
        assert_eq!(first.retry_count, 1);
        assert!(first.last_error.as_deref().unwrap_or("").contains("failed"));

        let second = process_next_job(&store)
            .await?
            .expect("exhausted job should be returned");
        assert_eq!(second.id, enqueued.id);
        assert_eq!(second.status, ProcessingJobStatus::Failed);
        assert_eq!(second.retry_count, 2);
        assert!(second
            .last_error
            .as_deref()
            .unwrap_or("")
            .contains("failed"));

        let conversation = store
            .conversations()
            .get(second.target_conversation_id.as_ref().unwrap())?
            .expect("conversation should exist");
        assert_eq!(conversation.status, "open");

        Ok(())
    }

    #[test]
    fn provider_style_processing_outputs_are_retry_safe() -> Result<()> {
        let store = Store::open_in_memory()?;
        let conversation_id = deterministic_id("conv", &["session-provider-retry"]);

        store.conversations().create(NewConversation {
            id: conversation_id.clone(),
            session_id: "session-provider-retry".to_string(),
            title: String::new(),
            overview: String::new(),
            started_at: None,
            metadata: None,
        })?;

        let output = ProcessingOutput {
            title: "Provider summary".to_string(),
            overview: "Provider overview".to_string(),
            action_items: vec![ExtractedActionItem {
                title: "Review retry behavior".to_string(),
                description: "Confirm local processing upserts deterministic rows.".to_string(),
            }],
            memories: vec![ExtractedMemory {
                content: "User prefers retry-safe local imports.".to_string(),
                category: Some("preference".to_string()),
            }],
            provider: "openai_compatible".to_string(),
        };

        let metadata = json!({
            "source": "local_processing",
            "mode": "model",
            "conversation_id": conversation_id,
            "job_id": "job-provider-retry-1",
            "job_kind": "finalize_transcript",
            "slot": SLOT_POST_TRANSCRIPT,
            "slot_source": "provider_policy",
            "model_id": "first-model",
            "provider_account_id": "local-openai",
            "provider_kind": "openai_compatible"
        });

        persist_processing_output(&store, &conversation_id, &output, &metadata)?;
        persist_processing_output(&store, &conversation_id, &output, &metadata)?;

        let action_items = store.action_items().list()?;
        let memories = store.memories().list()?;
        assert_eq!(action_items.len(), 1);
        assert_eq!(action_items[0].title, "Review retry behavior");
        assert_eq!(memories.len(), 1);
        assert_eq!(
            memories[0].content,
            "User prefers retry-safe local imports."
        );

        let replacement = ProcessingOutput {
            title: "Provider summary".to_string(),
            overview: "Provider overview".to_string(),
            action_items: vec![ExtractedActionItem {
                title: "Ship retry behavior".to_string(),
                description: "Replace stale local processing rows.".to_string(),
            }],
            memories: Vec::new(),
            provider: "openai_compatible".to_string(),
        };
        let replacement_metadata = json!({
            "source": "local_processing",
            "mode": "model",
            "conversation_id": conversation_id,
            "job_id": "job-provider-retry-2",
            "job_kind": "finalize_transcript",
            "slot": SLOT_POST_TRANSCRIPT,
            "slot_source": "provider_policy",
            "model_id": "replacement-model",
            "provider_account_id": "local-openai",
            "provider_kind": "openai_compatible"
        });
        persist_processing_output(
            &store,
            &conversation_id,
            &replacement,
            &replacement_metadata,
        )?;

        let action_items = store.action_items().list()?;
        let memories = store.memories().list()?;
        assert_eq!(action_items.len(), 1);
        assert_eq!(action_items[0].title, "Ship retry behavior");
        assert!(memories.is_empty());

        let action_metadata: Value = serde_json::from_str(&action_items[0].metadata_json)?;
        assert_eq!(
            action_metadata["local_processing"]["model_id"],
            "replacement-model"
        );

        Ok(())
    }

    fn seed_conversation_with_segment(
        store: &Store,
        conversation_id: &str,
        session_id: &str,
        text: &str,
    ) -> Result<()> {
        store.conversations().create(NewConversation {
            id: conversation_id.to_string(),
            session_id: session_id.to_string(),
            title: String::new(),
            overview: String::new(),
            started_at: None,
            metadata: None,
        })?;
        store.transcripts().append(NewTranscriptSegment {
            id: deterministic_id("seg", &[conversation_id, "0"]),
            conversation_id: conversation_id.to_string(),
            session_id: session_id.to_string(),
            speaker_id: None,
            speaker_label: None,
            text: text.to_string(),
            start_ms: 0,
            end_ms: 1000,
            segment_index: 0,
            source: None,
            metadata: None,
        })?;
        Ok(())
    }

    fn configure_post_transcript_stub_provider(
        store: &Store,
        base_url: &str,
        model_id: &str,
    ) -> Result<()> {
        let account = ProviderAccount {
            id: "slot-stub".to_string(),
            kind: "openai_compatible".to_string(),
            base_url: Some(base_url.to_string()),
            api_key: Some("local-test-key".to_string()),
            display_name: Some("Slot Stub".to_string()),
            capabilities: ProviderCapabilities {
                chat_completions: true,
                json_mode: true,
                tool_calls: false,
                vision: false,
                speech_to_text: false,
            },
            subscription_integration: None,
        };
        let mut slots = BTreeMap::new();
        slots.insert(
            SLOT_POST_TRANSCRIPT.to_string(),
            ModelSlotTarget {
                provider_account_id: Some(account.id.clone()),
                model_id: model_id.to_string(),
                options: ModelSlotOptions {
                    json_mode: Some(true),
                    tool_support: Some(false),
                },
            },
        );
        save_provider_policy(
            store,
            ProviderPolicy {
                version: PROVIDER_POLICY_VERSION,
                provider_accounts: vec![account],
                model_slots: slots,
            },
        )?;
        Ok(())
    }

    async fn spawn_processing_stub(content: Value) -> Result<String> {
        let content = serde_json::to_string(&content)?;
        let app = Router::new().route(
            "/v1/chat/completions",
            post(move || {
                let content = content.clone();
                async move {
                    Json(json!({
                        "choices": [{
                            "message": {
                                "content": content
                            }
                        }]
                    }))
                }
            }),
        );
        let listener = TokioTcpListener::bind("127.0.0.1:0").await?;
        let addr = listener.local_addr()?;
        tokio::spawn(async move {
            axum::serve(listener, app)
                .await
                .expect("stub server failed");
        });
        Ok(format!("http://{addr}/v1"))
    }
}
