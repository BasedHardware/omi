// Persona LLM - Prompts and methods for AI persona generation
// Port from Python backend persona functionality

use super::client::LlmClient;
use crate::models::MemoryDB;
use serde::Deserialize;

// =========================================================================
// PROMPTS - Copied from Python backend
// =========================================================================

/// Prompt for condensing memories into a personality profile
/// Used to create a condensed representation of user's memories
const MEMORY_CONDENSATION_PROMPT: &str = r#"You are a personality analyst. Your task is to analyze a person's memories and create a comprehensive personality profile.

Given the following memories about a person, create a detailed personality profile that captures:

1. **Core Identity & Personality**
   - Key personality traits
   - Values and beliefs
   - Communication style
   - Emotional patterns

2. **Knowledge & Expertise**
   - Professional background
   - Areas of expertise
   - Skills and capabilities

3. **Interests & Preferences**
   - Hobbies and interests
   - Preferences and dislikes
   - Lifestyle choices

4. **Behavioral Patterns**
   - Decision-making style
   - Problem-solving approach
   - Social interaction patterns

5. **Personal Facts**
   - Key biographical details
   - Relationships mentioned
   - Important life events

MEMORIES:
{memories}

Create a structured personality profile that would allow an AI to accurately emulate this person's communication style and personality. Be specific and include concrete examples from the memories.

Respond in JSON format:
{
  "personality_summary": "A 2-3 paragraph summary of who this person is",
  "key_traits": ["list", "of", "dominant", "traits"],
  "communication_style": "Description of how they communicate",
  "knowledge_areas": ["list", "of", "expertise", "areas"],
  "interests": ["list", "of", "interests"],
  "quirks_and_habits": ["distinctive", "behaviors", "or", "phrases"],
  "personal_facts": ["important", "biographical", "details"]
}"#;

/// Prompt for generating the persona system prompt
/// This creates the actual instruction that the AI will use when chatting
const PERSONA_SYSTEM_PROMPT_TEMPLATE: &str = r#"You are a personality analyst. Based on the following personality profile, create a system prompt that will instruct an AI to accurately emulate this person.

PERSONALITY PROFILE:
{profile}

Create a system prompt that:
1. Instructs the AI to personify this individual accurately
2. Captures their unique voice, tone, and communication style
3. Includes key facts they would naturally reference
4. Sets boundaries on what the AI should and shouldn't do
5. Keeps responses concise (2-3 sentences, max 20 words typically)
6. Makes the AI opinionated and interactive, not generic

The prompt should start with "You are [Name]..." and be written in second person.

IMPORTANT RULES TO INCLUDE:
- Never mention being an AI or having limitations
- Respond naturally as this person would
- Reference personal experiences and opinions naturally
- Keep responses conversational and brief
- Be opinionated - this person has views and isn't afraid to share them

Respond with ONLY the system prompt text, no JSON or additional formatting."#;

/// Prompt for generating a short description
const DESCRIPTION_PROMPT: &str = r#"Based on this personality profile, write a compelling 1-2 sentence description (max 250 characters) that would make someone want to chat with this person's AI clone.

Focus on what makes them interesting or unique. Be specific, not generic.

PERSONALITY PROFILE:
{profile}

Respond with ONLY the description text, no quotes or additional formatting."#;

// =========================================================================
// RESPONSE TYPES
// =========================================================================

#[derive(Debug, Deserialize)]
struct CondensedProfile {
    personality_summary: String,
    key_traits: Vec<String>,
    communication_style: String,
    knowledge_areas: Vec<String>,
    interests: Vec<String>,
    quirks_and_habits: Vec<String>,
    personal_facts: Vec<String>,
}

/// Result of persona prompt generation
pub struct PersonaPromptResult {
    pub persona_prompt: String,
    pub description: String,
    pub memories_used: i32,
}

// =========================================================================
// PERSONA GENERATION
// =========================================================================

impl LlmClient {
    /// Generate persona prompt and description from user memories
    ///
    /// Takes a user's public memories and generates:
    /// 1. A condensed personality profile
    /// 2. A system prompt for the AI persona
    /// 3. A short description for display
    pub async fn generate_persona_from_memories(
        &self,
        user_name: &str,
        memories: &[MemoryDB],
    ) -> Result<PersonaPromptResult, Box<dyn std::error::Error + Send + Sync>> {
        if memories.is_empty() {
            return Err("No memories provided for persona generation".into());
        }

        let memories_used = memories.len() as i32;

        // Step 1: Format memories for the prompt
        let memories_text = memories
            .iter()
            .enumerate()
            .map(|(i, m)| format!("{}. {}", i + 1, m.content))
            .collect::<Vec<_>>()
            .join("\n");

        // Step 2: Condense memories into personality profile
        let condensation_prompt = MEMORY_CONDENSATION_PROMPT.replace("{memories}", &memories_text);
        let profile_json = self.call_with_schema(
            &condensation_prompt,
            Some(0.7),
            Some(2000),
            None,
        ).await?;

        let profile: CondensedProfile = serde_json::from_str(&profile_json)
            .map_err(|e| format!("Failed to parse profile: {}", e))?;

        // Format profile for next prompts
        let profile_text = format!(
            "Name: {}\n\nPersonality Summary:\n{}\n\nKey Traits: {}\n\nCommunication Style: {}\n\nKnowledge Areas: {}\n\nInterests: {}\n\nQuirks & Habits: {}\n\nPersonal Facts: {}",
            user_name,
            profile.personality_summary,
            profile.key_traits.join(", "),
            profile.communication_style,
            profile.knowledge_areas.join(", "),
            profile.interests.join(", "),
            profile.quirks_and_habits.join(", "),
            profile.personal_facts.join(", ")
        );

        // Step 3: Generate the persona system prompt
        let system_prompt_request = PERSONA_SYSTEM_PROMPT_TEMPLATE.replace("{profile}", &profile_text);
        let persona_prompt = self.call_text(&system_prompt_request, Some(0.7), Some(1500)).await?;

        // Step 4: Generate short description
        let description_request = DESCRIPTION_PROMPT.replace("{profile}", &profile_text);
        let description = self.call_text(&description_request, Some(0.7), Some(300)).await?;

        // Ensure description is within limits
        let description = if description.len() > 250 {
            let mut end = 247;
            while end > 0 && !description.is_char_boundary(end) {
                end -= 1;
            }
            description[..end].to_string() + "..."
        } else {
            description
        };

        Ok(PersonaPromptResult {
            persona_prompt,
            description,
            memories_used,
        })
    }
}
