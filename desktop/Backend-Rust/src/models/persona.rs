// Persona models - For AI persona/clone feature
// Based on plugins_data collection with capability: "persona"

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

// =========================================================================
// REQUEST TYPES
// =========================================================================

/// Request to create a new persona
#[derive(Debug, Clone, Deserialize)]
pub struct CreatePersonaRequest {
    /// Display name for the persona
    pub name: String,
    /// Unique username (optional, auto-generated if not provided)
    pub username: Option<String>,
}

/// Request to update an existing persona
#[derive(Debug, Clone, Deserialize)]
pub struct UpdatePersonaRequest {
    /// Display name for the persona
    pub name: Option<String>,
    /// Short description (max 250 chars)
    pub description: Option<String>,
    /// Custom persona prompt (overrides auto-generated)
    pub persona_prompt: Option<String>,
    /// Avatar image URL
    pub image: Option<String>,
}

/// Request to regenerate persona prompt from current memories
#[derive(Debug, Clone, Deserialize)]
pub struct GeneratePromptRequest {
    // Empty for now, but allows adding options in the future
}

/// Query parameters for checking username availability
#[derive(Debug, Clone, Deserialize)]
pub struct CheckUsernameQuery {
    pub username: String,
}

// =========================================================================
// RESPONSE TYPES
// =========================================================================

/// Full persona response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PersonaResponse {
    pub id: String,
    pub uid: String,
    pub name: String,
    pub username: Option<String>,
    pub description: String,
    pub image: String,
    pub category: String,
    #[serde(default)]
    pub capabilities: Vec<String>,
    pub persona_prompt: Option<String>,
    #[serde(default)]
    pub approved: bool,
    pub status: String,
    #[serde(rename = "private")]
    pub is_private: bool,
    pub author: String,
    pub email: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    /// Number of public memories used to build the persona
    pub public_memories_count: Option<i32>,
}

/// Simple status response
#[derive(Debug, Clone, Serialize)]
pub struct PersonaStatusResponse {
    pub status: String,
    pub message: Option<String>,
}

/// Response for username availability check
#[derive(Debug, Clone, Serialize)]
pub struct UsernameAvailableResponse {
    pub available: bool,
    pub username: String,
}

/// Response for prompt generation
#[derive(Debug, Clone, Serialize)]
pub struct GeneratePromptResponse {
    pub persona_prompt: String,
    pub description: String,
    pub memories_used: i32,
}

// =========================================================================
// DATABASE MODEL
// =========================================================================

/// Persona as stored in Firestore (plugins_data collection)
/// Compatible with existing Python backend App model
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PersonaDB {
    pub id: String,
    /// Owner user ID
    pub uid: String,
    /// Display name
    pub name: String,
    /// Unique username for sharing
    pub username: Option<String>,
    /// Short description (max 250 chars)
    pub description: String,
    /// Avatar image URL
    pub image: String,
    /// Category - always "personality-emulation" for personas
    pub category: String,
    /// Capabilities - always ["persona"] for personas
    #[serde(default)]
    pub capabilities: Vec<String>,
    /// LLM-generated system prompt for the persona
    pub persona_prompt: Option<String>,
    /// Whether publicly listed (always false for user personas)
    #[serde(default)]
    pub approved: bool,
    /// Review status
    pub status: String,
    /// Whether private (not discoverable)
    #[serde(rename = "private")]
    pub is_private: bool,
    /// Author name (user's display name)
    pub author: String,
    /// Author email
    pub email: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl PersonaDB {
    /// Convert to API response
    pub fn to_response(self, public_memories_count: Option<i32>) -> PersonaResponse {
        PersonaResponse {
            id: self.id,
            uid: self.uid,
            name: self.name,
            username: self.username,
            description: self.description,
            image: self.image,
            category: self.category,
            capabilities: self.capabilities,
            persona_prompt: self.persona_prompt,
            approved: self.approved,
            status: self.status,
            is_private: self.is_private,
            author: self.author,
            email: self.email,
            created_at: self.created_at,
            updated_at: self.updated_at,
            public_memories_count,
        }
    }
}
