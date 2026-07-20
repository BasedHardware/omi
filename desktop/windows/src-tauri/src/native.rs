use std::{
    ffi::OsStr,
    path::{Path, PathBuf},
    sync::{Mutex, OnceLock},
};

use serde::Serialize;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[cfg_attr(not(test), allow(dead_code))]
enum Platform {
    Linux,
    Macos,
    Windows,
}

impl Platform {
    const fn current() -> Self {
        #[cfg(target_os = "windows")]
        {
            Self::Windows
        }
        #[cfg(target_os = "macos")]
        {
            Self::Macos
        }
        #[cfg(target_os = "linux")]
        {
            Self::Linux
        }
    }

    const fn name(self) -> &'static str {
        match self {
            Self::Linux => "linux",
            Self::Macos => "macos",
            Self::Windows => "windows",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum NativeError {
    DataRootUnavailable { platform: &'static str },
    DataRootOverrideNotAbsolute,
    MigrationFailed,
}

impl std::fmt::Display for NativeError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::DataRootUnavailable { platform } => {
                write!(formatter, "Omi data root is unavailable on {platform}")
            }
            Self::DataRootOverrideNotAbsolute => {
                write!(formatter, "OMI_DATA_ROOT must be an absolute path")
            }
            Self::MigrationFailed => write!(formatter, "Omi data migration failed"),
        }
    }
}

impl std::error::Error for NativeError {}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DatabasePath {
    pub path: String,
}

static USER_ID: OnceLock<Mutex<Option<String>>> = OnceLock::new();

fn user_id_lock() -> &'static Mutex<Option<String>> {
    USER_ID.get_or_init(|| Mutex::new(None))
}

fn trim_env(key: &str) -> Option<String> {
    std::env::var(key)
        .ok()
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

/// Configure the current Firebase user ID. This drives the per-user macOS data
/// root and is used by `data_root()` when `OMI_DATA_ROOT` is not set.
pub fn set_user_id(user_id: String) {
    let user_id = user_id.trim().to_owned();
    if user_id.is_empty() {
        return;
    }
    if let Ok(mut guard) = user_id_lock().lock() {
        *guard = Some(user_id);
    }
}

pub fn current_user_id() -> Option<String> {
    user_id_lock().lock().ok().and_then(|guard| guard.clone())
}

/// Seed the current user ID from the launch environment so local harnesses and
/// dev profiles resolve the right per-user storage before the first command.
pub fn initialize_user_id() {
    if current_user_id().is_some() {
        return;
    }
    if let Some(user_id) = trim_env("OMI_USER_ID").or_else(|| trim_env("OMI_LOCAL_AUTH_USER")) {
        set_user_id(user_id);
    }
}

fn anonymous_user_id() -> String {
    "anonymous".to_owned()
}

fn effective_user_id() -> String {
    current_user_id()
        .or_else(|| trim_env("OMI_USER_ID"))
        .or_else(|| trim_env("OMI_LOCAL_AUTH_USER"))
        .unwrap_or_else(anonymous_user_id)
}

fn is_named_development_bundle(bundle_id: &str) -> bool {
    const PREFIX: &str = "com.omi.omi-";
    if !bundle_id.starts_with(PREFIX) {
        return false;
    }
    let suffix = &bundle_id[PREFIX.len()..];
    if suffix.is_empty() {
        return false;
    }
    suffix
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || ch == '-' || ch == '.')
}

fn macos_application_support_components() -> Vec<String> {
    if trim_env("OMI_DESKTOP_LOCAL_PROFILE").as_deref() == Some("1") {
        if let Some(name) = trim_env("OMI_LOCAL_PROFILE_STORAGE_NAME") {
            return vec![name];
        }
    }
    if let Some(bundle_id) = trim_env("OMI_BUNDLE_ID") {
        if is_named_development_bundle(&bundle_id) {
            return vec!["Omi Dev Bundles".to_owned(), bundle_id];
        }
    }
    vec!["Omi".to_owned()]
}

fn data_root_for(
    platform: Platform,
    home: Option<&Path>,
    app_data: Option<&Path>,
    xdg_data_home: Option<&Path>,
) -> Result<PathBuf, NativeError> {
    match platform {
        Platform::Windows => {
            app_data
                .map(|path| path.join("omi-windows"))
                .ok_or(NativeError::DataRootUnavailable {
                    platform: platform.name(),
                })
        }
        Platform::Macos => {
            let mut base = home
                .map(|path| path.join("Library/Application Support"))
                .ok_or(NativeError::DataRootUnavailable {
                    platform: platform.name(),
                })?;
            for component in macos_application_support_components() {
                base = base.join(component);
            }
            Ok(base)
        }
        Platform::Linux => xdg_data_home
            .filter(|path| path.is_absolute())
            .map(|path| path.join("Omi"))
            .or_else(|| home.map(|path| path.join(".local/share/Omi")))
            .ok_or(NativeError::DataRootUnavailable {
                platform: platform.name(),
            }),
    }
}

#[cfg(test)]
fn data_root_with_override_for(
    override_path: Option<&OsStr>,
    platform: Platform,
    home: Option<&Path>,
    app_data: Option<&Path>,
    xdg_data_home: Option<&Path>,
) -> Result<PathBuf, NativeError> {
    if let Some(path) = override_path {
        let path = PathBuf::from(path);
        return path
            .is_absolute()
            .then_some(path)
            .ok_or(NativeError::DataRootOverrideNotAbsolute);
    }
    data_root_for(platform, home, app_data, xdg_data_home)
}

pub(crate) fn data_root() -> Result<PathBuf, NativeError> {
    if let Some(path) = std::env::var_os("OMI_DATA_ROOT") {
        let path = PathBuf::from(path);
        return path
            .is_absolute()
            .then_some(path)
            .ok_or(NativeError::DataRootOverrideNotAbsolute);
    }

    let home = std::env::var_os("HOME").map(PathBuf::from);
    let app_data = std::env::var_os("APPDATA").map(PathBuf::from);
    let xdg_data_home = std::env::var_os("XDG_DATA_HOME").map(PathBuf::from);

    let mut root = data_root_for(
        Platform::current(),
        home.as_deref(),
        app_data.as_deref(),
        xdg_data_home.as_deref(),
    )?;

    if Platform::current() == Platform::Macos {
        root = root.join("users").join(effective_user_id());
    }

    Ok(root)
}

pub fn database_file() -> Result<PathBuf, NativeError> {
    database_file_for(std::env::var_os("OMI_DB_PATH").as_deref())
}

fn database_file_for(override_path: Option<&OsStr>) -> Result<PathBuf, NativeError> {
    match override_path {
        Some(path) => Ok(PathBuf::from(path)),
        None => Ok(data_root()?.join("omi.db")),
    }
}

#[tauri::command]
pub fn database_path() -> Result<DatabasePath, NativeError> {
    let path = database_file()?;
    Ok(DatabasePath {
        path: path.to_string_lossy().into_owned(),
    })
}

fn platform_root() -> Result<PathBuf, NativeError> {
    let home = std::env::var_os("HOME").map(PathBuf::from);
    let app_data = std::env::var_os("APPDATA").map(PathBuf::from);
    let xdg_data_home = std::env::var_os("XDG_DATA_HOME").map(PathBuf::from);
    data_root_for(
        Platform::current(),
        home.as_deref(),
        app_data.as_deref(),
        xdg_data_home.as_deref(),
    )
}

fn directory_is_empty(path: &Path) -> bool {
    std::fs::read_dir(path)
        .map(|mut entries| entries.next().is_none())
        .unwrap_or(true)
}

/// Migrate data from the legacy shared path or the anonymous fallback into the
/// per-user `data_root()`. This mirrors `RewindDatabase.migrateFromLegacyPathIfNeeded`.
pub fn migrate_to_current_user() -> Result<(), NativeError> {
    let user_id = effective_user_id();
    if user_id == "anonymous" {
        return Ok(());
    }

    let user_dir = data_root()?;
    if user_dir.exists() && !directory_is_empty(&user_dir) {
        // Already has per-user state; don't overwrite it from legacy sources.
        return Ok(());
    }

    let platform_root = platform_root()?;
    let anonymous_dir = platform_root.join("users").join("anonymous");

    let source = if platform_root.join("omi.db").is_file() {
        platform_root.clone()
    } else if anonymous_dir.exists()
        && anonymous_dir != user_dir
        && !directory_is_empty(&anonymous_dir)
    {
        anonymous_dir
    } else {
        return Ok(());
    };

    if source == user_dir {
        return Ok(());
    }

    std::fs::create_dir_all(&user_dir).map_err(|_| NativeError::MigrationFailed)?;

    // WAL/SHM and the running flag are path-bound and must not be migrated.
    const STALE_FILES: &[&str] = &["omi.db-wal", "omi.db-shm", ".omi_running"];
    for name in STALE_FILES {
        let path = user_dir.join(name);
        if path.exists() {
            let _ = std::fs::remove_file(&path);
        }
    }

    let entries = std::fs::read_dir(&source).map_err(|_| NativeError::MigrationFailed)?;
    for entry in entries {
        let entry = entry.map_err(|_| NativeError::MigrationFailed)?;
        let name = entry.file_name();
        let name_str = name.to_string_lossy();

        // Never migrate the per-user namespace itself, runtime roots, or stale files.
        if name_str == "users"
            || name_str == "AgentRuntime"
            || name_str == "Artifacts"
            || STALE_FILES.iter().any(|stale| stale == &name_str.as_ref())
        {
            continue;
        }

        let source_path = entry.path();
        let dest_path = user_dir.join(&name);

        if source_path.is_dir() && dest_path.is_dir() {
            // Merge directories child-by-child so a partial re-run is safe.
            let children =
                std::fs::read_dir(&source_path).map_err(|_| NativeError::MigrationFailed)?;
            for child in children {
                let child = child.map_err(|_| NativeError::MigrationFailed)?;
                let child_name = child.file_name();
                let child_src = child.path();
                let child_dst = dest_path.join(&child_name);
                if child_dst.exists() {
                    continue;
                }
                std::fs::rename(&child_src, &child_dst)
                    .map_err(|_| NativeError::MigrationFailed)?;
            }
            if directory_is_empty(&source_path) {
                let _ = std::fs::remove_dir(&source_path);
            }
        } else if dest_path.exists() {
            // Destination already wins; drop the stale source copy.
            if source_path.is_dir() {
                let _ = std::fs::remove_dir_all(&source_path);
            } else {
                let _ = std::fs::remove_file(&source_path);
            }
        } else {
            std::fs::rename(&source_path, &dest_path).map_err(|_| NativeError::MigrationFailed)?;
        }
    }

    if source != platform_root && directory_is_empty(&source) {
        let _ = std::fs::remove_dir(&source);
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preserves_the_windows_electron_database_location() {
        let root = data_root_for(
            Platform::Windows,
            None,
            Some(Path::new(r"C:\\Users\\omi\\AppData\\Roaming")),
            None,
        )
        .unwrap();
        assert_eq!(
            root,
            Path::new(r"C:\\Users\\omi\\AppData\\Roaming").join("omi-windows")
        );
    }

    #[test]
    fn resolves_platform_data_roots_without_creating_them() {
        assert_eq!(
            data_root_for(Platform::Macos, Some(Path::new("/Users/omi")), None, None).unwrap(),
            Path::new("/Users/omi/Library/Application Support/Omi")
        );
        assert_eq!(
            data_root_for(
                Platform::Linux,
                Some(Path::new("/home/omi")),
                None,
                Some(Path::new("/var/lib/user-data")),
            )
            .unwrap(),
            Path::new("/var/lib/user-data/Omi")
        );
    }

    #[test]
    fn rejects_missing_or_relative_platform_data_roots() {
        assert_eq!(
            data_root_for(Platform::Windows, None, None, None),
            Err(NativeError::DataRootUnavailable {
                platform: "windows"
            })
        );
        assert_eq!(
            data_root_for(
                Platform::Linux,
                None,
                None,
                Some(Path::new("relative-data")),
            ),
            Err(NativeError::DataRootUnavailable { platform: "linux" })
        );
    }

    #[test]
    fn database_path_override_is_resolved_before_the_platform_root() {
        assert_eq!(
            database_file_for(Some(OsStr::new("/tmp/omi-override.db"))).unwrap(),
            PathBuf::from("/tmp/omi-override.db")
        );
    }

    #[test]
    fn data_root_override_is_absolute_and_wins_over_platform_storage() {
        assert_eq!(
            data_root_with_override_for(
                Some(OsStr::new("/tmp/omi-local")),
                Platform::Macos,
                Some(Path::new("/Users/omi")),
                None,
                None,
            )
            .unwrap(),
            PathBuf::from("/tmp/omi-local")
        );
        assert_eq!(
            data_root_with_override_for(
                Some(OsStr::new("relative")),
                Platform::Macos,
                Some(Path::new("/Users/omi")),
                None,
                None,
            ),
            Err(NativeError::DataRootOverrideNotAbsolute)
        );
    }

    #[test]
    fn detects_named_development_bundles() {
        assert!(is_named_development_bundle("com.omi.omi-memory"));
        assert!(!is_named_development_bundle("com.omi.computer-macos"));
        assert!(!is_named_development_bundle("com.omi.omi-"));
    }

    #[test]
    fn macos_data_root_includes_user_subdirectory() {
        let previous_user = std::env::var("OMI_USER_ID").ok();
        let previous_home = std::env::var("HOME").ok();
        std::env::set_var("OMI_USER_ID", "alice");
        std::env::set_var("HOME", "/Users/omi");
        let expected = Path::new("/Users/omi/Library/Application Support/Omi/users/alice");
        assert_eq!(data_root().unwrap(), expected);
        match previous_user {
            Some(value) => std::env::set_var("OMI_USER_ID", value),
            None => std::env::remove_var("OMI_USER_ID"),
        }
        match previous_home {
            Some(value) => std::env::set_var("HOME", value),
            None => std::env::remove_var("HOME"),
        }
    }
}
