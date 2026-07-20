use std::path::{Path, PathBuf};

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
        }
    }
}

impl std::error::Error for NativeError {}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DatabasePath {
    pub path: String,
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
        Platform::Macos => home
            .map(|path| path.join("Library/Application Support/Omi"))
            .ok_or(NativeError::DataRootUnavailable {
                platform: platform.name(),
            }),
        Platform::Linux => xdg_data_home
            .filter(|path| path.is_absolute())
            .map(|path| path.join("Omi"))
            .or_else(|| home.map(|path| path.join(".local/share/Omi")))
            .ok_or(NativeError::DataRootUnavailable {
                platform: platform.name(),
            }),
    }
}

fn data_root_with_override_for(
    override_path: Option<&std::ffi::OsStr>,
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
    let home = std::env::var_os("HOME").map(PathBuf::from);
    let app_data = std::env::var_os("APPDATA").map(PathBuf::from);
    let xdg_data_home = std::env::var_os("XDG_DATA_HOME").map(PathBuf::from);
    data_root_with_override_for(
        std::env::var_os("OMI_DATA_ROOT").as_deref(),
        Platform::current(),
        home.as_deref(),
        app_data.as_deref(),
        xdg_data_home.as_deref(),
    )
}

pub fn database_file() -> Result<PathBuf, NativeError> {
    database_file_for(std::env::var_os("OMI_DB_PATH").as_deref())
}

fn database_file_for(override_path: Option<&std::ffi::OsStr>) -> Result<PathBuf, NativeError> {
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
            database_file_for(Some(std::ffi::OsStr::new("/tmp/omi-override.db"))).unwrap(),
            PathBuf::from("/tmp/omi-override.db")
        );
    }

    #[test]
    fn data_root_override_is_absolute_and_wins_over_platform_storage() {
        assert_eq!(
            data_root_with_override_for(
                Some(std::ffi::OsStr::new("/tmp/omi-local")),
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
                Some(std::ffi::OsStr::new("relative")),
                Platform::Macos,
                Some(Path::new("/Users/omi")),
                None,
                None,
            ),
            Err(NativeError::DataRootOverrideNotAbsolute)
        );
    }
}
