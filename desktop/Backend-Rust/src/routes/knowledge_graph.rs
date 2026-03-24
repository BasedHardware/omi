// Knowledge Graph Routes
// API endpoints for the 3D memory visualization

use axum::{
    extract::{Query, State},
    http::StatusCode,
    routing::{delete, get, post},
    Json, Router,
};
use serde::Deserialize;
use std::collections::HashMap;

use crate::auth::AuthUser;
use crate::llm::LlmClient;
use crate::models::{
    KnowledgeGraphEdge, KnowledgeGraphNode, KnowledgeGraphResponse, KnowledgeGraphStatusResponse,
    NodeType, RebuildGraphResponse,
};
use crate::AppState;

/// GET /v1/knowledge-graph - Get the full knowledge graph
async fn get_knowledge_graph(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<KnowledgeGraphResponse>, StatusCode> {
    tracing::info!("Getting knowledge graph for user {}", user.uid);

    let nodes = state
        .firestore
        .get_kg_nodes(&user.uid)
        .await
        .map_err(|e| {
            tracing::error!("Failed to get KG nodes: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let edges = state
        .firestore
        .get_kg_edges(&user.uid)
        .await
        .map_err(|e| {
            tracing::error!("Failed to get KG edges: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    Ok(Json(KnowledgeGraphResponse { nodes, edges }))
}

/// Query parameters for rebuild
#[derive(Debug, Deserialize)]
pub struct RebuildQuery {
    pub limit: Option<usize>,
}

/// POST /v1/knowledge-graph/rebuild - Rebuild the knowledge graph from memories
async fn rebuild_knowledge_graph(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<RebuildQuery>,
) -> Result<Json<RebuildGraphResponse>, StatusCode> {
    tracing::info!("Rebuilding knowledge graph for user {}", user.uid);

    let limit = query.limit.unwrap_or(500);

    // Check for Gemini API key
    let api_key = state.config.gemini_api_key.clone().ok_or_else(|| {
        tracing::error!("Gemini API key not configured");
        StatusCode::SERVICE_UNAVAILABLE
    })?;

    // Delete existing graph
    if let Err(e) = state.firestore.delete_kg_data(&user.uid).await {
        tracing::warn!("Failed to delete existing graph: {}", e);
    }

    // Get memories to process
    let memories = state
        .firestore
        .get_memories(&user.uid, limit)
        .await
        .map_err(|e| {
            tracing::error!("Failed to get memories: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    if memories.is_empty() {
        tracing::info!("No memories found for user {}, skipping rebuild", user.uid);
        return Ok(Json(RebuildGraphResponse {
            status: "completed".to_string(),
            message: "No memories to process".to_string(),
        }));
    }

    tracing::info!("Processing {} memories for knowledge graph", memories.len());

    // Create LLM client
    let llm = LlmClient::new(api_key);

    // Track nodes by lowercase label for deduplication
    let mut node_map: HashMap<String, KnowledgeGraphNode> = HashMap::new();
    let mut edges: Vec<KnowledgeGraphEdge> = Vec::new();

    // Process memories in batches
    for memory in &memories {
        // Get current nodes for deduplication context
        let existing_nodes: Vec<KnowledgeGraphNode> = node_map.values().cloned().collect();

        // Extract entities from this memory
        let extraction = match llm
            .extract_knowledge_graph_entities(&memory.content, &existing_nodes)
            .await
        {
            Ok(e) => e,
            Err(e) => {
                tracing::warn!("Failed to extract entities from memory {}: {}", memory.id, e);
                continue;
            }
        };

        // Process extracted entities
        for entity in extraction.entities {
            let label_lower = entity.name.to_lowercase();

            // Check if entity already exists (by label or alias)
            let existing_key = node_map
                .iter()
                .find(|(_, n)| {
                    n.label_lower == label_lower
                        || n.aliases_lower.contains(&label_lower)
                        || entity
                            .aliases
                            .iter()
                            .any(|a| n.label_lower == a.to_lowercase())
                })
                .map(|(k, _)| k.clone());

            if let Some(key) = existing_key {
                // Update existing node with new memory reference
                if let Some(node) = node_map.get_mut(&key) {
                    node.add_memory_id(memory.id.clone());
                }
            } else {
                // Create new node
                let node_type = match entity.entity_type.as_str() {
                    "person" => NodeType::Person,
                    "place" => NodeType::Place,
                    "organization" => NodeType::Organization,
                    "thing" => NodeType::Thing,
                    _ => NodeType::Concept,
                };

                let mut node = KnowledgeGraphNode::new(entity.name.clone(), node_type);
                node = node.with_aliases(entity.aliases);
                node.add_memory_id(memory.id.clone());

                node_map.insert(label_lower, node);
            }
        }

        // Process relationships
        for rel in extraction.relationships {
            let source_lower = rel.source.to_lowercase();
            let target_lower = rel.target.to_lowercase();

            // Find source and target nodes
            let source_id = node_map
                .iter()
                .find(|(_, n)| n.label_lower == source_lower || n.aliases_lower.contains(&source_lower))
                .map(|(_, n)| n.id.clone());

            let target_id = node_map
                .iter()
                .find(|(_, n)| n.label_lower == target_lower || n.aliases_lower.contains(&target_lower))
                .map(|(_, n)| n.id.clone());

            if let (Some(src), Some(tgt)) = (source_id, target_id) {
                let mut edge = KnowledgeGraphEdge::new(src, tgt, rel.relationship);
                edge.add_memory_id(memory.id.clone());
                edges.push(edge);
            }
        }
    }

    // Save nodes to Firestore
    let nodes: Vec<KnowledgeGraphNode> = node_map.into_values().collect();
    for node in &nodes {
        if let Err(e) = state.firestore.upsert_kg_node(&user.uid, node).await {
            tracing::warn!("Failed to save node {}: {}", node.label, e);
        }
    }

    // Deduplicate edges (same source, target, label)
    let mut edge_keys: HashMap<String, KnowledgeGraphEdge> = HashMap::new();
    for edge in edges {
        let key = format!("{}_{}_{}", edge.source_id, edge.label, edge.target_id);
        edge_keys
            .entry(key)
            .and_modify(|e| {
                for mid in &edge.memory_ids {
                    if !e.memory_ids.contains(mid) {
                        e.memory_ids.push(mid.clone());
                    }
                }
            })
            .or_insert(edge);
    }

    // Save edges to Firestore
    for edge in edge_keys.values() {
        if let Err(e) = state.firestore.upsert_kg_edge(&user.uid, edge).await {
            tracing::warn!("Failed to save edge {}: {}", edge.id, e);
        }
    }

    tracing::info!(
        "Built knowledge graph with {} nodes and {} edges for user {}",
        nodes.len(),
        edge_keys.len(),
        user.uid
    );

    Ok(Json(RebuildGraphResponse {
        status: "completed".to_string(),
        message: format!(
            "Built graph with {} nodes and {} edges from {} memories",
            nodes.len(),
            edge_keys.len(),
            memories.len()
        ),
    }))
}

/// DELETE /v1/knowledge-graph - Delete the knowledge graph
async fn delete_knowledge_graph(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<KnowledgeGraphStatusResponse>, StatusCode> {
    tracing::info!("Deleting knowledge graph for user {}", user.uid);

    state
        .firestore
        .delete_kg_data(&user.uid)
        .await
        .map_err(|e| {
            tracing::error!("Failed to delete KG data: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    Ok(Json(KnowledgeGraphStatusResponse {
        success: true,
        message: "Knowledge graph deleted".to_string(),
    }))
}

/// Build knowledge graph routes
pub fn knowledge_graph_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/knowledge-graph", get(get_knowledge_graph))
        .route("/v1/knowledge-graph/rebuild", post(rebuild_knowledge_graph))
        .route("/v1/knowledge-graph", delete(delete_knowledge_graph))
}
