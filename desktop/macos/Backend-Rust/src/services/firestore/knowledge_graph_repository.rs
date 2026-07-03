use super::*;

impl FirestoreService {
    pub async fn upsert_kg_node(
        &self,
        uid: &str,
        node: &crate::models::KnowledgeGraphNode,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            KG_NODES_SUBCOLLECTION,
            node.id
        );

        // Build aliases arrays
        let aliases_values: Vec<Value> = node
            .aliases
            .iter()
            .map(|a| json!({"stringValue": a}))
            .collect();

        let aliases_lower_values: Vec<Value> = node
            .aliases_lower
            .iter()
            .map(|a| json!({"stringValue": a}))
            .collect();

        let memory_ids_values: Vec<Value> = node
            .memory_ids
            .iter()
            .map(|m| json!({"stringValue": m}))
            .collect();

        let doc = json!({
            "fields": {
                "id": {"stringValue": &node.id},
                "label": {"stringValue": &node.label},
                "node_type": {"stringValue": node.node_type.to_string()},
                "aliases": {"arrayValue": {"values": aliases_values}},
                "aliases_lower": {"arrayValue": {"values": aliases_lower_values}},
                "memory_ids": {"arrayValue": {"values": memory_ids_values}},
                "label_lower": {"stringValue": &node.label_lower},
                "created_at": {"timestampValue": node.created_at.to_rfc3339()},
                "updated_at": {"timestampValue": node.updated_at.to_rfc3339()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to upsert KG node: {}", error_text).into());
        }

        Ok(node.id.clone())
    }

    /// Create or update a knowledge graph edge
    pub async fn upsert_kg_edge(
        &self,
        uid: &str,
        edge: &crate::models::KnowledgeGraphEdge,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            KG_EDGES_SUBCOLLECTION,
            edge.id
        );

        let memory_ids_values: Vec<Value> = edge
            .memory_ids
            .iter()
            .map(|m| json!({"stringValue": m}))
            .collect();

        let doc = json!({
            "fields": {
                "id": {"stringValue": &edge.id},
                "source_id": {"stringValue": &edge.source_id},
                "target_id": {"stringValue": &edge.target_id},
                "label": {"stringValue": &edge.label},
                "memory_ids": {"arrayValue": {"values": memory_ids_values}},
                "created_at": {"timestampValue": edge.created_at.to_rfc3339()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to upsert KG edge: {}", error_text).into());
        }

        Ok(edge.id.clone())
    }

    /// Get all knowledge graph nodes for a user
    pub async fn get_kg_nodes(
        &self,
        uid: &str,
    ) -> Result<Vec<crate::models::KnowledgeGraphNode>, Box<dyn std::error::Error + Send + Sync>>
    {
        let base_url = format!(
            "{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            KG_NODES_SUBCOLLECTION
        );
        let mut page_token: Option<String> = None;
        let mut nodes = Vec::new();

        loop {
            let url = match &page_token {
                Some(token) => format!(
                    "{}?pageSize=500&pageToken={}",
                    base_url,
                    urlencoding::encode(token)
                ),
                None => format!("{}?pageSize=500", base_url),
            };

            let response = self
                .build_request(reqwest::Method::GET, &url)
                .await?
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Failed to get KG nodes: {}", error_text).into());
            }

            let result: Value = response.json().await?;
            if let Some(documents) = result.get("documents").and_then(|d| d.as_array()) {
                nodes.extend(
                    documents
                        .iter()
                        .filter_map(|doc| self.parse_kg_node(doc).ok()),
                );
            }
            page_token = result
                .get("nextPageToken")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            if page_token.is_none() {
                break;
            }
        }

        tracing::info!("Found {} KG nodes for user {}", nodes.len(), uid);
        Ok(nodes)
    }

    /// Get all knowledge graph edges for a user
    pub async fn get_kg_edges(
        &self,
        uid: &str,
    ) -> Result<Vec<crate::models::KnowledgeGraphEdge>, Box<dyn std::error::Error + Send + Sync>>
    {
        let base_url = format!(
            "{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            KG_EDGES_SUBCOLLECTION
        );
        let mut page_token: Option<String> = None;
        let mut edges = Vec::new();

        loop {
            let url = match &page_token {
                Some(token) => format!(
                    "{}?pageSize=500&pageToken={}",
                    base_url,
                    urlencoding::encode(token)
                ),
                None => format!("{}?pageSize=500", base_url),
            };

            let response = self
                .build_request(reqwest::Method::GET, &url)
                .await?
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Failed to get KG edges: {}", error_text).into());
            }

            let result: Value = response.json().await?;
            if let Some(documents) = result.get("documents").and_then(|d| d.as_array()) {
                edges.extend(
                    documents
                        .iter()
                        .filter_map(|doc| self.parse_kg_edge(doc).ok()),
                );
            }
            page_token = result
                .get("nextPageToken")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            if page_token.is_none() {
                break;
            }
        }

        tracing::info!("Found {} KG edges for user {}", edges.len(), uid);
        Ok(edges)
    }

    /// Delete all knowledge graph data for a user
    pub async fn delete_kg_data(
        &self,
        uid: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // Delete all nodes
        let nodes = self.get_kg_nodes(uid).await?;
        for node in &nodes {
            let url = format!(
                "{}/{}/{}/{}/{}",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                KG_NODES_SUBCOLLECTION,
                node.id
            );
            let response = self
                .build_request(reqwest::Method::DELETE, &url)
                .await?
                .send()
                .await?;
            if !response.status().is_success()
                && response.status() != reqwest::StatusCode::NOT_FOUND
            {
                let error_text = response.text().await?;
                return Err(format!("Failed to delete KG node: {}", error_text).into());
            }
        }

        // Delete all edges
        let edges = self.get_kg_edges(uid).await?;
        for edge in &edges {
            let url = format!(
                "{}/{}/{}/{}/{}",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                KG_EDGES_SUBCOLLECTION,
                edge.id
            );
            let response = self
                .build_request(reqwest::Method::DELETE, &url)
                .await?
                .send()
                .await?;
            if !response.status().is_success()
                && response.status() != reqwest::StatusCode::NOT_FOUND
            {
                let error_text = response.text().await?;
                return Err(format!("Failed to delete KG edge: {}", error_text).into());
            }
        }

        tracing::info!(
            "Deleted {} nodes and {} edges for user {}",
            nodes.len(),
            edges.len(),
            uid
        );
        Ok(())
    }

    /// Parse a knowledge graph node from Firestore document
    fn parse_kg_node(
        &self,
        doc: &Value,
    ) -> Result<crate::models::KnowledgeGraphNode, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;

        let node_type_str = self
            .parse_string(fields, "node_type")
            .unwrap_or_else(|| "concept".to_string());
        let node_type = match node_type_str.as_str() {
            "person" => crate::models::NodeType::Person,
            "place" => crate::models::NodeType::Place,
            "organization" => crate::models::NodeType::Organization,
            "thing" => crate::models::NodeType::Thing,
            _ => crate::models::NodeType::Concept,
        };

        Ok(crate::models::KnowledgeGraphNode {
            id: self.parse_string(fields, "id").unwrap_or_default(),
            label: self.parse_string(fields, "label").unwrap_or_default(),
            node_type,
            aliases: self.parse_string_array(fields, "aliases"),
            memory_ids: self.parse_string_array(fields, "memory_ids"),
            label_lower: self.parse_string(fields, "label_lower").unwrap_or_default(),
            aliases_lower: self.parse_string_array(fields, "aliases_lower"),
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
            updated_at: self
                .parse_timestamp_optional(fields, "updated_at")
                .unwrap_or_else(Utc::now),
        })
    }

    /// Parse a knowledge graph edge from Firestore document
    fn parse_kg_edge(
        &self,
        doc: &Value,
    ) -> Result<crate::models::KnowledgeGraphEdge, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;

        Ok(crate::models::KnowledgeGraphEdge {
            id: self.parse_string(fields, "id").unwrap_or_default(),
            source_id: self.parse_string(fields, "source_id").unwrap_or_default(),
            target_id: self.parse_string(fields, "target_id").unwrap_or_default(),
            label: self.parse_string(fields, "label").unwrap_or_default(),
            memory_ids: self.parse_string_array(fields, "memory_ids"),
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
        })
    }
}
