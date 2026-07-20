use std::{
    fs,
    path::Path,
    sync::{Mutex, MutexGuard},
};

use rusqlite::Connection;

pub(crate) mod file_index;
pub(crate) mod graph;

pub use file_index::FileIndexRuntime;

pub struct KnowledgeStore {
    connection: Mutex<Connection>,
    file_index: Mutex<FileIndexRuntime>,
}

impl KnowledgeStore {
    pub fn open(path: &Path) -> Result<Self, String> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        let connection = Connection::open(path).map_err(|error| error.to_string())?;
        Self::initialize(&connection)?;
        Ok(Self {
            connection: Mutex::new(connection),
            file_index: Mutex::new(FileIndexRuntime::default()),
        })
    }

    pub fn close(&self) -> Result<(), String> {
        let mut guard = self.connection.lock().map_err(|error| error.to_string())?;
        *guard = Connection::open_in_memory().map_err(|error| error.to_string())?;
        Ok(())
    }

    pub fn reroot(&self, database_file: &Path) -> Result<(), String> {
        if let Some(parent) = database_file.parent() {
            fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        let connection = Connection::open(database_file).map_err(|error| error.to_string())?;
        Self::initialize(&connection)?;
        let mut guard = self.connection.lock().map_err(|error| error.to_string())?;
        *guard = connection;
        Ok(())
    }

    fn initialize(connection: &Connection) -> Result<(), String> {
        connection
            .execute_batch("PRAGMA journal_mode = WAL;")
            .map_err(|error| error.to_string())?;
        file_index::initialize(connection)?;
        graph::initialize(connection)
    }

    pub(crate) fn connection(&self) -> Result<MutexGuard<'_, Connection>, String> {
        self.connection.lock().map_err(|error| error.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store() -> KnowledgeStore {
        let connection = Connection::open_in_memory().unwrap();
        KnowledgeStore::initialize(&connection).unwrap();
        KnowledgeStore {
            connection: Mutex::new(connection),
            file_index: Mutex::new(FileIndexRuntime::default()),
        }
    }

    #[test]
    fn preserves_file_and_graph_records_in_the_electron_schema() {
        let store = store();
        store
            .save_local_graph(graph::LocalKnowledgeGraph {
                nodes: vec![graph::LocalKnowledgeGraphNode {
                    id: "rust:technology".into(),
                    label: "Rust".into(),
                    node_type: "technology".into(),
                    summary: "Uses Rust".into(),
                    source: "files".into(),
                    created_at: 7,
                    aliases: Some(vec!["rs".into()]),
                    source_refs: None,
                }],
                edges: vec![],
            })
            .unwrap();
        assert_eq!(
            store.query_nodes("Rust", 12).unwrap().nodes[0]
                .aliases
                .as_deref(),
            Some(["rs".to_owned()].as_slice())
        );
        store
            .upsert_onboarding_graph(
                &[graph::OnboardingGraphNode {
                    id: "you".into(),
                    label: "Omi".into(),
                    node_type: "person".into(),
                    aliases: None,
                }],
                &[],
            )
            .unwrap();
        assert_eq!(store.load_onboarding_graph().unwrap().nodes[0].label, "Omi");
    }

    #[test]
    fn limits_queries_and_rejects_writes() {
        let store = store();
        assert!(store
            .execute_select("CREATE TABLE nope (id INTEGER)")
            .is_err());
        assert!(store
            .execute_select("PRAGMA table_info(indexed_files)")
            .is_err());
        assert!(store.execute_select("SELECT 1 AS value").is_ok());
        assert!(store.search_files("x", None, 0).is_ok());
    }
}
