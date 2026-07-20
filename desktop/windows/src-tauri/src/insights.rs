use std::{
    fs,
    path::Path,
    sync::{Mutex, MutexGuard},
};

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_notification::NotificationExt;

use crate::native;

const SHOWN: &str = "omi://insight-show";
const TOAST_LABEL: &str = "insight-toast";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InsightPayload {
    pub headline: String,
    pub advice: String,
    pub reasoning: String,
    pub category: String,
    pub source_app: String,
    pub confidence: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InsightSettings {
    pub enabled: bool,
    pub interval_min: i64,
    pub notification_style: String,
    pub denylist: Vec<String>,
    pub last_run_at: Option<i64>,
}

impl Default for InsightSettings {
    fn default() -> Self {
        Self {
            enabled: true,
            interval_min: 15,
            notification_style: "omi".into(),
            denylist: Vec::new(),
            last_run_at: None,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InsightRecord {
    pub id: i64,
    pub ts: i64,
    #[serde(flatten)]
    pub payload: InsightPayload,
    pub dismissed: i64,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct InsightSettingsPatch {
    pub enabled: Option<bool>,
    pub interval_min: Option<i64>,
    pub notification_style: Option<String>,
    pub denylist: Option<Vec<String>>,
    pub last_run_at: Option<Option<i64>>,
}

pub struct InsightStore {
    connection: Mutex<Connection>,
    settings_file: std::path::PathBuf,
    settings: Mutex<InsightSettings>,
}

impl InsightStore {
    pub fn open(database_file: &Path) -> Result<Self, String> {
        let root = native::data_root().map_err(|error| error.to_string())?;
        Self::open_at(database_file, &root)
    }

    fn open_at(database_file: &Path, root: &Path) -> Result<Self, String> {
        fs::create_dir_all(root).map_err(|error| error.to_string())?;
        let connection = Connection::open(database_file).map_err(|error| error.to_string())?;
        connection
            .execute_batch(
                "CREATE TABLE IF NOT EXISTS insights (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               ts INTEGER NOT NULL,
               headline TEXT NOT NULL,
               advice TEXT NOT NULL,
               reasoning TEXT NOT NULL DEFAULT '',
               category TEXT NOT NULL DEFAULT 'other',
               source_app TEXT NOT NULL DEFAULT '',
               confidence REAL NOT NULL DEFAULT 0,
               dismissed INTEGER NOT NULL DEFAULT 0
             );
             CREATE INDEX IF NOT EXISTS idx_insights_ts ON insights(ts);",
            )
            .map_err(|error| error.to_string())?;
        let settings_file = root.join("insights.json");
        let settings = fs::read(&settings_file)
            .ok()
            .and_then(|contents| serde_json::from_slice(&contents).ok())
            .unwrap_or_default();
        Ok(Self {
            connection: Mutex::new(connection),
            settings_file,
            settings: Mutex::new(settings),
        })
    }

    fn connection(&self) -> Result<MutexGuard<'_, Connection>, String> {
        self.connection.lock().map_err(|error| error.to_string())
    }

    fn settings(&self) -> Result<MutexGuard<'_, InsightSettings>, String> {
        self.settings.lock().map_err(|error| error.to_string())
    }

    fn save_settings(&self, settings: &InsightSettings) -> Result<(), String> {
        fs::write(
            &self.settings_file,
            serde_json::to_vec_pretty(settings).map_err(|error| error.to_string())?,
        )
        .map_err(|error| error.to_string())
    }
}

fn toast_window(app: &AppHandle) -> Result<tauri::WebviewWindow, String> {
    if let Some(window) = app.get_webview_window(TOAST_LABEL) {
        return Ok(window);
    }
    WebviewWindowBuilder::new(
        app,
        TOAST_LABEL,
        WebviewUrl::App("index.html#/insight-toast".into()),
    )
    .title("Omi")
    .inner_size(360.0, 168.0)
    .resizable(false)
    .decorations(false)
    .always_on_top(true)
    .skip_taskbar(true)
    .visible(false)
    .build()
    .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn insight_get_settings(store: State<'_, InsightStore>) -> Result<InsightSettings, String> {
    Ok(store.settings()?.clone())
}

#[tauri::command]
pub fn insight_set_settings(
    store: State<'_, InsightStore>,
    patch: InsightSettingsPatch,
) -> Result<InsightSettings, String> {
    let mut settings = store.settings()?;
    if let Some(value) = patch.enabled {
        settings.enabled = value;
    }
    if let Some(value) = patch.interval_min {
        settings.interval_min = value;
    }
    if let Some(value) = patch.notification_style {
        settings.notification_style = value;
    }
    if let Some(value) = patch.denylist {
        settings.denylist = value;
    }
    if let Some(value) = patch.last_run_at {
        settings.last_run_at = value;
    }
    store.save_settings(&settings)?;
    Ok(settings.clone())
}

#[tauri::command]
pub fn insight_add(store: State<'_, InsightStore>, payload: InsightPayload) -> Result<i64, String> {
    let connection = store.connection()?;
    connection.execute(
        "INSERT INTO insights (ts, headline, advice, reasoning, category, source_app, confidence) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        params![time::OffsetDateTime::now_utc().unix_timestamp() * 1_000, payload.headline, payload.advice, payload.reasoning, payload.category, payload.source_app, payload.confidence],
    ).map_err(|error| error.to_string())?;
    Ok(connection.last_insert_rowid())
}

#[tauri::command]
pub fn insight_recent(
    store: State<'_, InsightStore>,
    limit: usize,
) -> Result<Vec<InsightRecord>, String> {
    let connection = store.connection()?;
    let mut statement = connection.prepare("SELECT id, ts, headline, advice, reasoning, category, source_app, confidence, dismissed FROM insights ORDER BY ts DESC LIMIT ?1").map_err(|error| error.to_string())?;
    let records = statement
        .query_map([limit], |row| {
            Ok(InsightRecord {
                id: row.get(0)?,
                ts: row.get(1)?,
                payload: InsightPayload {
                    headline: row.get(2)?,
                    advice: row.get(3)?,
                    reasoning: row.get(4)?,
                    category: row.get(5)?,
                    source_app: row.get(6)?,
                    confidence: row.get(7)?,
                },
                dismissed: row.get(8)?,
            })
        })
        .map_err(|error| error.to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| error.to_string())?;
    Ok(records)
}

#[tauri::command]
pub fn insight_show(
    app: AppHandle,
    store: State<'_, InsightStore>,
    payload: InsightPayload,
) -> Result<(), String> {
    if store.settings()?.notification_style == "native" {
        app.notification()
            .builder()
            .title(&payload.headline)
            .body(&payload.advice)
            .show()
            .map_err(|error| error.to_string())
    } else {
        let window = toast_window(&app)?;
        window.show().map_err(|error| error.to_string())?;
        window
            .emit(SHOWN, payload)
            .map_err(|error| error.to_string())
    }
}

#[tauri::command]
pub fn insight_dismiss(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(TOAST_LABEL) {
        window.hide().map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn insight_test(app: AppHandle, store: State<'_, InsightStore>) -> Result<(), String> {
    insight_show(
        app,
        store,
        InsightPayload {
            headline: "Test notification".into(),
            advice: "If you can see this, Omi notifications are working.".into(),
            reasoning: "Triggered from Settings.".into(),
            category: "other".into(),
            source_app: "Omi".into(),
            confidence: 1.0,
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn persists_settings_and_dedupe_records() {
        let directory =
            std::env::temp_dir().join(format!("omi-insights-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        let database = directory.join("omi.db");
        let store = InsightStore::open_at(&database, &directory).unwrap();
        store.connection().unwrap().execute("INSERT INTO insights (ts, headline, advice, reasoning, category, source_app, confidence) VALUES (1, 'Focus', 'Stop', '', 'productivity', 'Omi', 1)", []).unwrap();
        assert_eq!(
            store
                .connection()
                .unwrap()
                .query_row("SELECT COUNT(*) FROM insights", [], |row| row
                    .get::<_, i64>(0))
                .unwrap(),
            1
        );
        fs::remove_dir_all(directory).unwrap();
    }
}
