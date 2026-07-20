use std::{
    path::Path,
    sync::{Mutex, MutexGuard},
};

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};

const CONVERSATIONS_CHANGED: &str = "omi://conversations-changed";

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct LocalConversation {
    pub id: String,
    pub started_at: i64,
    pub ended_at: i64,
    pub transcript: String,
    pub created_at: i64,
    #[serde(default)]
    pub kind: ConversationKind,
    pub messages: Option<Vec<ChatMessage>>,
    pub title: Option<String>,
}

#[derive(Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ConversationKind {
    #[default]
    Recording,
    Chat,
}

impl ConversationKind {
    const fn as_str(&self) -> &'static str {
        match self {
            Self::Recording => "recording",
            Self::Chat => "chat",
        }
    }

    fn from_str(value: &str) -> Self {
        if value == "chat" {
            Self::Chat
        } else {
            Self::Recording
        }
    }
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
pub struct ChatMessage {
    pub id: Option<String>,
    pub role: ChatRole,
    pub content: String,
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ChatRole {
    User,
    Assistant,
}

pub struct ConversationStore(Mutex<Connection>);

impl ConversationStore {
    pub fn open(path: &Path) -> Result<Self, String> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        let connection = Connection::open(path).map_err(|error| error.to_string())?;
        Self::initialize(&connection)?;
        Ok(Self(Mutex::new(connection)))
    }

    fn initialize(connection: &Connection) -> Result<(), String> {
        connection
            .execute_batch(
                "PRAGMA journal_mode = WAL;
                 CREATE TABLE IF NOT EXISTS local_conversation (
                   id TEXT PRIMARY KEY,
                   started_at INTEGER NOT NULL,
                   ended_at INTEGER NOT NULL,
                   transcript TEXT NOT NULL,
                   created_at INTEGER NOT NULL,
                   kind TEXT NOT NULL DEFAULT 'recording',
                   messages TEXT,
                   title TEXT
                 );",
            )
            .map_err(|error| error.to_string())?;
        for (column, declaration) in [
            ("kind", "TEXT NOT NULL DEFAULT 'recording'"),
            ("messages", "TEXT"),
            ("title", "TEXT"),
        ] {
            let exists = connection
                .prepare("PRAGMA table_info(local_conversation)")
                .and_then(|mut statement| {
                    statement
                        .query_map([], |row| row.get::<_, String>(1))?
                        .collect::<Result<Vec<_>, _>>()
                })
                .map_err(|error| error.to_string())?
                .iter()
                .any(|name| name == column);
            if !exists {
                connection
                    .execute_batch(&format!(
                        "ALTER TABLE local_conversation ADD COLUMN {column} {declaration}"
                    ))
                    .map_err(|error| error.to_string())?;
            }
        }
        Ok(())
    }

    fn connection(&self) -> Result<MutexGuard<'_, Connection>, String> {
        self.0.lock().map_err(|error| error.to_string())
    }

    fn get(&self, id: &str) -> Result<Option<LocalConversation>, String> {
        let connection = self.connection()?;
        connection
            .query_row(
                "SELECT id, started_at, ended_at, transcript, created_at, kind, messages, title FROM local_conversation WHERE id = ?1",
                [id],
                Self::row,
            )
            .optional()
            .map_err(|error| error.to_string())
    }

    fn list(&self) -> Result<Vec<LocalConversation>, String> {
        let connection = self.connection()?;
        let mut statement = connection
            .prepare("SELECT id, started_at, ended_at, transcript, created_at, kind, messages, title FROM local_conversation ORDER BY created_at DESC")
            .map_err(|error| error.to_string())?;
        let conversations = statement
            .query_map([], Self::row)
            .map_err(|error| error.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string());
        conversations
    }

    fn upsert(&self, conversation: &LocalConversation) -> Result<(), String> {
        let messages = conversation
            .messages
            .as_ref()
            .map(serde_json::to_string)
            .transpose()
            .map_err(|error| error.to_string())?;
        self.connection()?
            .execute(
                "INSERT OR REPLACE INTO local_conversation (id, started_at, ended_at, transcript, created_at, kind, messages, title) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
                params![&conversation.id, conversation.started_at, conversation.ended_at, &conversation.transcript, conversation.created_at, conversation.kind.as_str(), messages, conversation.title.as_deref()],
            )
            .map(|_| ())
            .map_err(|error| error.to_string())
    }

    fn delete(&self, id: &str) -> Result<(), String> {
        self.connection()?
            .execute("DELETE FROM local_conversation WHERE id = ?1", [id])
            .map(|_| ())
            .map_err(|error| error.to_string())
    }

    fn update_title(&self, id: &str, title: String) -> Result<(), String> {
        let title = title.trim();
        self.connection()?
            .execute(
                "UPDATE local_conversation SET title = ?1 WHERE id = ?2",
                params![(!title.is_empty()).then_some(title), id],
            )
            .map(|_| ())
            .map_err(|error| error.to_string())
    }

    fn row(row: &rusqlite::Row<'_>) -> rusqlite::Result<LocalConversation> {
        let messages: Option<String> = row.get(6)?;
        Ok(LocalConversation {
            id: row.get(0)?,
            started_at: row.get(1)?,
            ended_at: row.get(2)?,
            transcript: row.get(3)?,
            created_at: row.get(4)?,
            kind: ConversationKind::from_str(&row.get::<_, String>(5)?),
            messages: messages
                .map(|value| {
                    serde_json::from_str(&value)
                        .map_err(|error| rusqlite::Error::ToSqlConversionFailure(Box::new(error)))
                })
                .transpose()?,
            title: row.get(7)?,
        })
    }
}

fn changed(app: &AppHandle) -> Result<(), String> {
    app.emit(CONVERSATIONS_CHANGED, ())
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn local_conversation_get(
    id: String,
    store: State<'_, ConversationStore>,
) -> Result<Option<LocalConversation>, String> {
    store.get(&id)
}

#[tauri::command]
pub fn local_conversation_list(
    store: State<'_, ConversationStore>,
) -> Result<Vec<LocalConversation>, String> {
    store.list()
}

#[tauri::command]
pub fn local_conversation_upsert(
    app: AppHandle,
    conversation: LocalConversation,
    store: State<'_, ConversationStore>,
) -> Result<(), String> {
    store.upsert(&conversation)?;
    changed(&app)
}

#[tauri::command]
pub fn local_conversation_delete(
    app: AppHandle,
    id: String,
    store: State<'_, ConversationStore>,
) -> Result<(), String> {
    store.delete(&id)?;
    changed(&app)
}

#[tauri::command]
pub fn local_conversation_update_title(
    app: AppHandle,
    id: String,
    title: String,
    store: State<'_, ConversationStore>,
) -> Result<(), String> {
    store.update_title(&id, title)?;
    changed(&app)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store() -> ConversationStore {
        let connection = Connection::open_in_memory().unwrap();
        ConversationStore::initialize(&connection).unwrap();
        ConversationStore(Mutex::new(connection))
    }

    fn conversation() -> LocalConversation {
        LocalConversation {
            id: "chat-1".into(),
            started_at: 1,
            ended_at: 2,
            transcript: "You: hello".into(),
            created_at: 1,
            kind: ConversationKind::Chat,
            messages: Some(vec![ChatMessage {
                id: Some("message-1".into()),
                role: ChatRole::User,
                content: "hello".into(),
            }]),
            title: None,
        }
    }

    #[test]
    fn preserves_local_conversation_records() {
        let store = store();
        let conversation = conversation();
        store.upsert(&conversation).unwrap();
        assert_eq!(store.get("chat-1").unwrap(), Some(conversation));
        store.update_title("chat-1", "  named  ".into()).unwrap();
        assert_eq!(store.list().unwrap()[0].title.as_deref(), Some("named"));
        store.delete("chat-1").unwrap();
        assert_eq!(store.get("chat-1").unwrap(), None);
    }

    #[test]
    fn migrates_the_electron_conversation_schema_without_losing_rows() {
        let connection = Connection::open_in_memory().unwrap();
        connection
            .execute_batch(
                "CREATE TABLE local_conversation (
                   id TEXT PRIMARY KEY,
                   started_at INTEGER NOT NULL,
                   ended_at INTEGER NOT NULL,
                   transcript TEXT NOT NULL,
                   created_at INTEGER NOT NULL
                 );
                 INSERT INTO local_conversation VALUES ('local-1', 1, 2, 'saved', 1);",
            )
            .unwrap();
        ConversationStore::initialize(&connection).unwrap();
        let store = ConversationStore(Mutex::new(connection));
        assert_eq!(store.get("local-1").unwrap().unwrap().transcript, "saved");
        assert_eq!(
            store.get("local-1").unwrap().unwrap().kind,
            ConversationKind::Recording
        );
    }
}
