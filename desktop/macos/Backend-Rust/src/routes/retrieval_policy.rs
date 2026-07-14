use serde_json::json;

use crate::models::chat_completions::{AnthropicMessage, ChatCompletionRequest, ChatMessage};

pub(crate) const REQUIRED_WEB_SEARCH_INSTRUCTION: &str = "<omi_retrieval_policy>\n\
Public web search is required for this turn. Call web_search before answering. Build the query only from the user's latest request and public entities in the recent exchange. Do not include private memories, conversations, screen history, tasks, or other personal context unless the user explicitly asked to relate that private context to public information.\n\
</omi_retrieval_policy>";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum RetrievalSource {
    PublicWeb,
    OmiPrivate,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RetrievalReason {
    ExplicitWeb,
    Freshness,
    AnaphoricLookup,
    ExplicitPrivate,
    Mixed,
    Auto,
}

impl RetrievalReason {
    fn as_str(self) -> &'static str {
        match self {
            Self::ExplicitWeb => "explicit_web",
            Self::Freshness => "freshness",
            Self::AnaphoricLookup => "anaphoric_lookup",
            Self::ExplicitPrivate => "explicit_private",
            Self::Mixed => "mixed",
            Self::Auto => "auto",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct RetrievalPolicy {
    required_sources: Vec<RetrievalSource>,
    prohibited_sources: Vec<RetrievalSource>,
    reason: RetrievalReason,
}

impl RetrievalPolicy {
    fn auto() -> Self {
        Self {
            required_sources: Vec::new(),
            prohibited_sources: Vec::new(),
            reason: RetrievalReason::Auto,
        }
    }

    pub(crate) fn requires(&self, source: RetrievalSource) -> bool {
        self.required_sources.contains(&source)
    }

    pub(crate) fn prohibits(&self, source: RetrievalSource) -> bool {
        self.prohibited_sources.contains(&source)
    }

    pub(crate) fn reason(&self) -> &'static str {
        self.reason.as_str()
    }
}

const EXPLICIT_WEB_PHRASES: &[&str] = &[
    "search the web",
    "search web",
    "search the internet",
    "search online",
    "look it up online",
    "look this up online",
    "look that up online",
    "find it online",
    "find this online",
    "find that online",
    "google it",
    "google this",
    "google that",
    "browse the web",
    "web search",
    "internet search",
];

const EXPLICIT_PRIVATE_PHRASES: &[&str] = &[
    "my conversations",
    "our conversations",
    "my memories",
    "your memory of me",
    "my screen history",
    "my screen activity",
    "my calendar",
    "your calendar",
    "my email",
    "your email",
    "my files",
    "your files",
    "my tasks",
    "your tasks",
    "my action items",
    "my notes",
    "your notes",
    "what did i say",
    "what have i said",
    "when did i",
    "what was i doing",
    "what do you remember about me",
];

const FRESH_PUBLIC_PHRASES: &[&str] = &[
    "latest news",
    "latest on",
    "what's the latest",
    "what is the latest",
    "current weather",
    "weather right now",
    "current price",
    "price right now",
    "current score",
    "score right now",
    "current president",
    "current ceo",
    "who is the current",
    "today's news",
    "news today",
];

/// Weather lookups commonly place the location between "weather" and the
/// freshness qualifier (for example, "what's the weather in NYC right now?").
/// Keep those public-current requests on the same forced-search path as the
/// fixed phrases above instead of leaving their tool choice to the model.
const CURRENT_WEATHER_PREFIXES: &[&str] = &[
    "what's the weather",
    "what is the weather",
    "whats the weather",
    "how's the weather",
    "how is the weather",
    "hows the weather",
    "weather in ",
    "weather for ",
    "weather at ",
];

/// A broad temporal qualifier is only a public-web signal when paired with a
/// public lookup subject. This covers current sports fixtures and schedules
/// without turning ordinary urgency ("help me with this right now") into a
/// web search. Explicit private-context requests still take precedence.
const FRESH_PUBLIC_TEMPORAL_QUALIFIERS: &[&str] = &["right now", "currently", "today", "this week"];
const FRESH_PUBLIC_LOOKUP_TERMS: &[&str] = &[
    "world cup",
    "schedule",
    "fixture",
    "standings",
    "match",
    "game",
    "playing",
    "score",
    "weather",
    "price",
    "news",
    "release",
    "released",
    "election",
    "market",
];

const ANAPHORIC_LOOKUP_PHRASES: &[&str] = &[
    "look it up",
    "look this up",
    "look that up",
    "can you look it up",
    "please look it up",
    "research it",
    "research this",
    "research that",
    "check it out",
    "find out",
];

fn contains_any(text: &str, phrases: &[&str]) -> bool {
    phrases.iter().any(|phrase| text.contains(phrase))
}

fn is_current_weather_lookup(text: &str) -> bool {
    contains_any(text, CURRENT_WEATHER_PREFIXES)
}

fn is_fresh_public_lookup(text: &str) -> bool {
    contains_any(text, FRESH_PUBLIC_PHRASES)
        || is_current_weather_lookup(text)
        || (contains_any(text, FRESH_PUBLIC_TEMPORAL_QUALIFIERS)
            && contains_any(text, FRESH_PUBLIC_LOOKUP_TERMS))
}

pub(crate) fn caller_disabled_tools(req: &ChatCompletionRequest) -> bool {
    matches!(
        &req.tool_choice,
        Some(serde_json::Value::String(value)) if value == "none"
    )
}

fn extract_text_content(content: &Option<serde_json::Value>) -> String {
    match content {
        Some(serde_json::Value::String(text)) => text.clone(),
        Some(serde_json::Value::Array(blocks)) => blocks
            .iter()
            .filter_map(|block| {
                (block.get("type").and_then(|value| value.as_str()) == Some("text"))
                    .then(|| block.get("text").and_then(|value| value.as_str()))
                    .flatten()
            })
            .collect::<Vec<_>>()
            .join("\n"),
        _ => String::new(),
    }
}

fn normalized_lookup_text(text: &str) -> String {
    text.trim()
        .trim_matches(|ch: char| !ch.is_alphanumeric())
        .to_ascii_lowercase()
}

fn previous_assistant_text(messages: &[ChatMessage]) -> String {
    messages
        .iter()
        .rev()
        .skip_while(|message| message.role != "user")
        .skip(1)
        .find(|message| message.role == "assistant")
        .map(|message| extract_text_content(&message.content).to_ascii_lowercase())
        .unwrap_or_default()
}

pub(crate) fn retrieval_policy(messages: &[ChatMessage]) -> RetrievalPolicy {
    // Only classify a fresh user turn. During a client-tool continuation the
    // latest OpenAI message has role=tool; reapplying a forced web choice there
    // would search repeatedly and prevent the agent from consuming tool results.
    let Some(latest_user) = messages.last().filter(|message| message.role == "user") else {
        return RetrievalPolicy::auto();
    };
    let latest = normalized_lookup_text(&extract_text_content(&latest_user.content));
    let explicit_web = contains_any(&latest, EXPLICIT_WEB_PHRASES);
    let explicit_private = contains_any(&latest, EXPLICIT_PRIVATE_PHRASES);

    if explicit_web && explicit_private {
        return RetrievalPolicy {
            required_sources: vec![RetrievalSource::PublicWeb, RetrievalSource::OmiPrivate],
            prohibited_sources: Vec::new(),
            reason: RetrievalReason::Mixed,
        };
    }
    if explicit_web {
        return RetrievalPolicy {
            required_sources: vec![RetrievalSource::PublicWeb],
            prohibited_sources: Vec::new(),
            reason: RetrievalReason::ExplicitWeb,
        };
    }
    if explicit_private {
        return RetrievalPolicy {
            required_sources: vec![RetrievalSource::OmiPrivate],
            prohibited_sources: vec![RetrievalSource::PublicWeb],
            reason: RetrievalReason::ExplicitPrivate,
        };
    }
    if is_fresh_public_lookup(&latest) {
        return RetrievalPolicy {
            required_sources: vec![RetrievalSource::PublicWeb],
            prohibited_sources: Vec::new(),
            reason: RetrievalReason::Freshness,
        };
    }
    if ANAPHORIC_LOOKUP_PHRASES.contains(&latest.as_str()) {
        let previous = previous_assistant_text(messages);
        if contains_any(&previous, EXPLICIT_PRIVATE_PHRASES) {
            return RetrievalPolicy {
                required_sources: vec![RetrievalSource::OmiPrivate],
                prohibited_sources: vec![RetrievalSource::PublicWeb],
                reason: RetrievalReason::ExplicitPrivate,
            };
        }
        return RetrievalPolicy {
            required_sources: vec![RetrievalSource::PublicWeb],
            prohibited_sources: Vec::new(),
            reason: RetrievalReason::AnaphoricLookup,
        };
    }

    RetrievalPolicy::auto()
}

pub(crate) fn prepend_latest_user_instruction(
    messages: &mut [AnthropicMessage],
    instruction: &str,
) {
    let Some(latest_user) = messages
        .iter_mut()
        .rev()
        .find(|message| message.role == "user")
    else {
        return;
    };
    match &mut latest_user.content {
        serde_json::Value::String(text) => {
            *text = format!("{instruction}\n\n{text}");
        }
        serde_json::Value::Array(blocks) => {
            blocks.insert(0, json!({"type": "text", "text": instruction}));
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn message(role: &str, text: &str) -> ChatMessage {
        ChatMessage {
            role: role.to_string(),
            content: Some(json!(text)),
            name: None,
            tool_calls: None,
            tool_call_id: None,
        }
    }

    #[test]
    fn requires_web_for_explicit_request() {
        let policy = retrieval_policy(&[message("user", "Search the web for HumanPost")]);
        assert!(policy.requires(RetrievalSource::PublicWeb));
        assert!(!policy.requires(RetrievalSource::OmiPrivate));
        assert_eq!(policy.reason, RetrievalReason::ExplicitWeb);
    }

    #[test]
    fn resolves_public_anaphoric_lookup_from_history() {
        let policy = retrieval_policy(&[
            message("user", "I'm working on humanpost.co now"),
            message(
                "assistant",
                "Is HumanPost separate from Vost or part of it?",
            ),
            message("user", "look it up"),
        ]);
        assert!(policy.requires(RetrievalSource::PublicWeb));
        assert_eq!(policy.reason, RetrievalReason::AnaphoricLookup);
    }

    #[test]
    fn keeps_private_anaphoric_lookup_inside_omi() {
        let policy = retrieval_policy(&[
            message("user", "What did I decide about pricing?"),
            message("assistant", "I can check your conversations and memories."),
            message("user", "look it up"),
        ]);
        assert!(policy.requires(RetrievalSource::OmiPrivate));
        assert!(policy.prohibits(RetrievalSource::PublicWeb));
        assert_eq!(policy.reason, RetrievalReason::ExplicitPrivate);
    }

    #[test]
    fn requires_web_for_high_confidence_freshness() {
        let policy =
            retrieval_policy(&[message("user", "What's the latest news about Anthropic?")]);
        assert!(policy.requires(RetrievalSource::PublicWeb));
        assert_eq!(policy.reason, RetrievalReason::Freshness);
    }

    #[test]
    fn requires_web_for_weather_with_a_location_and_current_time() {
        let policy = retrieval_policy(&[message("user", "What's the weather in NYC right now?")]);
        assert!(policy.requires(RetrievalSource::PublicWeb));
        assert!(!policy.prohibits(RetrievalSource::PublicWeb));
        assert_eq!(policy.reason, RetrievalReason::Freshness);
    }

    #[test]
    fn requires_web_for_current_public_sports_schedule() {
        let policy =
            retrieval_policy(&[message("user", "Who's playing in the World Cup right now?")]);
        assert!(policy.requires(RetrievalSource::PublicWeb));
        assert!(!policy.prohibits(RetrievalSource::PublicWeb));
        assert_eq!(policy.reason, RetrievalReason::Freshness);
    }

    #[test]
    fn keeps_private_weather_history_queries_off_the_public_web() {
        let policy = retrieval_policy(&[message(
            "user",
            "Search my conversations for weather in NYC",
        )]);
        assert!(!policy.requires(RetrievalSource::PublicWeb));
        assert!(policy.prohibits(RetrievalSource::PublicWeb));
        assert_eq!(policy.reason, RetrievalReason::ExplicitPrivate);
    }

    #[test]
    fn supports_mixed_public_and_private_sources() {
        let policy = retrieval_policy(&[message(
            "user",
            "Search the web and my conversations for HumanPost",
        )]);
        assert!(policy.requires(RetrievalSource::PublicWeb));
        assert!(policy.requires(RetrievalSource::OmiPrivate));
        assert_eq!(policy.reason, RetrievalReason::Mixed);
    }

    #[test]
    fn leaves_ordinary_questions_on_auto() {
        assert_eq!(
            retrieval_policy(&[message("user", "Help me name this project")]),
            RetrievalPolicy::auto()
        );
    }

    #[test]
    fn does_not_reforce_web_during_tool_continuation() {
        let mut tool_result = message("tool", "search result");
        tool_result.tool_call_id = Some("call_123".to_string());
        assert_eq!(
            retrieval_policy(&[
                message("user", "Search the web and my conversations for HumanPost"),
                message("assistant", "I'll check both."),
                tool_result,
            ]),
            RetrievalPolicy::auto()
        );
    }
}
