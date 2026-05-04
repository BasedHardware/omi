// Person models - Speaker voice profiles for transcript naming

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// A person (speaker profile) associated with the user
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Person {
    pub id: String,
    pub name: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

