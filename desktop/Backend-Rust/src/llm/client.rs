// LLM Client - Gemini API integration
// Port from Python backend (llm.py)

use chrono::{DateTime, Utc};
use reqwest::Client;
use serde::{Deserialize, Serialize};

use super::prompts::*;
use crate::models::{ActionItem, Category, Event, ExtractedKnowledge, KnowledgeGraphNode, Memory, MemoryCategory, MemoryDB, Structured, TranscriptSegment};

/// Calendar participant for meeting context
#[derive(Debug, Clone, Default)]
pub struct CalendarParticipant {
    pub name: Option<String>,
    pub email: Option<String>,
}

/// Context from a calendar meeting for better conversation analysis
#[derive(Debug, Clone, Default)]
pub struct CalendarMeetingContext {
    pub title: String,
    pub start_time: Option<DateTime<Utc>>,
    pub duration_minutes: i32,
    pub platform: Option<String>,
    pub participants: Vec<CalendarParticipant>,
    pub notes: Option<String>,
    pub meeting_link: Option<String>,
}

impl CalendarMeetingContext {
    /// Build the calendar context string for the prompt
    pub fn to_context_string(&self) -> String {
        if self.title.is_empty() {
            return String::new();
        }

        let participants_str = self.participants.iter()
            .map(|p| {
                match (&p.name, &p.email) {
                    (Some(name), Some(email)) => format!("{} <{}>", name, email),
                    (Some(name), None) => name.clone(),
                    (None, Some(email)) => email.clone(),
                    (None, None) => "Unknown".to_string(),
                }
            })
            .collect::<Vec<_>>()
            .join(", ");

        let start_time_str = self.start_time
            .map(|t| t.format("%Y-%m-%d %H:%M UTC").to_string())
            .unwrap_or_else(|| "Not specified".to_string());

        let mut context = format!(
            "CALENDAR MEETING CONTEXT:\n- Meeting Title: {}\n- Scheduled Time: {}\n- Duration: {} minutes\n- Platform: {}\n- Participants: {}",
            self.title,
            start_time_str,
            self.duration_minutes,
            self.platform.as_deref().unwrap_or("Not specified"),
            if participants_str.is_empty() { "None listed" } else { &participants_str }
        );

        if let Some(notes) = &self.notes {
            context.push_str(&format!("\n- Meeting Notes: {}", notes));
        }
        if let Some(link) = &self.meeting_link {
            context.push_str(&format!("\n- Meeting Link: {}", link));
        }

        context
    }
}

/// LLM Client for calling Gemini
pub struct LlmClient {
    client: Client,
    api_key: String,
    model: String,
}

// Gemini API types
#[derive(Debug, Serialize)]
struct GeminiRequest {
    contents: Vec<GeminiContent>,
    #[serde(rename = "generationConfig")]
    generation_config: Option<GeminiGenerationConfig>,
}

#[derive(Debug, Serialize)]
struct GeminiContent {
    parts: Vec<GeminiPart>,
}

#[derive(Debug, Serialize)]
struct GeminiPart {
    text: String,
}

#[derive(Debug, Serialize)]
struct GeminiGenerationConfig {
    #[serde(rename = "responseMimeType")]
    response_mime_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    #[serde(rename = "responseSchema")]
    response_schema: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    temperature: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    #[serde(rename = "maxOutputTokens")]
    max_output_tokens: Option<i32>,
}

#[derive(Debug, Deserialize)]
struct GeminiResponse {
    candidates: Vec<GeminiCandidate>,
}

#[derive(Debug, Deserialize)]
struct GeminiCandidate {
    content: GeminiContentResponse,
}

#[derive(Debug, Deserialize)]
struct GeminiContentResponse {
    parts: Vec<GeminiPartResponse>,
}

#[derive(Debug, Deserialize)]
struct GeminiPartResponse {
    text: String,
}

impl LlmClient {
    /// Create a new Gemini client
    pub fn new(api_key: String) -> Self {
        Self {
            client: Client::new(),
            api_key,
            model: "gemini-3-pro-preview".to_string(),
        }
    }

    /// Set the model to use
    #[allow(dead_code)]
    pub fn with_model(mut self, model: &str) -> Self {
        self.model = model.to_string();
        self
    }

    /// Call the LLM with a specific JSON schema for structured output
    pub async fn call_with_schema(&self, prompt: &str, temperature: Option<f32>, max_tokens: Option<i32>, schema: Option<serde_json::Value>) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let request = GeminiRequest {
            contents: vec![GeminiContent {
                parts: vec![GeminiPart {
                    text: prompt.to_string(),
                }],
            }],
            generation_config: Some(GeminiGenerationConfig {
                response_mime_type: "application/json".to_string(),
                response_schema: schema,
                temperature,
                max_output_tokens: max_tokens,
            }),
        };

        let url = format!(
            "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}",
            self.model, self.api_key
        );

        let response = self
            .client
            .post(&url)
            .json(&request)
            .send()
            .await?;

        if !response.status().is_success() {
            let error = response.text().await?;
            return Err(format!("Gemini API error: {}", error).into());
        }

        let result: GeminiResponse = response.json().await?;
        Ok(result.candidates.first()
            .and_then(|c| c.content.parts.first())
            .map(|p| p.text.clone())
            .unwrap_or_default())
    }

    // =========================================================================
    // CONVERSATION PROCESSING - Port from Python llm.py
    // =========================================================================

    /// Extract brief structure from a short transcript
    /// Used for transcripts below BRIEF_TRANSCRIPT_THRESHOLD words
    /// Returns a simple summary without action items, events, or memories
    pub async fn extract_brief_structure(
        &self,
        transcript: &str,
        language: &str,
    ) -> Result<Structured, Box<dyn std::error::Error + Send + Sync>> {
        let prompt = BRIEF_SUMMARY_PROMPT
            .replace("{transcript_text}", transcript)
            .replace("{language}", language)
            .replace("{categories}", &Category::all_as_string());

        // Define schema for structured output
        let schema = serde_json::json!({
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "overview": {"type": "string"},
                "emoji": {"type": "string"},
                "category": {"type": "string"}
            },
            "required": ["title", "overview", "emoji", "category"]
        });

        let response = self.call_with_schema(&prompt, Some(0.5), Some(500), Some(schema)).await?;

        #[derive(Deserialize)]
        struct BriefResponse {
            title: String,
            overview: String,
            emoji: String,
            category: String,
        }

        let result: BriefResponse = serde_json::from_str(&response)
            .map_err(|e| format!("Failed to parse brief structure response: {} - {}", e, response))?;

        let category = serde_json::from_str(&format!("\"{}\"", result.category))
            .unwrap_or(Category::Other);

        Ok(Structured {
            title: result.title,
            overview: result.overview,
            emoji: result.emoji,
            category,
            action_items: vec![],
            events: vec![],
        })
    }

    /// Extract structure from transcript (title, overview, emoji, category, events)
    /// Copied from Python extract_transcript_structure
    pub async fn extract_structure(
        &self,
        transcript: &str,
        started_at: &str,
        timezone: &str,
        language: &str,
        calendar_context: Option<&CalendarMeetingContext>,
    ) -> Result<Structured, Box<dyn std::error::Error + Send + Sync>> {
        // Build calendar context section
        let calendar_prompt_section = match calendar_context {
            Some(ctx) if !ctx.title.is_empty() => {
                STRUCTURE_CALENDAR_SECTION.replace("{calendar_context_str}", &ctx.to_context_string())
            }
            _ => String::new(),
        };

        let prompt = STRUCTURE_PROMPT
            .replace("{transcript_text}", transcript)
            .replace("{started_at}", started_at)
            .replace("{tz}", timezone)
            .replace("{language}", language)
            .replace("{categories}", &Category::all_as_string())
            .replace("{calendar_prompt_section}", &calendar_prompt_section);

        // Define schema for structured output
        let schema = serde_json::json!({
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "overview": {"type": "string"},
                "emoji": {"type": "string"},
                "category": {"type": "string"},
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "start": {"type": "string"},
                            "duration": {"type": "integer"}
                        },
                        "required": ["title", "start"]
                    }
                }
            },
            "required": ["title", "overview", "emoji", "category"]
        });

        let response = self.call_with_schema(&prompt, Some(0.7), Some(1500), Some(schema)).await?;

        #[derive(Deserialize)]
        struct StructureResponse {
            title: String,
            overview: String,
            emoji: String,
            category: String,
            #[serde(default)]
            events: Vec<EventResponse>,
        }

        #[derive(Deserialize)]
        struct EventResponse {
            title: String,
            #[serde(default)]
            description: String,
            start: String,
            #[serde(default = "default_duration")]
            duration: i32,
        }

        fn default_duration() -> i32 { 30 }

        let result: StructureResponse = serde_json::from_str(&response)
            .map_err(|e| format!("Failed to parse structure response: {} - {}", e, response))?;

        let events: Vec<Event> = result.events.into_iter().filter_map(|e| {
            chrono::DateTime::parse_from_rfc3339(&e.start).ok().map(|dt| Event {
                title: e.title,
                description: e.description,
                start: dt.with_timezone(&chrono::Utc),
                // Cap duration at 180 minutes
                duration: e.duration.min(180),
            })
        }).collect();

        let category = serde_json::from_str(&format!("\"{}\"", result.category))
            .unwrap_or(Category::Other);

        Ok(Structured {
            title: result.title,
            overview: result.overview,
            emoji: result.emoji,
            category,
            action_items: vec![], // Extracted separately
            events,
        })
    }

    /// Extract action items from transcript
    /// Copied from Python extract_action_items
    pub async fn extract_action_items(
        &self,
        transcript: &str,
        started_at: &str,
        timezone: &str,
        language: &str,
        existing_items: &[ActionItem],
        calendar_context: Option<&CalendarMeetingContext>,
    ) -> Result<Vec<ActionItem>, Box<dyn std::error::Error + Send + Sync>> {
        if transcript.is_empty() || transcript.trim().is_empty() {
            return Ok(vec![]);
        }

        // Build existing items context for deduplication
        let existing_items_context = if existing_items.is_empty() {
            String::new()
        } else {
            let items_list: Vec<String> = existing_items.iter()
                .map(|item| {
                    let due_str = item.due_at
                        .map(|d| d.to_rfc3339())
                        .unwrap_or_else(|| "No due date".to_string());
                    let completed = if item.completed { "✓ Completed" } else { "Pending" };
                    format!("  • {} (Due: {}) [{}]", item.description, due_str, completed)
                })
                .collect();
            format!("\n\nEXISTING ACTION ITEMS FROM PAST 2 DAYS ({} items):\n{}",
                items_list.len(),
                items_list.join("\n"))
        };

        // Build calendar context section
        let calendar_prompt_section = match calendar_context {
            Some(ctx) if !ctx.title.is_empty() => {
                ACTION_ITEMS_CALENDAR_SECTION.replace("{calendar_context_str}", &ctx.to_context_string())
            }
            _ => String::new(),
        };

        let prompt = ACTION_ITEMS_PROMPT
            .replace("{transcript_text}", transcript)
            .replace("{started_at}", started_at)
            .replace("{tz}", timezone)
            .replace("{language}", language)
            .replace("{existing_items_context}", &existing_items_context)
            .replace("{calendar_prompt_section}", &calendar_prompt_section);

        // Define schema for structured output (includes confidence and priority)
        let schema = serde_json::json!({
            "type": "object",
            "properties": {
                "action_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "due_at": {"type": "string"},
                            "confidence": {"type": "number"},
                            "priority": {"type": "string"}
                        },
                        "required": ["description", "confidence", "priority"]
                    }
                }
            },
            "required": ["action_items"]
        });

        let response = self.call_with_schema(&prompt, Some(0.7), Some(1500), Some(schema)).await?;

        #[derive(Deserialize)]
        struct ActionItemsResponse {
            action_items: Vec<ActionItemResponse>,
        }

        #[derive(Deserialize)]
        struct ActionItemResponse {
            description: String,
            due_at: Option<String>,
            #[serde(default)]
            confidence: Option<f64>,
            #[serde(default)]
            priority: Option<String>,
        }

        let result: ActionItemsResponse = serde_json::from_str(&response)
            .map_err(|e| format!("Failed to parse action items response: {} - {}", e, response))?;

        let items: Vec<ActionItem> = result.action_items.into_iter()
            .filter(|item| {
                let conf = item.confidence.unwrap_or(0.0);
                if conf < 0.75 {
                    tracing::info!("Filtering out low-confidence action item ({}): {}", conf, item.description);
                    false
                } else {
                    true
                }
            })
            .map(|item| ActionItem {
                description: item.description,
                completed: false,
                due_at: item.due_at.and_then(|d| chrono::DateTime::parse_from_rfc3339(&d).ok())
                    .map(|dt| dt.with_timezone(&chrono::Utc)),
                confidence: item.confidence,
                priority: item.priority,
            })
            .collect();

        Ok(items)
    }

    /// Extract memories from transcript
    /// Copied from Python extract_memories
    pub async fn extract_memories(
        &self,
        transcript: &str,
        user_name: &str,
        existing_memories: &[MemoryDB],
    ) -> Result<Vec<Memory>, Box<dyn std::error::Error + Send + Sync>> {
        if transcript.is_empty() || transcript.trim().is_empty() {
            return Ok(vec![]);
        }

        // Build existing memories context for deduplication
        let existing_memories_str = if existing_memories.is_empty() {
            "(No existing memories)".to_string()
        } else {
            existing_memories.iter()
                .take(100) // Limit context size
                .map(|m| format!("- [{}] {}",
                    match m.category {
                        MemoryCategory::System => "system",
                        MemoryCategory::Interesting => "interesting",
                        MemoryCategory::Manual => "manual",
                        MemoryCategory::Core => "core",
                        MemoryCategory::Hobbies => "hobbies",
                        MemoryCategory::Lifestyle => "lifestyle",
                        MemoryCategory::Interests => "interests",
                    },
                    m.content
                ))
                .collect::<Vec<_>>()
                .join("\n")
        };

        let prompt = MEMORIES_PROMPT
            .replace("{transcript_text}", transcript)
            .replace("{user_name}", user_name)
            .replace("{existing_memories_str}", &existing_memories_str);

        // Define schema for structured output
        let schema = serde_json::json!({
            "type": "object",
            "properties": {
                "memories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "category": {"type": "string", "enum": ["system", "interesting"]}
                        },
                        "required": ["content", "category"]
                    }
                }
            },
            "required": ["memories"]
        });

        let response = self.call_with_schema(&prompt, Some(0.5), Some(500), Some(schema)).await?;

        #[derive(Deserialize)]
        struct MemoriesResponse {
            memories: Vec<MemoryResponse>,
        }

        #[derive(Deserialize)]
        struct MemoryResponse {
            content: String,
            category: String,
        }

        let result: MemoriesResponse = serde_json::from_str(&response)
            .map_err(|e| format!("Failed to parse memories response: {} - {}", e, response))?;

        // Validate categories and enforce limits: max 2 interesting + max 2 system
        let mut valid_memories = Vec::new();
        let mut interesting_count = 0;
        let mut system_count = 0;

        for m in result.memories {
            let content = m.content.trim().to_string();
            if content.is_empty() {
                continue;
            }

            let category = match m.category.as_str() {
                "interesting" => MemoryCategory::Interesting,
                "system" => MemoryCategory::System,
                _ => MemoryCategory::System,
            };

            // Enforce per-category limits
            match category {
                MemoryCategory::Interesting => {
                    if interesting_count >= 2 {
                        continue;
                    }
                    interesting_count += 1;
                }
                MemoryCategory::System | MemoryCategory::Manual |
                MemoryCategory::Core | MemoryCategory::Hobbies |
                MemoryCategory::Lifestyle | MemoryCategory::Interests => {
                    if system_count >= 2 {
                        continue;
                    }
                    system_count += 1;
                }
            }

            valid_memories.push(Memory {
                content,
                category,
                tags: Vec::new(),
            });
        }

        Ok(valid_memories)
    }

    /// Full conversation processing pipeline
    /// Copied from Python generate_structure
    pub async fn process_conversation(
        &self,
        segments: &[TranscriptSegment],
        started_at: &str,
        timezone: &str,
        language: &str,
        user_name: &str,
        existing_action_items: &[ActionItem],
        existing_memories: &[MemoryDB],
    ) -> Result<ProcessedConversation, Box<dyn std::error::Error + Send + Sync>> {
        self.process_conversation_with_calendar(
            segments,
            started_at,
            timezone,
            language,
            user_name,
            existing_action_items,
            existing_memories,
            None,
        ).await
    }

    /// Skip all LLM extraction for non-desktop sources.
    /// The Python backend handles structure, memories, and tasks for OMI/bee/etc.
    /// Returns a minimal ProcessedConversation with no LLM calls.
    pub fn skip_extraction() -> ProcessedConversation {
        ProcessedConversation {
            discarded: false,
            structured: Structured {
                title: String::new(),
                overview: String::new(),
                emoji: String::new(),
                category: crate::models::Category::Other,
                action_items: vec![],
                events: vec![],
            },
            action_items: vec![],
            memories: vec![],
        }
    }

    /// Full conversation processing pipeline with calendar context
    pub async fn process_conversation_with_calendar(
        &self,
        segments: &[TranscriptSegment],
        started_at: &str,
        timezone: &str,
        language: &str,
        user_name: &str,
        existing_action_items: &[ActionItem],
        existing_memories: &[MemoryDB],
        calendar_context: Option<&CalendarMeetingContext>,
    ) -> Result<ProcessedConversation, Box<dyn std::error::Error + Send + Sync>> {
        let transcript = TranscriptSegment::to_transcript_text(segments);
        let word_count = transcript.split_whitespace().count();

        // Brief transcripts: use simplified processing (no action items/memories extraction)
        if word_count < BRIEF_TRANSCRIPT_THRESHOLD {
            tracing::info!("Brief transcript ({} words < {}), using simplified processing", word_count, BRIEF_TRANSCRIPT_THRESHOLD);
            let structured = self.extract_brief_structure(&transcript, language).await?;
            return Ok(ProcessedConversation {
                discarded: false,
                structured,
                action_items: vec![],
                memories: vec![],
            });
        }

        // Full processing for normal transcripts
        tracing::info!("Full transcript processing ({} words)", word_count);

        // Step 1: Extract structure (title, overview, emoji, category, events)
        let structured = self.extract_structure(&transcript, started_at, timezone, language, calendar_context).await?;

        // Step 2: Extract action items
        let action_items = self.extract_action_items(
            &transcript,
            started_at,
            timezone,
            language,
            existing_action_items,
            calendar_context,
        ).await?;

        // Step 3: Extract memories
        let memories = self.extract_memories(&transcript, user_name, existing_memories).await?;

        Ok(ProcessedConversation {
            discarded: false,
            structured: Structured {
                action_items: action_items.clone(),
                ..structured
            },
            action_items,
            memories,
        })
    }
}

/// Result of processing a conversation
#[derive(Debug)]
pub struct ProcessedConversation {
    pub discarded: bool,
    pub structured: Structured,
    pub action_items: Vec<ActionItem>,
    pub memories: Vec<Memory>,
}

impl LlmClient {
    /// Run an app's memory prompt against a conversation transcript
    /// Used for reprocessing conversations with different apps
    pub async fn run_memory_prompt(
        &self,
        prompt_template: &str,
        transcript: &str,
        structured: &Structured,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        // Build context about the conversation
        let context = format!(
            "CONVERSATION CONTEXT:\nTitle: {}\nCategory: {:?}\nOverview: {}\n\nTRANSCRIPT:\n{}",
            structured.title,
            structured.category,
            structured.overview,
            transcript
        );

        // Build the full prompt
        let full_prompt = format!(
            "{}\n\n{}\n\nProvide your analysis based on the app's prompt and the conversation above. Be specific and actionable.",
            prompt_template,
            context
        );

        // Call the LLM without JSON format requirement (free-form text response)
        self.call_text(&full_prompt, Some(0.7), Some(2000)).await
    }

    /// Call Gemini API with text (non-JSON) response
    pub async fn call_text(&self, prompt: &str, temperature: Option<f32>, max_tokens: Option<i32>) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        #[derive(Debug, Serialize)]
        struct GeminiTextRequest {
            contents: Vec<GeminiContent>,
            #[serde(rename = "generationConfig")]
            generation_config: Option<GeminiTextConfig>,
        }

        #[derive(Debug, Serialize)]
        struct GeminiTextConfig {
            #[serde(skip_serializing_if = "Option::is_none")]
            temperature: Option<f32>,
            #[serde(skip_serializing_if = "Option::is_none")]
            #[serde(rename = "maxOutputTokens")]
            max_output_tokens: Option<i32>,
        }

        let request = GeminiTextRequest {
            contents: vec![GeminiContent {
                parts: vec![GeminiPart {
                    text: prompt.to_string(),
                }],
            }],
            generation_config: Some(GeminiTextConfig {
                temperature,
                max_output_tokens: max_tokens,
            }),
        };

        let url = format!(
            "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}",
            self.model, self.api_key
        );

        let response = self
            .client
            .post(&url)
            .json(&request)
            .send()
            .await?;

        if !response.status().is_success() {
            let error = response.text().await?;
            return Err(format!("Gemini API error: {}", error).into());
        }

        let result: GeminiResponse = response.json().await?;
        Ok(result.candidates.first()
            .and_then(|c| c.content.parts.first())
            .map(|p| p.text.clone())
            .unwrap_or_default())
    }

    // =========================================================================
    // CHAT CONTEXT - For RAG context retrieval
    // Ported from Python: utils/llm/chat.py
    // =========================================================================

    /// Check if a question requires context to answer
    /// Ported from Python requires_context()
    pub async fn check_requires_context(
        &self,
        prompt: &str,
    ) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        let schema = serde_json::json!({
            "type": "object",
            "properties": {
                "requires_context": {
                    "type": "boolean",
                    "description": "Whether the question requires personal context to answer"
                }
            },
            "required": ["requires_context"]
        });

        let response = self.call_with_schema(prompt, Some(0.1), Some(50), Some(schema)).await?;

        #[derive(Deserialize)]
        struct RequiresContextResponse {
            requires_context: bool,
        }

        let result: RequiresContextResponse = serde_json::from_str(&response)
            .map_err(|e| format!("Failed to parse requires_context response: {} - {}", e, response))?;

        Ok(result.requires_context)
    }

    /// Extract date range from a question
    /// Ported from Python retrieve_context_dates_by_question()
    pub async fn extract_date_range(
        &self,
        prompt: &str,
    ) -> Result<Option<(DateTime<Utc>, DateTime<Utc>)>, Box<dyn std::error::Error + Send + Sync>> {
        let schema = serde_json::json!({
            "type": "object",
            "properties": {
                "has_date_reference": {
                    "type": "boolean",
                    "description": "Whether the question contains a date/time reference"
                },
                "start_date": {
                    "type": "string",
                    "description": "Start of date range in ISO 8601 format (UTC)"
                },
                "end_date": {
                    "type": "string",
                    "description": "End of date range in ISO 8601 format (UTC)"
                }
            },
            "required": ["has_date_reference"]
        });

        let response = self.call_with_schema(prompt, Some(0.1), Some(200), Some(schema)).await?;

        #[derive(Deserialize)]
        struct DateRangeResponse {
            has_date_reference: bool,
            start_date: Option<String>,
            end_date: Option<String>,
        }

        let result: DateRangeResponse = serde_json::from_str(&response)
            .map_err(|e| format!("Failed to parse date range response: {} - {}", e, response))?;

        if !result.has_date_reference {
            return Ok(None);
        }

        // Parse dates
        let start = result.start_date
            .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
            .map(|dt| dt.with_timezone(&Utc));

        let end = result.end_date
            .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
            .map(|dt| dt.with_timezone(&Utc));

        match (start, end) {
            (Some(s), Some(e)) => Ok(Some((s, e))),
            _ => Ok(None),
        }
    }

    // =========================================================================
    // INITIAL MESSAGE GENERATION - For chat session greeting
    // =========================================================================

    /// Generate a personalized initial greeting message for a new chat session
    pub async fn generate_initial_message(
        &self,
        memories: &[String],
        app_name: Option<&str>,
        app_persona: Option<&str>,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let memories_context = if memories.is_empty() {
            "No memories available yet - this appears to be a new user.".to_string()
        } else {
            let mem_list: Vec<String> = memories.iter().take(10).map(|m| format!("- {}", m)).collect();
            format!("User facts and memories:\n{}", mem_list.join("\n"))
        };

        let persona_context = match (app_name, app_persona) {
            (Some(name), Some(persona)) => format!(
                "You are {}, an AI assistant with this persona: {}\n\nGenerate a greeting that reflects this persona.",
                name, persona
            ),
            (Some(name), None) => format!(
                "You are {}, an AI assistant.",
                name
            ),
            _ => "You are OMI, a friendly personal AI assistant that helps users with their daily life.".to_string(),
        };

        let prompt = format!(
            r#"{persona_context}

{memories_context}

Generate a short, warm, personalized greeting message to start a new chat session. The greeting should:
- Be friendly and conversational (1-2 sentences max)
- Reference something specific from the user's memories if available
- Feel natural, not robotic
- NOT ask "how can I help you today?" or similar generic questions
- Be casual and engaging

Return ONLY the greeting text, nothing else."#,
            persona_context = persona_context,
            memories_context = memories_context
        );

        self.call_text(&prompt, Some(0.8), Some(150)).await
    }

    // =========================================================================
    // SESSION TITLE GENERATION - For auto-titling chat sessions
    // =========================================================================

    /// Generate a concise title for a chat session based on the conversation
    pub async fn generate_session_title(
        &self,
        messages: &[(String, String)], // (text, sender)
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        if messages.is_empty() {
            return Ok("New Chat".to_string());
        }

        // Format messages for the prompt
        let messages_text: Vec<String> = messages
            .iter()
            .take(6) // Only use first 6 messages for title generation
            .map(|(text, sender)| {
                let role = if sender == "human" { "User" } else { "Assistant" };
                format!("{}: {}", role, text)
            })
            .collect();

        let prompt = format!(
            r#"Based on this conversation, generate a short, descriptive title (3-6 words max).

Conversation:
{}

Rules:
- Title should capture the main topic or purpose of the conversation
- Be concise and specific (3-6 words)
- Use title case
- Don't use quotes or punctuation
- Don't start with "Chat about" or similar phrases
- Examples of good titles: "Python API Error Fix", "Weekend Trip Planning", "Resume Review Feedback"

Return ONLY the title text, nothing else."#,
            messages_text.join("\n")
        );

        let title = self.call_text(&prompt, Some(0.5), Some(50)).await?;

        // Clean up the title
        let cleaned = title
            .trim()
            .trim_matches('"')
            .trim_matches('\'')
            .to_string();

        // Ensure reasonable length
        if cleaned.len() > 50 {
            Ok(cleaned.chars().take(47).collect::<String>() + "...")
        } else if cleaned.is_empty() {
            Ok("New Chat".to_string())
        } else {
            Ok(cleaned)
        }
    }

    // =========================================================================
    // KNOWLEDGE GRAPH - Entity extraction for memory graph
    // =========================================================================

    /// Extract entities and relationships from a memory for the knowledge graph
    pub async fn extract_knowledge_graph_entities(
        &self,
        memory_content: &str,
        existing_nodes: &[KnowledgeGraphNode],
    ) -> Result<ExtractedKnowledge, Box<dyn std::error::Error + Send + Sync>> {
        if memory_content.is_empty() || memory_content.trim().is_empty() {
            return Ok(ExtractedKnowledge {
                entities: vec![],
                relationships: vec![],
            });
        }

        // Build existing nodes context for deduplication
        let existing_nodes_str = if existing_nodes.is_empty() {
            "(No existing entities)".to_string()
        } else {
            existing_nodes
                .iter()
                .take(100)
                .map(|n| format!("- {} ({})", n.label, n.node_type))
                .collect::<Vec<_>>()
                .join("\n")
        };

        let prompt = format!(
            r#"Extract named entities and their relationships from this memory/fact about a user.

MEMORY:
{memory_content}

EXISTING ENTITIES IN GRAPH (use these exact names if referring to same entity):
{existing_nodes_str}

INSTRUCTIONS:
1. Extract ONLY specific, named entities - people, places, organizations, concrete things, or abstract concepts
2. DO NOT extract:
   - Generic terms (e.g., "work", "home", "weekend")
   - Dates or times
   - Actions or verbs
   - Pronouns (he, she, they)
   - Common words without specific meaning
3. For each entity, determine its type: person, place, organization, thing, or concept
4. If an entity matches one in EXISTING ENTITIES, use the EXACT same name
5. Extract relationships between entities (e.g., "Alice" -> "works at" -> "Google")
6. Relationship labels should be short verb phrases (2-3 words max)

Return entities with their types and any aliases (alternative names for the same entity).
Return relationships as source -> relationship -> target triples."#,
            memory_content = memory_content,
            existing_nodes_str = existing_nodes_str
        );

        let schema = serde_json::json!({
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "The entity name"},
                            "type": {"type": "string", "enum": ["person", "place", "organization", "thing", "concept"]},
                            "aliases": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Alternative names for this entity"
                            }
                        },
                        "required": ["name", "type"]
                    }
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string", "description": "Source entity name"},
                            "target": {"type": "string", "description": "Target entity name"},
                            "relationship": {"type": "string", "description": "Relationship verb/phrase"}
                        },
                        "required": ["source", "target", "relationship"]
                    }
                }
            },
            "required": ["entities", "relationships"]
        });

        let response = self.call_with_schema(&prompt, Some(0.3), Some(1000), Some(schema)).await?;

        let result: ExtractedKnowledge = serde_json::from_str(&response)
            .map_err(|e| format!("Failed to parse knowledge graph extraction: {} - {}", e, response))?;

        Ok(result)
    }
}
