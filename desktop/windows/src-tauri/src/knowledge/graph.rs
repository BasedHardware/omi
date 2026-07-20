use std::collections::BTreeMap;

use rusqlite::{params, params_from_iter, types::ValueRef, Connection};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::State;

use super::{file_index::IndexedFileRecord, KnowledgeStore};

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalKnowledgeGraph {
    pub nodes: Vec<LocalKnowledgeGraphNode>,
    pub edges: Vec<LocalKnowledgeGraphEdge>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalKnowledgeGraphNode {
    pub id: String,
    pub label: String,
    pub node_type: String,
    pub summary: String,
    pub source: String,
    pub created_at: i64,
    pub aliases: Option<Vec<String>>,
    pub source_refs: Option<Vec<String>>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalKnowledgeGraphEdge {
    pub id: String,
    pub source_id: String,
    pub target_id: String,
    pub label: String,
    pub created_at: i64,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalKnowledgeGraphStatus {
    node_count: i64,
    edge_count: i64,
    last_built_at: Option<i64>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OnboardingGraphNode {
    pub id: String,
    pub label: String,
    pub node_type: String,
    pub aliases: Option<Vec<String>>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OnboardingGraphEdge {
    pub id: String,
    pub source_id: String,
    pub target_id: String,
    pub label: String,
}
#[derive(Serialize)]
pub struct KnowledgeGraph {
    pub(crate) nodes: Vec<KnowledgeGraphNode>,
    edges: Vec<KnowledgeGraphEdge>,
}
#[derive(Serialize)]
pub struct KnowledgeGraphNode {
    id: String,
    pub(crate) label: String,
    node_type: String,
    aliases: Vec<String>,
    memory_ids: Vec<String>,
}
#[derive(Serialize)]
pub struct KnowledgeGraphEdge {
    id: String,
    source_id: String,
    target_id: String,
    label: String,
    memory_ids: Vec<String>,
}
#[derive(Serialize)]
pub struct KgSqlResult {
    columns: Vec<String>,
    rows: Vec<BTreeMap<String, Value>>,
}

pub(crate) fn initialize(connection: &Connection) -> Result<(), String> {
    connection.execute_batch("CREATE TABLE IF NOT EXISTS local_kg_nodes (id TEXT PRIMARY KEY, label TEXT NOT NULL, node_type TEXT NOT NULL, summary TEXT NOT NULL, source TEXT NOT NULL, created_at INTEGER NOT NULL, aliases_json TEXT, source_refs TEXT); CREATE INDEX IF NOT EXISTS idx_local_kg_nodes_label ON local_kg_nodes(label); CREATE INDEX IF NOT EXISTS idx_local_kg_nodes_type ON local_kg_nodes(node_type); CREATE TABLE IF NOT EXISTS local_kg_edges (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL, label TEXT NOT NULL, created_at INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS onboarding_kg_nodes (node_id TEXT PRIMARY KEY, label TEXT NOT NULL, node_type TEXT NOT NULL, aliases_json TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS onboarding_kg_edges (edge_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL, label TEXT NOT NULL, created_at INTEGER NOT NULL);").map_err(|error| error.to_string())?;
    for (table, column) in [
        ("local_kg_nodes", "aliases_json"),
        ("local_kg_nodes", "source_refs"),
    ] {
        if !has_column(connection, table, column)? {
            connection
                .execute_batch(&format!("ALTER TABLE {table} ADD COLUMN {column} TEXT"))
                .map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

impl KnowledgeStore {
    pub(crate) fn local_graph_status(&self) -> Result<LocalKnowledgeGraphStatus, String> {
        let connection = self.connection()?;
        Ok(LocalKnowledgeGraphStatus {
            node_count: connection
                .query_row("SELECT COUNT(*) FROM local_kg_nodes", [], |row| row.get(0))
                .map_err(|error| error.to_string())?,
            edge_count: connection
                .query_row("SELECT COUNT(*) FROM local_kg_edges", [], |row| row.get(0))
                .map_err(|error| error.to_string())?,
            last_built_at: connection
                .query_row("SELECT MAX(created_at) FROM local_kg_nodes", [], |row| {
                    row.get(0)
                })
                .map_err(|error| error.to_string())?,
        })
    }
    pub(crate) fn save_local_graph(&self, graph: LocalKnowledgeGraph) -> Result<(), String> {
        let mut connection = self.connection()?;
        let transaction = connection
            .transaction()
            .map_err(|error| error.to_string())?;
        transaction
            .execute("DELETE FROM local_kg_edges", [])
            .map_err(|error| error.to_string())?;
        transaction
            .execute("DELETE FROM local_kg_nodes", [])
            .map_err(|error| error.to_string())?;
        {
            let mut node = transaction.prepare("INSERT INTO local_kg_nodes (id, label, node_type, summary, source, created_at, aliases_json, source_refs) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)").map_err(|error| error.to_string())?;
            for value in &graph.nodes {
                node.execute(params![
                    value.id,
                    value.label,
                    value.node_type,
                    value.summary,
                    value.source,
                    value.created_at,
                    json_array(&value.aliases)?,
                    json_array(&value.source_refs)?
                ])
                .map_err(|error| error.to_string())?;
            }
        }
        {
            let mut edge = transaction.prepare("INSERT INTO local_kg_edges (id, source_id, target_id, label, created_at) VALUES (?1, ?2, ?3, ?4, ?5)").map_err(|error| error.to_string())?;
            for value in &graph.edges {
                edge.execute(params![
                    value.id,
                    value.source_id,
                    value.target_id,
                    value.label,
                    value.created_at
                ])
                .map_err(|error| error.to_string())?;
            }
        }
        transaction.commit().map_err(|error| error.to_string())
    }
    pub(crate) fn query_nodes(
        &self,
        query: &str,
        limit: i64,
    ) -> Result<LocalKnowledgeGraph, String> {
        let connection = self.connection()?;
        let tokens = query
            .split_whitespace()
            .filter(|token| token.len() >= 2)
            .collect::<Vec<_>>();
        let cap = limit.clamp(1, 200);
        let sql = if tokens.is_empty() {
            "SELECT id, label, node_type, summary, source, created_at, aliases_json, source_refs FROM local_kg_nodes ORDER BY created_at DESC LIMIT ?".to_owned()
        } else {
            let condition = std::iter::repeat("(label LIKE ? OR summary LIKE ?)")
                .take(tokens.len())
                .collect::<Vec<_>>()
                .join(" OR ");
            format!("SELECT id, label, node_type, summary, source, created_at, aliases_json, source_refs FROM local_kg_nodes WHERE {condition} ORDER BY created_at DESC LIMIT ?")
        };
        let mut statement = connection
            .prepare(&sql)
            .map_err(|error| error.to_string())?;
        let nodes = if tokens.is_empty() {
            statement
                .query_map([cap], local_node)
                .map_err(|error| error.to_string())?
                .collect::<Result<Vec<_>, _>>()
                .map_err(|error| error.to_string())?
        } else {
            let mut bindings = tokens
                .iter()
                .flat_map(|token| {
                    [
                        rusqlite::types::Value::Text(format!("%{token}%")),
                        rusqlite::types::Value::Text(format!("%{token}%")),
                    ]
                })
                .collect::<Vec<_>>();
            bindings.push(rusqlite::types::Value::Integer(cap));
            statement
                .query_map(params_from_iter(bindings), local_node)
                .map_err(|error| error.to_string())?
                .collect::<Result<Vec<_>, _>>()
                .map_err(|error| error.to_string())?
        };
        let ids = nodes.iter().map(|node| node.id.clone()).collect::<Vec<_>>();
        if ids.is_empty() {
            return Ok(LocalKnowledgeGraph {
                nodes,
                edges: Vec::new(),
            });
        }
        let placeholders = std::iter::repeat("?")
            .take(ids.len())
            .collect::<Vec<_>>()
            .join(",");
        let mut statement = connection.prepare(&format!("SELECT id, source_id, target_id, label, created_at FROM local_kg_edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})")).map_err(|error| error.to_string())?;
        let bindings = ids
            .iter()
            .chain(ids.iter())
            .map(|id| rusqlite::types::Value::Text(id.clone()))
            .collect::<Vec<_>>();
        let edges = statement
            .query_map(params_from_iter(bindings), |row| {
                Ok(LocalKnowledgeGraphEdge {
                    id: row.get(0)?,
                    source_id: row.get(1)?,
                    target_id: row.get(2)?,
                    label: row.get(3)?,
                    created_at: row.get(4)?,
                })
            })
            .map_err(|error| error.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        Ok(LocalKnowledgeGraph { nodes, edges })
    }
    pub(crate) fn load_onboarding_graph(&self) -> Result<KnowledgeGraph, String> {
        let connection = self.connection()?;
        let nodes = connection
            .prepare("SELECT node_id, label, node_type, aliases_json FROM onboarding_kg_nodes")
            .map_err(|error| error.to_string())?
            .query_map([], |row| {
                Ok(KnowledgeGraphNode {
                    id: row.get(0)?,
                    label: row.get(1)?,
                    node_type: row.get(2)?,
                    aliases: parse_array(row.get(3)?),
                    memory_ids: Vec::new(),
                })
            })
            .map_err(|error| error.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        let edges = connection
            .prepare("SELECT edge_id, source_id, target_id, label FROM onboarding_kg_edges")
            .map_err(|error| error.to_string())?
            .query_map([], |row| {
                Ok(KnowledgeGraphEdge {
                    id: row.get(0)?,
                    source_id: row.get(1)?,
                    target_id: row.get(2)?,
                    label: row.get(3)?,
                    memory_ids: Vec::new(),
                })
            })
            .map_err(|error| error.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        Ok(KnowledgeGraph { nodes, edges })
    }
    pub(crate) fn upsert_onboarding_graph(
        &self,
        nodes: &[OnboardingGraphNode],
        edges: &[OnboardingGraphEdge],
    ) -> Result<KnowledgeGraph, String> {
        let mut connection = self.connection()?;
        let transaction = connection
            .transaction()
            .map_err(|error| error.to_string())?;
        let now = now_ms();
        {
            let mut node = transaction.prepare("INSERT INTO onboarding_kg_nodes (node_id, label, node_type, aliases_json, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?5) ON CONFLICT(node_id) DO UPDATE SET label = excluded.label, node_type = excluded.node_type, aliases_json = excluded.aliases_json, updated_at = excluded.updated_at").map_err(|error| error.to_string())?;
            for value in nodes {
                node.execute(params![
                    value.id,
                    value.label,
                    value.node_type,
                    json_array(&value.aliases)?,
                    now
                ])
                .map_err(|error| error.to_string())?;
            }
        }
        {
            let mut edge = transaction.prepare("INSERT INTO onboarding_kg_edges (edge_id, source_id, target_id, label, created_at) VALUES (?1, ?2, ?3, ?4, ?5) ON CONFLICT(edge_id) DO UPDATE SET source_id = excluded.source_id, target_id = excluded.target_id, label = excluded.label").map_err(|error| error.to_string())?;
            for value in edges {
                edge.execute(params![
                    value.id,
                    value.source_id,
                    value.target_id,
                    value.label,
                    now
                ])
                .map_err(|error| error.to_string())?;
            }
        }
        transaction.commit().map_err(|error| error.to_string())?;
        drop(connection);
        self.load_onboarding_graph()
    }
    pub(crate) fn clear_onboarding_graph(&self) -> Result<(), String> {
        self.connection()?
            .execute_batch("DELETE FROM onboarding_kg_edges; DELETE FROM onboarding_kg_nodes;")
            .map_err(|error| error.to_string())
    }
    pub(crate) fn execute_select(&self, sql: &str) -> Result<KgSqlResult, String> {
        let normalized = sql.trim_start().to_ascii_lowercase();
        if !(normalized.starts_with("select") || normalized.starts_with("with"))
            || normalized.contains(';')
        {
            return Err("only a single read-only SELECT statement is allowed".into());
        }
        let connection = self.connection()?;
        let mut statement = connection.prepare(sql).map_err(|error| error.to_string())?;
        if !statement.readonly() {
            return Err("only read-only SELECT statements are allowed".into());
        }
        let columns = statement
            .column_names()
            .into_iter()
            .map(str::to_owned)
            .collect::<Vec<_>>();
        let mut rows = statement.query([]).map_err(|error| error.to_string())?;
        let mut values = Vec::new();
        while let Some(row) = rows.next().map_err(|error| error.to_string())? {
            let mut item = BTreeMap::new();
            for (index, name) in columns.iter().enumerate() {
                item.insert(
                    name.clone(),
                    sqlite_value(row.get_ref(index).map_err(|error| error.to_string())?),
                );
            }
            values.push(item);
        }
        Ok(KgSqlResult {
            columns,
            rows: values,
        })
    }
}

fn has_column(connection: &Connection, table: &str, column: &str) -> Result<bool, String> {
    connection
        .prepare(&format!("PRAGMA table_info({table})"))
        .map_err(|error| error.to_string())?
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|error| error.to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| error.to_string())
        .map(|columns| columns.iter().any(|name| name == column))
}
fn local_node(row: &rusqlite::Row<'_>) -> rusqlite::Result<LocalKnowledgeGraphNode> {
    Ok(LocalKnowledgeGraphNode {
        id: row.get(0)?,
        label: row.get(1)?,
        node_type: row.get(2)?,
        summary: row.get(3)?,
        source: row.get(4)?,
        created_at: row.get(5)?,
        aliases: row
            .get::<_, Option<String>>(6)?
            .map(|value| parse_array(Some(value)))
            .filter(|values| !values.is_empty()),
        source_refs: row
            .get::<_, Option<String>>(7)?
            .map(|value| parse_array(Some(value)))
            .filter(|values| !values.is_empty()),
    })
}
fn parse_array(value: Option<String>) -> Vec<String> {
    value
        .and_then(|value| serde_json::from_str(&value).ok())
        .unwrap_or_default()
}
fn json_array(value: &Option<Vec<String>>) -> Result<Option<String>, String> {
    value
        .as_ref()
        .filter(|value| !value.is_empty())
        .map(serde_json::to_string)
        .transpose()
        .map_err(|error| error.to_string())
}
fn sqlite_value(value: ValueRef<'_>) -> Value {
    match value {
        ValueRef::Null => Value::Null,
        ValueRef::Integer(value) => Value::from(value),
        ValueRef::Real(value) => Value::from(value),
        ValueRef::Text(value) => Value::String(String::from_utf8_lossy(value).into_owned()),
        ValueRef::Blob(value) => Value::String(base64::Engine::encode(
            &base64::engine::general_purpose::STANDARD,
            value,
        )),
    }
}
fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}

#[tauri::command]
pub fn kg_save_graph(
    graph: LocalKnowledgeGraph,
    store: State<'_, KnowledgeStore>,
) -> Result<(), String> {
    store.save_local_graph(graph)
}
#[tauri::command]
pub fn kg_status(store: State<'_, KnowledgeStore>) -> Result<LocalKnowledgeGraphStatus, String> {
    store.local_graph_status()
}
#[tauri::command]
pub fn kg_query_nodes(
    query: String,
    limit: Option<i64>,
    store: State<'_, KnowledgeStore>,
) -> Result<LocalKnowledgeGraph, String> {
    store.query_nodes(&query, limit.unwrap_or(12))
}
#[tauri::command]
pub fn kg_search_files(
    query: String,
    file_type: Option<String>,
    limit: Option<i64>,
    store: State<'_, KnowledgeStore>,
) -> Result<Vec<IndexedFileRecord>, String> {
    store.search_files(&query, file_type.as_deref(), limit.unwrap_or(20))
}
#[tauri::command]
pub fn kg_execute_sql(
    sql: String,
    store: State<'_, KnowledgeStore>,
) -> Result<KgSqlResult, String> {
    store.execute_select(&sql)
}
#[tauri::command]
pub fn local_graph_load(store: State<'_, KnowledgeStore>) -> Result<KnowledgeGraph, String> {
    store.load_onboarding_graph()
}
#[tauri::command]
pub fn local_graph_upsert(
    nodes: Vec<OnboardingGraphNode>,
    edges: Vec<OnboardingGraphEdge>,
    store: State<'_, KnowledgeStore>,
) -> Result<KnowledgeGraph, String> {
    store.upsert_onboarding_graph(&nodes, &edges)
}
#[tauri::command]
pub fn local_graph_clear(store: State<'_, KnowledgeStore>) -> Result<(), String> {
    store.clear_onboarding_graph()
}
