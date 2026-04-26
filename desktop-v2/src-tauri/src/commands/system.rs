use serde::Serialize;
use std::sync::Mutex;
use sysinfo::{Pid, ProcessRefreshKind, RefreshKind, System};
use tauri::command;

/// Read a file and return its raw bytes as a Vec<u8> (serialized as number[]
/// across IPC).  Used by the Companion pipeline to load the PTT WAV for
/// forwarding to Gemini without pulling in @tauri-apps/plugin-fs.
#[command]
pub async fn read_file_bytes(path: String) -> Result<Vec<u8>, String> {
    tokio::fs::read(&path)
        .await
        .map_err(|e| format!("read_file_bytes({}): {}", path, e))
}

/// Bridge for TS-side diagnostics: writes the message to stderr so it shows
/// up in the same terminal as Rust eprintln! traces. Used by the Companion
/// pipeline to make Gemini call / TTS / state-transition logs visible during
/// development without needing devtools open.
#[command]
pub fn term_log(msg: String) {
    eprintln!("[ts] {}", msg);
}

/// A single icon in the macOS dock. Positions and sizes are in AppKit screen
/// points (top-origin), which the TS side converts into image-pixel space
/// using the captured display's scale factor.
#[derive(Debug, serde::Serialize)]
pub struct DockIcon {
    /// AXTitle as reported by the Dock process (e.g. "System Settings",
    /// "Google Chrome"). Some Dock items report `missing value` — those are
    /// filtered out before returning.
    pub name: String,
    /// Top-left corner of the icon's frame in screen points.
    pub x: f64,
    pub y: f64,
    /// Width and height of the icon's frame in screen points.
    pub w: f64,
    pub h: f64,
}

/// Query the macOS Dock's Accessibility tree for the current list of icons
/// with their exact pixel positions. Used by the Companion pipeline to ground
/// dock-icon points deterministically instead of relying on Gemini's
/// spatial-grounding (which is unreliable for small adjacent dock icons).
///
/// Implementation uses `osascript` rather than direct AXUIElement FFI so we
/// can ship without a new dependency. ~80ms cold, ~25ms warm — fine for the
/// once-per-PTT-press cadence.
///
/// Requires Accessibility permission for whichever process is calling. Tauri
/// dev / signed builds already request it for the rdev PTT listener.
#[command]
#[cfg(target_os = "macos")]
pub async fn get_dock_icons() -> Result<Vec<DockIcon>, String> {
    let script = r#"
tell application "System Events"
  tell process "Dock"
    set out to ""
    repeat with i in UI elements of list 1
      try
        set itemName to name of i
        set itemPos to position of i
        set itemSize to size of i
        set out to out & itemName & "|" & (item 1 of itemPos) & "," & (item 2 of itemPos) & "|" & (item 1 of itemSize) & "," & (item 2 of itemSize) & linefeed
      end try
    end repeat
    return out
  end tell
end tell
"#;

    let output = tokio::task::spawn_blocking(move || {
        std::process::Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()
    })
    .await
    .map_err(|e| format!("osascript task panicked: {}", e))?
    .map_err(|e| format!("osascript spawn failed: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("osascript failed: {}", stderr));
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut icons = Vec::new();
    for line in stdout.lines() {
        let parts: Vec<&str> = line.split('|').collect();
        if parts.len() != 3 {
            continue;
        }
        let name = parts[0].trim();
        if name.is_empty() || name == "missing value" {
            continue;
        }
        let pos: Vec<&str> = parts[1].split(',').collect();
        let size: Vec<&str> = parts[2].split(',').collect();
        if pos.len() != 2 || size.len() != 2 {
            continue;
        }
        let (Ok(x), Ok(y), Ok(w), Ok(h)) = (
            pos[0].trim().parse::<f64>(),
            pos[1].trim().parse::<f64>(),
            size[0].trim().parse::<f64>(),
            size[1].trim().parse::<f64>(),
        ) else {
            continue;
        };
        icons.push(DockIcon {
            name: name.to_string(),
            x,
            y,
            w,
            h,
        });
    }
    Ok(icons)
}

#[command]
#[cfg(not(target_os = "macos"))]
pub async fn get_dock_icons() -> Result<Vec<DockIcon>, String> {
    Ok(Vec::new())
}

/// Identity of the macOS app that's currently frontmost. Used by the Companion
/// pipeline to keep Gemini's grounding in-context — when the user is in
/// Chrome/Safari and asks "how do I get to the sports section", we don't want
/// the answer to point at a dock icon.
#[derive(Debug, serde::Serialize)]
pub struct ActiveApp {
    /// `localizedName` of the frontmost NSRunningApplication (e.g. "Google Chrome").
    pub name: String,
    /// `bundleIdentifier` (e.g. "com.google.Chrome"). Empty string if unavailable.
    pub bundle_id: String,
}

/// Return the frontmost app's name + bundle id. Spawns `osascript` to
/// query System Events; ~30 ms warm. Returns the empty `ActiveApp { "", "" }`
/// on non-macOS or on AppleScript failure so the caller can pass through.
#[command]
#[cfg(target_os = "macos")]
pub async fn get_active_app() -> Result<ActiveApp, String> {
    let script = r#"
tell application "System Events"
  set frontApp to first application process whose frontmost is true
  set frontName to name of frontApp
  try
    set frontId to bundle identifier of frontApp
  on error
    set frontId to ""
  end try
  return frontName & "|" & frontId
end tell
"#;

    let output = tokio::task::spawn_blocking(move || {
        std::process::Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()
    })
    .await
    .map_err(|e| format!("osascript task panicked: {}", e))?
    .map_err(|e| format!("osascript spawn failed: {}", e))?;

    if !output.status.success() {
        return Ok(ActiveApp {
            name: String::new(),
            bundle_id: String::new(),
        });
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let line = stdout.trim();
    let mut parts = line.splitn(2, '|');
    let name = parts.next().unwrap_or("").trim().to_string();
    let bundle_id = parts.next().unwrap_or("").trim().to_string();
    Ok(ActiveApp { name, bundle_id })
}

#[command]
#[cfg(not(target_os = "macos"))]
pub async fn get_active_app() -> Result<ActiveApp, String> {
    Ok(ActiveApp {
        name: String::new(),
        bundle_id: String::new(),
    })
}

static SYSTEM: Mutex<Option<System>> = Mutex::new(None);

#[derive(Serialize)]
pub struct MemoryUsage {
    /// Resident set size of this process in bytes.
    pub process_bytes: u64,
    /// Total system RAM in bytes.
    pub total_bytes: u64,
    /// Used system RAM in bytes (active + wired).
    pub used_bytes: u64,
}

#[command]
pub async fn get_memory_usage() -> Result<MemoryUsage, String> {
    let pid = Pid::from_u32(std::process::id());
    let mut guard = SYSTEM.lock().map_err(|e| e.to_string())?;
    let sys = guard.get_or_insert_with(|| {
        System::new_with_specifics(
            RefreshKind::new()
                .with_memory(sysinfo::MemoryRefreshKind::everything())
                .with_processes(ProcessRefreshKind::new().with_memory()),
        )
    });

    sys.refresh_memory();
    sys.refresh_processes_specifics(
        sysinfo::ProcessesToUpdate::Some(&[pid]),
        true,
        ProcessRefreshKind::new().with_memory(),
    );

    let process_bytes = sys.process(pid).map(|p| p.memory()).unwrap_or(0);
    let total_bytes = sys.total_memory();
    let used_bytes = sys.used_memory();

    Ok(MemoryUsage {
        process_bytes,
        total_bytes,
        used_bytes,
    })
}

/// Relaunch the application. Needed after granting macOS Full Disk Access
/// (and occasionally Accessibility) because TCC decisions are cached at
/// process launch for those scopes — the new permission doesn't take effect
/// until the process is restarted.
#[command]
pub fn relaunch_app(app: tauri::AppHandle) {
    app.restart();
}

/// Temporarily unregister every global shortcut. Used by the onboarding
/// shortcut-capture widget: the default floating-bar binding (Cmd+\) would
/// otherwise fire before the webview ever sees the keydown, making it
/// impossible for the user to pick Cmd+\ (or any other already-bound combo)
/// as their shortcut.
#[command]
pub fn suspend_global_shortcuts(app: tauri::AppHandle) -> Result<(), String> {
    use tauri_plugin_global_shortcut::GlobalShortcutExt;
    app.global_shortcut()
        .unregister_all()
        .map_err(|e| format!("unregister_all: {e}"))
}

/// Re-register the floating-bar shortcut. Paired with
/// `suspend_global_shortcuts`; call after the capture widget unmounts. Uses
/// the same `CommandOrControl+\` binding registered at app launch — once
/// onboarding stores a user-chosen chord, a follow-up change will make this
/// read from the store.
#[command]
pub fn restore_global_shortcuts(app: tauri::AppHandle) -> Result<(), String> {
    use tauri_plugin_global_shortcut::GlobalShortcutExt;
    app.global_shortcut()
        .register("CommandOrControl+\\")
        .map_err(|e| format!("register: {e}"))
}
