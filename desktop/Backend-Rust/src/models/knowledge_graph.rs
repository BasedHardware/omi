// Knowledge Graph Models
// Nodes and edges for the 3D memory visualization

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Node types for the knowledge graph
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum NodeType {
    Person,
    Place,
    Organization,
    Thing,
    Concept,
}

impl Default for NodeType {
    fn default() -> Self {
        NodeType::Concept
    }
}

impl std::fmt::Display for NodeType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            NodeType::Person => write!(f, "person"),
            NodeType::Place => write!(f, "place"),
            NodeType::Organization => write!(f, "organization"),
            NodeType::Thing => write!(f, "thing"),
            NodeType::Concept => write!(f, "concept"),
        }
    }
}

/// A node in the knowledge graph representing an entity
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeGraphNode {
    pub id: String,
    pub label: String,
    pub node_type: NodeType,
    #[serde(default)]
    pub aliases: Vec<String>,
    #[serde(default)]
    pub memory_ids: Vec<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    // Lowercase versions for case-insensitive matching
    #[serde(default)]
    pub label_lower: String,
    #[serde(default)]
    pub aliases_lower: Vec<String>,
}

impl KnowledgeGraphNode {
    pub fn new(label: String, node_type: NodeType) -> Self {
        let now = Utc::now();
        let label_lower = label.to_lowercase();
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            label,
            node_type,
            aliases: vec![],
            memory_ids: vec![],
            created_at: now,
            updated_at: now,
            label_lower,
            aliases_lower: vec![],
        }
    }

    pub fn with_aliases(mut self, aliases: Vec<String>) -> Self {
        self.aliases_lower = aliases.iter().map(|a| a.to_lowercase()).collect();
        self.aliases = aliases;
        self
    }

    pub fn add_memory_id(&mut self, memory_id: String) {
        if !self.memory_ids.contains(&memory_id) {
            self.memory_ids.push(memory_id);
            self.updated_at = Utc::now();
        }
    }
}

/// An edge in the knowledge graph representing a relationship
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeGraphEdge {
    pub id: String,
    pub source_id: String,
    pub target_id: String,
    pub label: String,
    #[serde(default)]
    pub memory_ids: Vec<String>,
    pub created_at: DateTime<Utc>,
}

impl KnowledgeGraphEdge {
    pub fn new(source_id: String, target_id: String, label: String) -> Self {
        let id = format!("{}_{}_{}", source_id, label.replace(' ', "_"), target_id);
        Self {
            id,
            source_id,
            target_id,
            label,
            memory_ids: vec![],
            created_at: Utc::now(),
        }
    }

    pub fn add_memory_id(&mut self, memory_id: String) {
        if !self.memory_ids.contains(&memory_id) {
            self.memory_ids.push(memory_id);
        }
    }
}

// ============================================================================
// API Request/Response Types
// ============================================================================

/// Response containing the full knowledge graph
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeGraphResponse {
    pub nodes: Vec<KnowledgeGraphNode>,
    pub edges: Vec<KnowledgeGraphEdge>,
}

/// Request to rebuild the knowledge graph from memories
#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
pub struct RebuildGraphRequest {
    /// Optional limit on number of memories to process (default 500)
    pub limit: Option<usize>,
}

/// Response for rebuild status
#[derive(Debug, Clone, Serialize)]
pub struct RebuildGraphResponse {
    pub status: String,
    pub message: String,
}

/// Entity extracted by LLM from a memory
#[derive(Debug, Clone, Deserialize)]
pub struct ExtractedEntity {
    pub name: String,
    #[serde(rename = "type")]
    pub entity_type: String,
    #[serde(default)]
    pub aliases: Vec<String>,
}

/// Relationship extracted by LLM from a memory
#[derive(Debug, Clone, Deserialize)]
pub struct ExtractedRelationship {
    pub source: String,
    pub target: String,
    pub relationship: String,
}

/// LLM extraction result for a memory
#[derive(Debug, Clone, Deserialize)]
pub struct ExtractedKnowledge {
    #[serde(default)]
    pub entities: Vec<ExtractedEntity>,
    #[serde(default)]
    pub relationships: Vec<ExtractedRelationship>,
}

/// Status response for graph operations
#[derive(Debug, Clone, Serialize)]
pub struct KnowledgeGraphStatusResponse {
    pub success: bool,
    pub message: String,
}
