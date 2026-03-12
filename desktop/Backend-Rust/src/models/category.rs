// Categories - Copied from Python backend (models.py)

use serde::{Deserialize, Serialize};

/// Categories for conversations
/// Copied from Python CategoryEnum
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Category {
    Personal,
    Education,
    Health,
    Finance,
    Legal,
    Philosophy,
    Spiritual,
    Science,
    Entrepreneurship,
    Parenting,
    #[serde(rename = "romantic")]
    Romance,
    Travel,
    Inspiration,
    Technology,
    Business,
    Social,
    Work,
    Sports,
    Politics,
    Literature,
    History,
    Architecture,
    Music,
    Weather,
    News,
    Entertainment,
    Psychology,
    Real,
    Design,
    Family,
    Economics,
    Environment,
    Other,
}

impl Default for Category {
    fn default() -> Self {
        Category::Other
    }
}

impl Category {
    /// Get all category values as a comma-separated string (for prompts)
    pub fn all_as_string() -> String {
        vec![
            "personal", "education", "health", "finance", "legal", "philosophy",
            "spiritual", "science", "entrepreneurship", "parenting", "romantic",
            "travel", "inspiration", "technology", "business", "social", "work",
            "sports", "politics", "literature", "history", "architecture", "music",
            "weather", "news", "entertainment", "psychology", "real", "design",
            "family", "economics", "environment", "other",
        ]
        .join(", ")
    }
}

/// Categories for memories
/// Copied from Python MemoryCategory
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum MemoryCategory {
    /// Facts ABOUT the user (preferences, network, projects)
    System,
    /// External wisdom WITH attribution from others
    Interesting,
    /// Manually added by user
    Manual,
    // Legacy categories for backward compatibility with old data
    Core,
    Hobbies,
    Lifestyle,
    Interests,
}

impl Default for MemoryCategory {
    fn default() -> Self {
        MemoryCategory::System
    }
}
