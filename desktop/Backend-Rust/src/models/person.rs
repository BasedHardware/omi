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

/// Request to create a new person
#[derive(Debug, Clone, Deserialize)]
pub struct CreatePersonRequest {
    pub name: String,
}

/// Request body for bulk segment assignment
#[derive(Debug, Clone, Deserialize)]
pub struct BulkAssignSegmentsRequest {
    pub segment_ids: Vec<String>,
    pub assign_type: String,
    pub value: Option<String>,
}
