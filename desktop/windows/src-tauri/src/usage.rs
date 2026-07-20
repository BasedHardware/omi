use std::{
    fs,
    path::Path,
    sync::{Mutex, MutexGuard},
};

#[cfg(any(target_os = "windows", test))]
use std::collections::HashMap;

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
#[cfg(target_os = "windows")]
use tauri::Emitter;
#[cfg(target_os = "windows")]
use tauri::Manager;
use tauri::State;

use crate::native;

const DEFAULT_RETENTION_DAYS: i64 = 45;
const MIN_RETENTION_DAYS: i64 = 7;
const MAX_RETENTION_DAYS: i64 = 365;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct AppUsageRecord {
    pub exe_path: String,
    pub exe_name: String,
    pub category: String,
    pub total_seconds: i64,
    pub last_used: i64,
    pub distinct_days: i64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct UsageSettings {
    pub enabled: bool,
    pub retention_days: i64,
}

impl Default for UsageSettings {
    fn default() -> Self {
        Self {
            enabled: true,
            retention_days: DEFAULT_RETENTION_DAYS,
        }
    }
}

pub struct UsageStore {
    connection: Mutex<Connection>,
    settings_file: Mutex<std::path::PathBuf>,
    #[cfg(target_os = "windows")]
    foreground: Mutex<Option<(String, i64)>>,
    #[cfg(target_os = "windows")]
    pending_seconds: Mutex<HashMap<String, i64>>,
}

impl UsageStore {
    pub fn open(database_file: &Path) -> Result<Self, String> {
        let root = native::data_root().map_err(|error| error.to_string())?;
        fs::create_dir_all(&root).map_err(|error| error.to_string())?;
        let connection = Connection::open(database_file).map_err(|error| error.to_string())?;
        Self::initialize(&connection)?;
        Ok(Self {
            connection: Mutex::new(connection),
            settings_file: Mutex::new(root.join("usage-settings.json")),
            #[cfg(target_os = "windows")]
            foreground: Mutex::new(None),
            #[cfg(target_os = "windows")]
            pending_seconds: Mutex::new(HashMap::new()),
        })
    }

    pub fn close(&self) -> Result<(), String> {
        let mut guard = self.connection.lock().map_err(|error| error.to_string())?;
        *guard = Connection::open_in_memory().map_err(|error| error.to_string())?;
        Ok(())
    }

    pub fn reroot(&self, database_file: &Path, root: &Path) -> Result<(), String> {
        fs::create_dir_all(root).map_err(|error| error.to_string())?;
        let connection = Connection::open(database_file).map_err(|error| error.to_string())?;
        Self::initialize(&connection)?;
        {
            let mut guard = self.connection.lock().map_err(|error| error.to_string())?;
            *guard = connection;
        }
        *self
            .settings_file
            .lock()
            .map_err(|error| error.to_string())? = root.join("usage-settings.json");
        Ok(())
    }

    fn initialize(connection: &Connection) -> Result<(), String> {
        connection
            .execute_batch(
                "PRAGMA journal_mode = WAL;
                 CREATE TABLE IF NOT EXISTS app_usage (
                   exe_path TEXT PRIMARY KEY,
                   exe_name TEXT NOT NULL,
                   category TEXT NOT NULL DEFAULT 'other',
                   total_seconds INTEGER NOT NULL DEFAULT 0,
                   last_used INTEGER NOT NULL DEFAULT 0,
                   distinct_days INTEGER NOT NULL DEFAULT 0,
                   first_seen INTEGER NOT NULL DEFAULT 0
                 );",
            )
            .map_err(|error| error.to_string())
    }

    fn connection(&self) -> Result<MutexGuard<'_, Connection>, String> {
        self.connection.lock().map_err(|error| error.to_string())
    }

    fn list(&self) -> Result<Vec<AppUsageRecord>, String> {
        let connection = self.connection()?;
        let mut statement = connection
            .prepare("SELECT exe_path, exe_name, category, total_seconds, last_used, distinct_days FROM app_usage ORDER BY total_seconds DESC")
            .map_err(|error| error.to_string())?;
        let records = statement
            .query_map([], |row| {
                Ok(AppUsageRecord {
                    exe_path: row.get(0)?,
                    exe_name: row.get(1)?,
                    category: row.get(2)?,
                    total_seconds: row.get(3)?,
                    last_used: row.get(4)?,
                    distinct_days: row.get(5)?,
                })
            })
            .map_err(|error| error.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        Ok(records)
    }

    fn settings(&self) -> Result<UsageSettings, String> {
        let settings_file = self
            .settings_file
            .lock()
            .map_err(|error| error.to_string())?;
        match fs::read(&*settings_file) {
            Ok(bytes) => serde_json::from_slice(&bytes)
                .map(sanitize)
                .map_err(|error| format!("invalid usage settings: {error}")),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                Ok(UsageSettings::default())
            }
            Err(error) => Err(format!("could not read usage settings: {error}")),
        }
    }

    fn update_settings(&self, settings: UsageSettings) -> Result<UsageSettings, String> {
        let settings = sanitize(settings);
        let settings_file = self
            .settings_file
            .lock()
            .map_err(|error| error.to_string())?;
        fs::write(
            &*settings_file,
            serde_json::to_vec(&settings).map_err(|error| error.to_string())?,
        )
        .map_err(|error| error.to_string())?;
        let cutoff = now_ms().saturating_sub(settings.retention_days.saturating_mul(86_400_000));
        self.connection()?
            .execute("DELETE FROM app_usage WHERE last_used < ?1", [cutoff])
            .map_err(|error| error.to_string())?;
        #[cfg(target_os = "windows")]
        if !settings.enabled {
            *self.foreground.lock().map_err(|error| error.to_string())? = None;
            self.pending_seconds
                .lock()
                .map_err(|error| error.to_string())?
                .clear();
        }
        Ok(settings)
    }

    #[cfg(target_os = "windows")]
    fn sample_windows(&self) -> Result<(), String> {
        if !self.settings()?.enabled {
            return Ok(());
        }
        let now = now_ms();
        let path = windows_usage::foreground_process_path().unwrap_or_default();
        let previous = self
            .foreground
            .lock()
            .map_err(|error| error.to_string())?
            .replace((path, now));
        if let Some((path, sampled_at)) = previous.filter(|(path, _)| !path.is_empty()) {
            let elapsed = now.saturating_sub(sampled_at);
            if elapsed > 0 && elapsed <= 45_000 {
                *self
                    .pending_seconds
                    .lock()
                    .map_err(|error| error.to_string())?
                    .entry(path)
                    .or_default() += (elapsed + 500) / 1_000;
            }
        }
        Ok(())
    }

    #[cfg(target_os = "windows")]
    fn flush_windows(&self) -> Result<Vec<AppUsageRecord>, String> {
        self.sample_windows()?;
        let pending = std::mem::take(
            &mut *self
                .pending_seconds
                .lock()
                .map_err(|error| error.to_string())?,
        );
        if pending.is_empty() {
            return self.list();
        }
        let now = now_ms();
        let mut connection = self.connection()?;
        let transaction = connection
            .transaction()
            .map_err(|error| error.to_string())?;
        for (path, seconds) in pending {
            if seconds == 0 {
                continue;
            }
            let name = Path::new(&path)
                .file_stem()
                .and_then(|name| name.to_str())
                .unwrap_or("Unknown");
            transaction.execute("INSERT INTO app_usage (exe_path, exe_name, category, total_seconds, last_used, distinct_days, first_seen) VALUES (?1, ?2, 'other', ?3, ?4, 1, ?4) ON CONFLICT(exe_path) DO UPDATE SET total_seconds = total_seconds + excluded.total_seconds, last_used = excluded.last_used", rusqlite::params![path, name, seconds, now]).map_err(|error| error.to_string())?;
        }
        transaction.commit().map_err(|error| error.to_string())?;
        self.list()
    }

    #[cfg(target_os = "windows")]
    fn seed_user_assist_windows(&self) -> Result<(), String> {
        if !self.settings()?.enabled {
            return Ok(());
        }
        let settings_file = self
            .settings_file
            .lock()
            .map_err(|error| error.to_string())?;
        let marker = settings_file.with_file_name("userassist-seeded.json");
        if marker.exists() {
            return Ok(());
        }
        let apps = aggregate_user_assist(windows_usage::read_user_assist_raw()?);
        let now = now_ms();
        let mut seeded = 0;
        let mut connection = self.connection()?;
        let transaction = connection
            .transaction()
            .map_err(|error| error.to_string())?;
        for app in apps.into_iter().filter(|app| app.focus_seconds >= 60) {
            transaction.execute("INSERT OR IGNORE INTO app_usage (exe_path, exe_name, category, total_seconds, last_used, distinct_days, first_seen) VALUES (?1, ?2, 'other', ?3, ?4, 1, ?4)", rusqlite::params![format!("userassist:{}", app.name), app.name, app.focus_seconds, now]).map_err(|error| error.to_string())?;
            seeded += 1;
        }
        transaction.commit().map_err(|error| error.to_string())?;
        fs::write(
            marker,
            serde_json::to_vec(&serde_json::json!({ "at": now, "seeded": seeded }))
                .map_err(|error| error.to_string())?,
        )
        .map_err(|error| error.to_string())
    }
}

#[cfg(target_os = "windows")]
pub fn start_monitor(app: tauri::AppHandle) {
    std::thread::spawn(move || {
        let store = app.state::<UsageStore>();
        if let Err(error) = store.seed_user_assist_windows() {
            report_monitor_error(&app, error);
        }
        loop {
            if let Err(error) = store.sample_windows() {
                report_monitor_error(&app, error);
            }
            std::thread::sleep(std::time::Duration::from_secs(15));
            if let Err(error) = store.flush_windows() {
                report_monitor_error(&app, error);
            }
            std::thread::sleep(std::time::Duration::from_secs(45));
        }
    });
}

#[cfg(target_os = "windows")]
fn report_monitor_error(app: &tauri::AppHandle, error: String) {
    eprintln!("Omi usage monitor failed: {error}");
    if let Err(emit_error) = app.emit("omi://usage-monitor-error", error) {
        eprintln!("Omi usage monitor could not report its failure: {emit_error}");
    }
}

fn sanitize(settings: UsageSettings) -> UsageSettings {
    UsageSettings {
        enabled: settings.enabled,
        retention_days: settings
            .retention_days
            .clamp(MIN_RETENTION_DAYS, MAX_RETENTION_DAYS),
    }
}

fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |duration| {
            duration.as_millis().try_into().unwrap_or(i64::MAX)
        })
}

#[cfg(any(target_os = "windows", test))]
#[derive(Clone, Debug, PartialEq, Eq)]
struct UserAssistApp {
    name: String,
    focus_seconds: i64,
    run_count: u32,
    last_used: i64,
}

#[cfg(any(target_os = "windows", test))]
fn rot13(value: &str) -> String {
    value
        .bytes()
        .map(|byte| match byte {
            b'a'..=b'z' => b'a' + (byte - b'a' + 13) % 26,
            b'A'..=b'Z' => b'A' + (byte - b'A' + 13) % 26,
            _ => byte,
        })
        .map(char::from)
        .collect()
}

#[cfg(any(target_os = "windows", test))]
fn friendly_app_name(value: &str) -> Option<String> {
    let value = value.trim();
    if value.is_empty() || value.starts_with("UEME_") {
        return None;
    }
    let value = value.rsplit(['\\', '/']).next().unwrap_or(value);
    let value = value.split('!').next().unwrap_or(value);
    let value = value.strip_suffix(".exe").unwrap_or(value);
    let value = value.rsplit('.').next().unwrap_or(value);
    let value = value.rsplit('_').nth(1).unwrap_or(value);
    (!value.is_empty()).then(|| value.to_string())
}

#[cfg(any(target_os = "windows", test))]
fn aggregate_user_assist(raw: Vec<(String, Vec<u8>)>) -> Vec<UserAssistApp> {
    let mut apps = HashMap::<String, UserAssistApp>::new();
    for (encoded_name, data) in raw {
        let Some(name) = friendly_app_name(&rot13(&encoded_name)) else {
            continue;
        };
        if data.len() < 16 {
            continue;
        }
        let run_count = u32::from_le_bytes(data[4..8].try_into().expect("fixed slice"));
        let focus_seconds = i64::from(u32::from_le_bytes(
            data[12..16].try_into().expect("fixed slice"),
        )) / 1_000;
        let last_used = if data.len() >= 68 {
            let filetime = u64::from_le_bytes(data[60..68].try_into().expect("fixed slice"));
            if filetime == 0 {
                0
            } else {
                i64::try_from(filetime / 10_000).unwrap_or(i64::MAX) - 11_644_473_600_000
            }
        } else {
            0
        };
        let entry = apps.entry(name.clone()).or_insert(UserAssistApp {
            name,
            focus_seconds: 0,
            run_count: 0,
            last_used: 0,
        });
        entry.focus_seconds += focus_seconds;
        entry.run_count += run_count;
        entry.last_used = entry.last_used.max(last_used);
    }
    let mut apps: Vec<_> = apps.into_values().collect();
    apps.sort_by_key(|app| std::cmp::Reverse(app.focus_seconds));
    apps
}

#[tauri::command]
pub fn usage_list(store: State<'_, UsageStore>) -> Result<Vec<AppUsageRecord>, String> {
    store.list()
}

#[tauri::command]
pub fn app_usage_list(store: State<'_, UsageStore>) -> Result<Vec<AppUsageRecord>, String> {
    store.list()
}

#[tauri::command]
pub fn usage_flush(store: State<'_, UsageStore>) -> Result<Vec<AppUsageRecord>, String> {
    #[cfg(target_os = "windows")]
    {
        store.flush_windows()
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = store;
        Err("Foreground usage tracking is only supported on Windows".into())
    }
}

#[tauri::command]
pub fn usage_get_settings(store: State<'_, UsageStore>) -> Result<UsageSettings, String> {
    store.settings()
}

#[tauri::command]
pub fn usage_set_settings(
    settings: UsageSettings,
    store: State<'_, UsageStore>,
) -> Result<UsageSettings, String> {
    store.update_settings(settings)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamps_usage_settings() {
        let settings = sanitize(UsageSettings {
            enabled: false,
            retention_days: 1,
        });
        assert_eq!(settings.retention_days, MIN_RETENTION_DAYS);
    }

    #[test]
    fn reads_existing_usage_rows() {
        let connection = Connection::open_in_memory().unwrap();
        UsageStore::initialize(&connection).unwrap();
        connection
            .execute(
                "INSERT INTO app_usage (exe_path, exe_name, total_seconds) VALUES ('/app', 'App', 42)",
                [],
            )
            .unwrap();
        let store = UsageStore {
            connection: Mutex::new(connection),
            settings_file: Mutex::new(std::path::PathBuf::new()),
            #[cfg(target_os = "windows")]
            foreground: Mutex::new(None),
            #[cfg(target_os = "windows")]
            pending_seconds: Mutex::new(HashMap::new()),
        };

        assert_eq!(store.list().unwrap()[0].total_seconds, 42);
    }

    #[test]
    fn rejects_corrupt_persisted_settings() {
        let root = std::env::temp_dir().join(format!("omi-usage-{}", now_ms()));
        fs::create_dir_all(&root).unwrap();
        let store = UsageStore {
            connection: Mutex::new(Connection::open_in_memory().unwrap()),
            settings_file: Mutex::new(root.join("usage-settings.json")),
            #[cfg(target_os = "windows")]
            foreground: Mutex::new(None),
            #[cfg(target_os = "windows")]
            pending_seconds: Mutex::new(HashMap::new()),
        };
        fs::write(&*store.settings_file.lock().unwrap(), b"not json").unwrap();

        assert!(store
            .settings()
            .unwrap_err()
            .contains("invalid usage settings"));
    }

    #[test]
    fn aggregates_rot13_user_assist_records() {
        let mut data = vec![0; 68];
        data[4..8].copy_from_slice(&3_u32.to_le_bytes());
        data[12..16].copy_from_slice(&90_000_u32.to_le_bytes());
        let apps = aggregate_user_assist(vec![(rot13(r"C:\\Apps\\Chrome.exe"), data)]);
        assert_eq!(
            apps,
            vec![UserAssistApp {
                name: "Chrome".into(),
                focus_seconds: 90,
                run_count: 3,
                last_used: 0
            }]
        );
    }
}

#[cfg(target_os = "windows")]
mod windows_usage {
    use std::path::PathBuf;

    #[link(name = "user32")]
    extern "system" {
        fn GetForegroundWindow() -> isize;
        fn GetWindowThreadProcessId(window: isize, process_id: *mut u32) -> u32;
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn OpenProcess(access: u32, inherit: i32, process_id: u32) -> isize;
        fn QueryFullProcessImageNameW(
            process: isize,
            flags: u32,
            path: *mut u16,
            length: *mut u32,
        ) -> i32;
        fn CloseHandle(handle: isize) -> i32;
    }
    #[link(name = "advapi32")]
    extern "system" {
        fn RegOpenKeyExW(
            key: isize,
            sub_key: *const u16,
            options: u32,
            access: u32,
            result: *mut isize,
        ) -> i32;
        fn RegEnumValueW(
            key: isize,
            index: u32,
            name: *mut u16,
            name_length: *mut u32,
            reserved: *mut u32,
            value_type: *mut u32,
            data: *mut u8,
            data_length: *mut u32,
        ) -> i32;
        fn RegCloseKey(key: isize) -> i32;
    }

    pub fn read_user_assist_raw() -> Result<Vec<(String, Vec<u8>)>, String> {
        let path: Vec<u16> = "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\UserAssist\\{CEBFF5CD-ACE2-4F4F-9178-9926F41749EA}\\Count\0".encode_utf16().collect();
        // SAFETY: the registry functions use the documented Windows system ABI; all pointer arguments reference live local storage with their lengths supplied, and the opened registry handle is closed before returning.
        unsafe {
            let mut key = 0;
            if RegOpenKeyExW(
                0x8000_0001_u32 as isize,
                path.as_ptr(),
                0,
                0x20_019,
                &mut key,
            ) != 0
            {
                return Err("could not open the current user's UserAssist registry key".into());
            }
            let mut records = Vec::new();
            for index in 0.. {
                let mut name = vec![0_u16; 32_768];
                let mut name_length = name.len() as u32;
                let mut data = vec![0_u8; 8_192];
                let mut data_length = data.len() as u32;
                let status = RegEnumValueW(
                    key,
                    index,
                    name.as_mut_ptr(),
                    &mut name_length,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    data.as_mut_ptr(),
                    &mut data_length,
                );
                match status {
                    0 => {
                        name.truncate(name_length as usize);
                        data.truncate(data_length as usize);
                        records.push((String::from_utf16_lossy(&name), data));
                    }
                    259 => break,
                    status => {
                        RegCloseKey(key);
                        return Err(format!(
                            "could not enumerate UserAssist registry values ({status})"
                        ));
                    }
                }
            }
            RegCloseKey(key);
            Ok(records)
        }
    }

    pub fn foreground_process_path() -> Option<String> {
        // SAFETY: these declarations use the documented Windows system ABI; the output pointers reference initialized local buffers for the stated lengths, and every successful OpenProcess handle is closed before returning.
        unsafe {
            let window = GetForegroundWindow();
            if window == 0 {
                return None;
            }
            let mut process_id = 0;
            GetWindowThreadProcessId(window, &mut process_id);
            if process_id == 0 {
                return None;
            }
            let process = OpenProcess(0x1000, 0, process_id);
            if process == 0 {
                return None;
            }
            let mut path = [0u16; 32_768];
            let mut length = path.len() as u32;
            let ok = QueryFullProcessImageNameW(process, 0, path.as_mut_ptr(), &mut length);
            CloseHandle(process);
            (ok != 0).then(|| {
                PathBuf::from(String::from_utf16_lossy(&path[..length as usize]))
                    .to_string_lossy()
                    .into_owned()
            })
        }
    }
}
