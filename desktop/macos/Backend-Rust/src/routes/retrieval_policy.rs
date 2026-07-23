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
    ExplicitNoWeb,
    Freshness,
    AnaphoricLookup,
    ResearchIntent,
    ExplicitPrivate,
    Mixed,
    Auto,
}

impl RetrievalReason {
    fn as_str(self) -> &'static str {
        match self {
            Self::ExplicitWeb => "explicit_web",
            Self::ExplicitNoWeb => "explicit_no_web",
            Self::Freshness => "freshness",
            Self::AnaphoricLookup => "anaphoric_lookup",
            Self::ResearchIntent => "research_intent",
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

    /// True only when the user asked for the public web in so many words.
    ///
    /// Everything else (`Freshness`, `AnaphoricLookup`, `ResearchIntent`) is a
    /// heuristic guess, so it may steer a turn but must never fail one: a route
    /// that cannot search the web still owes the user an answer.
    pub(crate) fn web_requirement_is_explicit(&self) -> bool {
        matches!(
            self.reason,
            RetrievalReason::ExplicitWeb | RetrievalReason::Mixed
        )
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

const EXPLICIT_WEB_PROHIBITION_PHRASES: &[&str] = &[
    "don't call web search",
    "do not call web search",
    "don't call the web search",
    "do not call the web search",
    "don't call internet search",
    "do not call internet search",
    "don't call the internet search",
    "do not call the internet search",
    "don't use web search",
    "do not use web search",
    "don't use the web search",
    "do not use the web search",
    "don't use internet search",
    "do not use internet search",
    "don't use the internet search",
    "do not use the internet search",
    "don't search the web",
    "do not search the web",
    "don't search the internet",
    "do not search the internet",
    "without web search",
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

/// Implicit web-research asks pair a lookup verb with a public-web locus
/// ("find out who X is ... online", "look him up on the web", "research X on the
/// internet"). They carry none of the fixed `EXPLICIT_WEB_PHRASES`, so they fell
/// through to `auto` and the model was handed no web tool — users saw "I can't
/// search the web" even though the capability exists. Requiring both a research
/// verb and an explicit online/web locus keeps this high-precision; it is still
/// a non-explicit guess, so a web-unavailable route degrades to model knowledge
/// instead of failing the turn.
const RESEARCH_INTENT_VERBS: &[&str] = &[
    "find out",
    "look up",
    "look him up",
    "look her up",
    "look them up",
    "research",
    "tell me about",
    "everything about",
    "everything on",
    "all about",
    "information about",
    "information on",
    "who is",
    "who's",
];

const PUBLIC_WEB_LOCUS: &[&str] = &["online", "on the web", "on the internet"];

/// The generic qualifier+subject pairing describes a short conversational ask
/// ("who is playing today?"). Service synthesis prompts, pasted documents and
/// agent instructions are long and hit these common words by accident, so they
/// stay out of the broad heuristic. The fixed phrases above still apply at any
/// length.
const MAX_GENERIC_LOOKUP_CHARS: usize = 240;

fn contains_any(text: &str, phrases: &[&str]) -> bool {
    phrases.iter().any(|phrase| text.contains(phrase))
}

/// Substring matching on single words reads "market" out of "marketing" and
/// "game" out of "gameplan", so the generic terms match on word boundaries.
fn contains_any_word(text: &str, words: &[&str]) -> bool {
    words.iter().any(|word| {
        text.match_indices(word).any(|(start, _)| {
            let before_is_word = text[..start]
                .chars()
                .next_back()
                .is_some_and(|ch| ch.is_alphanumeric());
            let after_is_word = text[start + word.len()..]
                .chars()
                .next()
                .is_some_and(|ch| ch.is_alphanumeric());
            !before_is_word && !after_is_word
        })
    })
}

fn is_current_weather_lookup(text: &str) -> bool {
    contains_any(text, CURRENT_WEATHER_PREFIXES)
}

fn is_fresh_public_lookup(text: &str) -> bool {
    contains_any(text, FRESH_PUBLIC_PHRASES)
        || is_current_weather_lookup(text)
        || (text.len() <= MAX_GENERIC_LOOKUP_CHARS
            && contains_any_word(text, FRESH_PUBLIC_TEMPORAL_QUALIFIERS)
            && contains_any_word(text, FRESH_PUBLIC_LOOKUP_TERMS))
}

/// A lookup verb paired with an explicit online/web locus, on a short turn.
/// Locus matches on word boundaries so "on the web" does not read out of "on the
/// webinar"; the length cap keeps long machine-written prompts (which never name
/// a web locus about a subject anyway) out of the heuristic.
fn is_research_intent_lookup(text: &str) -> bool {
    text.len() <= MAX_GENERIC_LOOKUP_CHARS
        && contains_any_word(text, PUBLIC_WEB_LOCUS)
        && contains_any(text, RESEARCH_INTENT_VERBS)
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
        .replace(['\u{2018}', '\u{2019}'], "'")
        .to_ascii_lowercase()
}

fn explicitly_prohibits_public_web(text: &str) -> bool {
    if EXPLICIT_WEB_PROHIBITION_PHRASES.iter().any(|phrase| {
        text.match_indices(phrase).any(|(start, _)| {
            let suffix = text[start + phrase.len()..].trim_start();
            let starts_with_result_noun = ["result", "results"].iter().any(|noun| {
                suffix
                    .strip_prefix(noun)
                    .is_some_and(|tail| tail.chars().next().is_none_or(|ch| !ch.is_alphanumeric()))
            });
            !starts_with_result_noun
        })
    }) {
        return true;
    }

    // The Beta prompt used a pronoun after naming the "web search tool".
    // Keep that special case local and causal so unrelated phrases such as
    // "search the web, but don't call it authoritative" remain explicit web
    // requests instead of being inverted by a context-free substring.
    ["web search tool", "internet search tool"]
        .iter()
        .filter_map(|referent| text.find(referent).map(|index| (referent, index)))
        .any(|(referent, index)| {
            let tail = text[index + referent.len()..]
                .chars()
                .take(160)
                .collect::<String>();
            contains_any(
                &tail,
                &[
                    "don't call it because",
                    "do not call it because",
                    "don't call it again",
                    "do not call it again",
                ],
            )
        })
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
    let explicitly_prohibits_web = explicit_web && explicitly_prohibits_public_web(&latest);
    let explicit_private = contains_any(&latest, EXPLICIT_PRIVATE_PHRASES);

    if explicitly_prohibits_web {
        return RetrievalPolicy {
            required_sources: if explicit_private {
                vec![RetrievalSource::OmiPrivate]
            } else {
                Vec::new()
            },
            prohibited_sources: vec![RetrievalSource::PublicWeb],
            reason: if explicit_private {
                RetrievalReason::ExplicitPrivate
            } else {
                RetrievalReason::ExplicitNoWeb
            },
        };
    }
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
    if is_research_intent_lookup(&latest) {
        return RetrievalPolicy {
            required_sources: vec![RetrievalSource::PublicWeb],
            prohibited_sources: Vec::new(),
            reason: RetrievalReason::ResearchIntent,
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
    fn leaves_a_service_synthesis_prompt_on_auto() {
        // The calendar/gmail/notes readers synthesize with a long machine-written
        // prompt that happens to contain "today" and "schedule". Classifying it as
        // a public-web lookup routed the import into the web-search-unavailable
        // failure and dropped every extracted memory.
        let policy = retrieval_policy(&[message(
            "user",
            "Analyze these calendar events and extract a profile.\n\
             Today's date: 2026-07-14\n\
             - Extract 10-15 memories (facts about their role, recurring meetings, \
             relationships, routines, interests, work schedule, hobbies, social life)\n\
             - Profile should summarize professional identity and schedule patterns",
        )]);
        assert_eq!(policy, RetrievalPolicy::auto());
    }

    #[test]
    fn does_not_match_generic_lookup_terms_inside_longer_words() {
        let policy =
            retrieval_policy(&[message("user", "Review the marketing copy I wrote today")]);
        assert_eq!(policy, RetrievalPolicy::auto());
    }

    #[test]
    fn only_an_explicit_request_is_a_strict_web_requirement() {
        let guessed = retrieval_policy(&[message("user", "Who's playing in the World Cup today?")]);
        assert!(guessed.requires(RetrievalSource::PublicWeb));
        assert!(!guessed.web_requirement_is_explicit());

        let asked = retrieval_policy(&[message("user", "Search the web for the World Cup final")]);
        assert!(asked.requires(RetrievalSource::PublicWeb));
        assert!(asked.web_requirement_is_explicit());
    }

    #[test]
    fn requires_web_for_implicit_research_with_a_web_locus() {
        // The reported repro: no fixed trigger phrase, but a lookup verb plus an
        // explicit "online" locus. Previously fell through to auto and the model
        // was handed no web tool, so it told the user it couldn't search.
        let policy = retrieval_policy(&[message(
            "user",
            "Find out who David Zhang is and get every piece of information \
             available on him online.",
        )]);
        assert!(policy.requires(RetrievalSource::PublicWeb));
        assert!(!policy.prohibits(RetrievalSource::PublicWeb));
        assert_eq!(policy.reason, RetrievalReason::ResearchIntent);
    }

    #[test]
    fn research_intent_is_a_guess_not_a_strict_requirement() {
        // A guess must degrade (answer from model knowledge) on a web-unavailable
        // route rather than fail the turn.
        let policy = retrieval_policy(&[message("user", "look him up on the web")]);
        assert!(policy.requires(RetrievalSource::PublicWeb));
        assert!(!policy.web_requirement_is_explicit());
    }

    #[test]
    fn research_intent_requires_both_a_verb_and_a_web_locus() {
        // A lookup verb with no online/web locus stays on auto (the model may
        // still choose its own tools); a locus with no research verb likewise.
        assert_eq!(
            retrieval_policy(&[message("user", "Find out who David Zhang is")]),
            RetrievalPolicy::auto()
        );
        assert_eq!(
            retrieval_policy(&[message("user", "The team standup is online today")]),
            RetrievalPolicy::auto()
        );
    }

    #[test]
    fn private_context_still_wins_over_a_research_web_locus() {
        // "what did i say" is an explicit private phrase; the trailing "online"
        // must not flip the turn onto the public web.
        let policy = retrieval_policy(&[message(
            "user",
            "What did I say about the pricing I found online?",
        )]);
        assert!(policy.prohibits(RetrievalSource::PublicWeb));
        assert_eq!(policy.reason, RetrievalReason::ExplicitPrivate);
    }

    #[test]
    fn leaves_a_long_prompt_that_mentions_research_and_online_on_auto() {
        // A machine-written synthesis prompt can contain "research" and "online"
        // by accident; the length cap keeps it off the forced-search path.
        let policy = retrieval_policy(&[message(
            "user",
            "Analyze these calendar events and extract a profile.\n\
             Today's date: 2026-07-23\n\
             - Extract 10-15 memories about their role, recurring meetings, \
             online research habits, relationships, routines, interests, and \
             the way they schedule collaborative work across time zones.",
        )]);
        assert_eq!(policy, RetrievalPolicy::auto());
    }

    #[test]
    fn explicit_web_prohibition_wins_over_web_reference() {
        for request in [
            "Do you know why the web search tool times out? Don't call it because it will time out again.",
            "Do you know why the web search tool times out? Don’t call it because it will time out again.",
            "Do not call the web search tool; answer from what you already know.",
            "Do not use web search resulting in external network access.",
            "Explain web search without web search.",
            "Do not use web search; answer from what you already know.",
        ] {
            let policy = retrieval_policy(&[message("user", request)]);
            assert!(!policy.requires(RetrievalSource::PublicWeb));
            assert!(policy.prohibits(RetrievalSource::PublicWeb));
            assert_eq!(policy.reason, RetrievalReason::ExplicitNoWeb);
        }
    }

    #[test]
    fn unrelated_negation_does_not_invert_an_explicit_web_request() {
        for request in [
            "Search the web for naming ideas, but don't call it Omi.",
            "Search the web for webpack docs; don't use webpack examples.",
            "Use web search for the answer, but don't call it authoritative.",
            "Search the web because I got no web search results.",
            "Search the web, but do not use the web search results as the only source.",
            "Search the web and explain why no web search results appeared.",
            "Search the web for the term no web search.",
        ] {
            let policy = retrieval_policy(&[message("user", request)]);
            assert!(policy.requires(RetrievalSource::PublicWeb));
            assert!(!policy.prohibits(RetrievalSource::PublicWeb));
            assert_eq!(policy.reason, RetrievalReason::ExplicitWeb);
        }
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
