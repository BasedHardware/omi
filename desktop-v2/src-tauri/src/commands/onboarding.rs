use serde::Serialize;
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Runtime, State};
use tauri_plugin_opener::OpenerExt;

/// Return the host OS as a normalized lowercase string.
#[tauri::command]
pub fn get_platform() -> String {
    match std::env::consts::OS {
        "macos" => "macos".to_string(),
        "windows" => "windows".to_string(),
        _ => "linux".to_string(),
    }
}

// ------------------------- macOS native bindings -------------------------

#[cfg(target_os = "macos")]
mod macos {
    use core_foundation::base::TCFType;
    use core_foundation::boolean::CFBoolean;
    use core_foundation::dictionary::CFDictionary;
    use core_foundation::string::{CFString, CFStringRef};

    #[link(name = "ApplicationServices", kind = "framework")]
    extern "C" {
        /// Returns true if the process is already listed as a trusted accessibility client.
        fn AXIsProcessTrusted() -> bool;
        /// Returns true if trusted; with `kAXTrustedCheckOptionPrompt: true` pops the
        /// system prompt the first time a process requests accessibility.
        fn AXIsProcessTrustedWithOptions(options: core_foundation::dictionary::CFDictionaryRef) -> bool;
        static kAXTrustedCheckOptionPrompt: CFStringRef;
    }

    #[link(name = "CoreGraphics", kind = "framework")]
    extern "C" {
        /// Returns true if the current process has been granted screen-capture access.
        fn CGPreflightScreenCaptureAccess() -> bool;
        /// Requests screen-capture access; returns true if already granted, false if the
        /// user was prompted / hasn't yet granted.
        fn CGRequestScreenCaptureAccess() -> bool;
    }

    #[link(name = "AVFoundation", kind = "framework")]
    extern "C" {}

    // AVCaptureDevice lives in AVFoundation. We only need authorization status,
    // plus an async requestAccess that triggers the OS dialog. We call it via
    // the Objective-C runtime rather than pulling in full objc2 bindings.
    #[link(name = "objc", kind = "dylib")]
    extern "C" {
        fn objc_getClass(name: *const std::os::raw::c_char) -> *mut std::os::raw::c_void;
        fn sel_registerName(name: *const std::os::raw::c_char) -> *mut std::os::raw::c_void;
    }

    #[link(name = "Foundation", kind = "framework")]
    extern "C" {}

    type Id = *mut std::os::raw::c_void;

    extern "C" {
        fn objc_msgSend();
    }

    // Objective-C long enum values for AVAuthorizationStatus:
    // 0 = notDetermined, 1 = restricted, 2 = denied, 3 = authorized
    fn av_authorization_status_for_media_type(media_type: &str) -> i64 {
        use std::ffi::CString;

        unsafe {
            let class_name = CString::new("AVCaptureDevice").unwrap();
            let cls = objc_getClass(class_name.as_ptr()) as Id;
            if cls.is_null() {
                return -1;
            }

            // authorizationStatusForMediaType:
            let sel_name = CString::new("authorizationStatusForMediaType:").unwrap();
            let sel = sel_registerName(sel_name.as_ptr());
            // NSString literal via CFString bridged; use CFString pointer as NSString
            let cf = CFString::new(media_type);
            let ns_string_ptr: *const std::os::raw::c_void = cf.as_concrete_TypeRef() as *const _;

            // Call: (long)[AVCaptureDevice authorizationStatusForMediaType:mediaType]
            // We use a typed function pointer cast to perform a proper ABI call.
            type Fn1 = unsafe extern "C" fn(Id, Id, *const std::os::raw::c_void) -> i64;
            let msg_send: Fn1 = std::mem::transmute(objc_msgSend as *const ());
            msg_send(cls, sel as Id, ns_string_ptr)
        }
    }

    fn av_request_access_for_media_type(media_type: &str) {
        use std::ffi::CString;

        unsafe {
            let class_name = CString::new("AVCaptureDevice").unwrap();
            let cls = objc_getClass(class_name.as_ptr()) as Id;
            if cls.is_null() {
                return;
            }
            let sel_name = CString::new("requestAccessForMediaType:completionHandler:").unwrap();
            let sel = sel_registerName(sel_name.as_ptr());

            let cf = CFString::new(media_type);
            let ns_string_ptr: *const std::os::raw::c_void = cf.as_concrete_TypeRef() as *const _;

            // completionHandler: ^(BOOL) {} — passing a null block is crash-y on recent macOS,
            // so we pass a no-op block structure. To keep this dependency-free we use a minimal
            // stack-allocated C block literal.
            #[repr(C)]
            struct Block {
                isa: *const std::os::raw::c_void,
                flags: i32,
                reserved: i32,
                invoke: extern "C" fn(*mut Block, bool),
                descriptor: *const BlockDescriptor,
            }
            #[repr(C)]
            struct BlockDescriptor {
                reserved: u64,
                size: u64,
            }

            extern "C" fn noop(_block: *mut Block, _granted: bool) {}

            static DESCRIPTOR: BlockDescriptor = BlockDescriptor {
                reserved: 0,
                size: std::mem::size_of::<Block>() as u64,
            };

            // _NSConcreteGlobalBlock symbol
            #[link(name = "System", kind = "dylib")]
            extern "C" {
                static _NSConcreteGlobalBlock: std::os::raw::c_void;
            }

            let mut block = Block {
                isa: &_NSConcreteGlobalBlock as *const _ as *const std::os::raw::c_void,
                flags: 1 << 28, // BLOCK_IS_GLOBAL
                reserved: 0,
                invoke: noop,
                descriptor: &DESCRIPTOR,
            };

            type Fn2 = unsafe extern "C" fn(
                Id,
                Id,
                *const std::os::raw::c_void,
                *mut Block,
            );
            let msg_send: Fn2 = std::mem::transmute(objc_msgSend as *const ());
            msg_send(cls, sel as Id, ns_string_ptr, &mut block);
        }
    }

    pub fn microphone_status() -> &'static str {
        match av_authorization_status_for_media_type("soun") {
            3 => "granted",
            0 => "not_granted",
            1 | 2 => "denied",
            _ => "not_granted",
        }
    }

    pub fn microphone_request() {
        av_request_access_for_media_type("soun");
    }

    pub fn screen_recording_status() -> &'static str {
        if unsafe { CGPreflightScreenCaptureAccess() } {
            "granted"
        } else {
            "not_granted"
        }
    }

    /// Triggers the native macOS screen-recording prompt the first time; on
    /// subsequent calls (already decided) it's a no-op and the user must open
    /// Settings. Returns whether access is currently granted.
    pub fn screen_recording_request() -> bool {
        unsafe { CGRequestScreenCaptureAccess() }
    }

    pub fn accessibility_status() -> &'static str {
        if unsafe { AXIsProcessTrusted() } {
            "granted"
        } else {
            "not_granted"
        }
    }

    /// Calls AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: true}),
    /// which causes macOS to show the native "grant accessibility" prompt if the
    /// app isn't yet trusted.
    pub fn accessibility_request() {
        unsafe {
            let key = CFString::wrap_under_get_rule(kAXTrustedCheckOptionPrompt);
            let val = CFBoolean::true_value();
            let dict = CFDictionary::from_CFType_pairs(&[(key, val)]);
            AXIsProcessTrustedWithOptions(dict.as_concrete_TypeRef());
        }
    }

    /// Probe for Full Disk Access by trying to read a file only FDA-enabled
    /// apps can access. `/Library/Application Support/com.apple.TCC/TCC.db`
    /// is the TCC database — readable only when FDA is granted.
    pub fn full_disk_access_status() -> &'static str {
        use std::fs::File;
        if File::open("/Library/Application Support/com.apple.TCC/TCC.db").is_ok() {
            "granted"
        } else {
            "not_granted"
        }
    }
}

// ------------------------- unified permission commands -------------------------

#[tauri::command]
pub async fn get_permission_status<R: Runtime>(
    _app: AppHandle<R>,
    kind: String,
) -> Result<String, String> {
    #[cfg(target_os = "macos")]
    {
        let result = match kind.as_str() {
            "microphone" => macos::microphone_status(),
            "screen_recording" => macos::screen_recording_status(),
            "accessibility" => macos::accessibility_status(),
            "full_disk_access" => macos::full_disk_access_status(),
            // Automation has no reliable programmatic check on macOS.
            "automation" => "not_granted",
            // Notifications: handled on the JS side via the plugin.
            "notifications" => "not_granted",
            _ => "not_granted",
        };
        return Ok(result.to_string());
    }

    #[cfg(not(target_os = "macos"))]
    {
        // On non-macOS platforms, microphone is checked at capture time by the
        // audio plugin; screen recording / accessibility / automation / full-disk
        // are macOS-only concepts. We treat them as granted so the UI skips them.
        let result = match kind.as_str() {
            "microphone" => "not_granted", // prompt on first use
            _ => "granted",
        };
        return Ok(result.to_string());
    }
}

#[tauri::command]
pub async fn request_permission<R: Runtime>(
    app: AppHandle<R>,
    kind: String,
) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        match kind.as_str() {
            "microphone" => {
                // If already determined, we can't re-prompt — push them to Settings.
                match macos::microphone_status() {
                    "granted" => {}
                    "denied" => open_url(
                        &app,
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
                    )?,
                    _ => macos::microphone_request(),
                }
            }
            "screen_recording" => {
                // Try the native prompt first; if it doesn't fire (already decided), open Settings.
                let already = macos::screen_recording_request();
                if !already && macos::screen_recording_status() == "not_granted" {
                    open_url(
                        &app,
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
                    )?;
                }
            }
            "accessibility" => {
                if macos::accessibility_status() == "not_granted" {
                    // Show the native AX prompt if eligible.
                    macos::accessibility_request();
                    // And open Settings as a reliable fallback (the prompt alone is
                    // sometimes not enough when an older copy was trusted before).
                    open_url(
                        &app,
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
                    )?;
                }
            }
            "automation" => open_url(
                &app,
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
            )?,
            "full_disk_access" => open_url(
                &app,
                "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
            )?,
            "notifications" => {
                // Handled on the JS side via tauri-plugin-notification.
            }
            other => return Err(format!("unknown permission kind: {}", other)),
        }
        Ok(())
    }

    #[cfg(not(target_os = "macos"))]
    {
        // On non-macOS, only microphone has a meaningful prompt path, and it
        // happens implicitly on first capture. Everything else is a no-op.
        let _ = (app, kind);
        Ok(())
    }
}

#[cfg(target_os = "macos")]
fn open_url<R: Runtime>(app: &AppHandle<R>, url: &str) -> Result<(), String> {
    app.opener()
        .open_url(url, None::<&str>)
        .map_err(|e| format!("failed to open {}: {}", url, e))
}

// ----------------- file scan -----------------
//
// Walks a tightly-scoped list of user directories, skipping system / build /
// VCS / cache folders, and reports progress via Tauri events. Memory footprint
// is bounded: only a small set of project root names is kept — never paths.
//
// Events emitted:
//   "file_scan:progress"  { file_count, project_names, current_root }
//   "file_scan:complete"  { file_count, project_names }

#[derive(Serialize, Clone, Default)]
pub struct ScanSnapshot {
    pub file_count: u64,
    pub project_names: Vec<String>,
    /// Installed applications detected on the user's machine (e.g. "Slack",
    /// "Zoom", "Figma"). Mirrors Swift's scan.applications field — gives the
    /// LLM real context about the user's workflow beyond file names.
    pub applications: Vec<String>,
    /// Technologies inferred from file extensions across the scan (e.g.
    /// "TypeScript", "Rust", "Python"). Mirrors Swift's scan.technologies
    /// field. Sorted by frequency, capped to the most common handful.
    pub technologies: Vec<String>,
    pub complete: bool,
    pub current_root: Option<String>,
}

pub struct ScanState {
    pub snapshot: Arc<Mutex<ScanSnapshot>>,
    pub running: Arc<AtomicBool>,
}

// Hard caps to keep memory and latency predictable.
const MAX_FILES: u64 = 50_000;
const MAX_DEPTH: usize = 6;
const MAX_PROJECT_NAMES: usize = 32;
// Progress-event cadence: the webview only needs a refresh every ~250ms to
// feel live. Emitting faster than this in a tight fs loop can saturate the
// Tauri IPC and lock up the window.
const EMIT_INTERVAL_MS: u64 = 400;
const EMIT_EVERY_N_FILES: u64 = 1_000;
// Yield periodically so the walker thread doesn't starve the process or
// saturate the IPC channel into the webview.
const YIELD_EVERY_N_FILES: u64 = 100;
const YIELD_MICROS: u64 = 400;

fn is_skipped_dir(name: &str) -> bool {
    // Hidden dotfiles: always skip. They're almost always config/cache.
    if name.starts_with('.') {
        return true;
    }

    // Hard-banned directories — anywhere in the tree.
    const SKIP: &[&str] = &[
        // VCS + CI
        "node_modules",
        "vendor",
        "bower_components",
        "Pods",
        "Carthage",
        // SDKs / toolchains / VMs that explode file count without yielding
        // project signal
        "Android",
        "flutter",
        "google-cloud-sdk",
        "jdk-17",
        "jdk-21",
        "jdk-11",
        "go",
        "anaconda3",
        "miniconda3",
        ".rustup",
        ".cargo",
        ".npm",
        ".pnpm-store",
        ".yarn",
        ".gradle",
        ".m2",
        ".nvm",
        ".pyenv",
        ".rbenv",
        // Build artifacts
        "target",
        "build",
        "dist",
        "out",
        "output",
        "DerivedData",
        "obj",
        "cmake-build-debug",
        "cmake-build-release",
        // Python
        "__pycache__",
        "venv",
        // System-ish stuff the user shouldn't have us walking into
        "Applications",
        "System",
        "private",
        "Trash",
        "$RECYCLE.BIN",
        "AppData",
        // Linux system mounts that can appear under $HOME on some distros
        "snap",
        "lost+found",
    ];
    SKIP.iter().any(|s| s.eq_ignore_ascii_case(name))
}

fn project_marker(name: &str) -> bool {
    matches!(
        name,
        "package.json"
            | "Cargo.toml"
            | "pyproject.toml"
            | "go.mod"
            | "pom.xml"
            | "build.gradle"
            | "build.gradle.kts"
            | "Gemfile"
            | ".git"
    )
}

fn user_roots() -> Vec<PathBuf> {
    // Order matters here: the walker stops once it hits MAX_FILES, so the
    // first roots in this list get the most budget. Put high-signal,
    // low-noise directories first (conventional code folders), then $HOME
    // itself on Linux where users frequently keep projects at the top level
    // under non-standard folder names (e.g. ~/togodynamics, ~/work, ~/code).
    // Massive, low-signal roots like Downloads come last.
    let mut ordered: Vec<PathBuf> = Vec::new();
    let mut seen: HashSet<PathBuf> = HashSet::new();
    let push = |p: PathBuf, ordered: &mut Vec<PathBuf>, seen: &mut HashSet<PathBuf>| {
        if p.is_dir() && seen.insert(p.clone()) {
            ordered.push(p);
        }
    };

    let Some(home) = dirs_home() else {
        return Vec::new();
    };

    // 1. High-signal code folders the user explicitly named.
    for sub in [
        "Projects",
        "projects",
        "Code",
        "code",
        "Developer",
        "dev",
        "workspace",
        "work",
        "repos",
        "git",
        "src",
        "DataGripProjects",
    ] {
        push(home.join(sub), &mut ordered, &mut seen);
    }

    // 2. $HOME itself (Linux/macOS). On Linux especially, projects often
    //    live in top-level custom folders (~/togodynamics, ~/company, etc.)
    //    rather than inside the conventional names above. Scanning home
    //    with our depth cap still catches those quickly.
    #[cfg(any(target_os = "linux", target_os = "macos"))]
    push(home.clone(), &mut ordered, &mut seen);

    // 3. XDG on Linux: honor xdg-user-dirs so we pick up localized dirs
    //    (~/Documentos, ~/Bureau). Cheap and broad.
    #[cfg(target_os = "linux")]
    {
        let xdg_config = std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join(".config"));
        let user_dirs_file = xdg_config.join("user-dirs.dirs");
        if let Ok(contents) = std::fs::read_to_string(&user_dirs_file) {
            for line in contents.lines() {
                let line = line.trim();
                if line.is_empty() || line.starts_with('#') {
                    continue;
                }
                if let Some(eq) = line.find('=') {
                    let value = line[eq + 1..].trim().trim_matches('"');
                    let expanded = if let Some(stripped) = value.strip_prefix("$HOME/") {
                        home.join(stripped)
                    } else {
                        PathBuf::from(value)
                    };
                    push(expanded, &mut ordered, &mut seen);
                }
            }
        }
    }

    // 4. Mid-signal dirs: Documents and Desktop often have a mix of work
    //    and personal; still useful but lower priority than code folders.
    for sub in ["Documents", "Desktop"] {
        push(home.join(sub), &mut ordered, &mut seen);
    }

    // 5. Low-signal dirs (Downloads can be huge and mostly non-project).
    for sub in ["Downloads"] {
        push(home.join(sub), &mut ordered, &mut seen);
    }

    ordered
}

fn dirs_home() -> Option<PathBuf> {
    // Avoid pulling in the `dirs` crate just for this.
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

/// Return the lowercased file extension (without the dot) if present.
/// Filters out junk like `tar.gz` middle segments — we only keep the last.
fn file_extension(name: &str) -> Option<String> {
    let dot = name.rfind('.')?;
    if dot == 0 || dot == name.len() - 1 {
        return None;
    }
    let ext = name[dot + 1..].to_ascii_lowercase();
    if ext.len() > 6 || !ext.chars().all(|c| c.is_ascii_alphanumeric()) {
        return None;
    }
    Some(ext)
}

/// Map a file extension to a friendly technology name. Mirrors the subset
/// of Swift's `technologyName(forFileExtension:)` that matches the stacks
/// we expect to see on user machines.
fn technology_name(ext: &str) -> Option<&'static str> {
    Some(match ext {
        "swift" => "Swift",
        "dart" => "Flutter",
        "ts" | "tsx" => "TypeScript",
        "js" | "jsx" | "mjs" | "cjs" => "JavaScript",
        "py" | "ipynb" => "Python",
        "rs" => "Rust",
        "go" => "Go",
        "kt" | "kts" => "Kotlin",
        "java" => "Java",
        "rb" => "Ruby",
        "php" => "PHP",
        "cs" => "C#",
        "cpp" | "cc" | "cxx" | "hpp" => "C++",
        "c" | "h" => "C",
        "m" | "mm" => "Objective-C",
        "lua" => "Lua",
        "sh" | "bash" | "zsh" => "Shell",
        "sql" => "SQL",
        "html" | "htm" => "HTML",
        "css" | "scss" | "sass" => "CSS",
        "md" | "mdx" => "Markdown",
        "sol" => "Solidity",
        "r" => "R",
        "ex" | "exs" => "Elixir",
        "erl" => "Erlang",
        "clj" | "cljs" => "Clojure",
        "hs" => "Haskell",
        "ml" | "mli" => "OCaml",
        "scala" => "Scala",
        "zig" => "Zig",
        _ => return None,
    })
}

/// Roots where application bundles / launcher entries live per-platform.
/// These are cheap to scan (one level deep) and give us the strongest
/// signal about the user's workflow tools (Slack, Zoom, Figma, VS Code…).
fn application_roots() -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = Vec::new();

    #[cfg(target_os = "macos")]
    {
        out.push(PathBuf::from("/Applications"));
        if let Some(home) = dirs_home() {
            out.push(home.join("Applications"));
        }
    }

    #[cfg(target_os = "linux")]
    {
        out.push(PathBuf::from("/usr/share/applications"));
        out.push(PathBuf::from("/var/lib/flatpak/exports/share/applications"));
        out.push(PathBuf::from("/var/lib/snapd/desktop/applications"));
        if let Some(home) = dirs_home() {
            out.push(home.join(".local/share/applications"));
            out.push(home.join(".local/share/flatpak/exports/share/applications"));
        }
    }

    #[cfg(target_os = "windows")]
    {
        // Windows Start-menu shortcuts live under these paths.
        if let Some(appdata) = std::env::var_os("APPDATA").map(PathBuf::from) {
            out.push(appdata.join("Microsoft/Windows/Start Menu/Programs"));
        }
        out.push(PathBuf::from(
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        ));
    }

    out.into_iter().filter(|p| p.is_dir()).collect()
}

/// Single-level scan of an application root. Adds entries to the walker
/// without bloating the file-count (applications are not user files).
fn scan_applications_shallow(root: &Path, into: &mut HashSet<String>) {
    let Ok(read) = std::fs::read_dir(root) else { return };
    for entry in read.flatten() {
        if into.len() >= 128 {
            break;
        }
        let name = match entry.file_name().into_string() {
            Ok(s) => s,
            Err(_) => continue,
        };
        let app_name = name
            .strip_suffix(".app")
            .or_else(|| name.strip_suffix(".desktop"))
            .or_else(|| name.strip_suffix(".lnk"));
        if let Some(base) = app_name {
            if !base.is_empty() {
                into.insert(base.to_string());
            }
        }
    }
}

struct Walker<R: Runtime> {
    app: AppHandle<R>,
    state: Arc<Mutex<ScanSnapshot>>,
    running: Arc<AtomicBool>,
    file_count: u64,
    project_names: HashSet<String>,
    /// File-extension frequency across the scan. Sorted at snapshot-build
    /// time and translated to friendly technology names (e.g. "ts" → "TypeScript").
    ext_counts: std::collections::HashMap<String, u64>,
    /// Installed applications discovered during scan (cross-platform best-effort).
    applications: HashSet<String>,
    last_emit: Instant,
    last_emit_files: u64,
}

impl<R: Runtime> Walker<R> {
    fn new(app: AppHandle<R>, state: Arc<Mutex<ScanSnapshot>>, running: Arc<AtomicBool>) -> Self {
        Self {
            app,
            state,
            running,
            file_count: 0,
            project_names: HashSet::with_capacity(MAX_PROJECT_NAMES),
            ext_counts: std::collections::HashMap::with_capacity(64),
            applications: HashSet::with_capacity(64),
            last_emit: Instant::now(),
            last_emit_files: 0,
        }
    }

    fn walk(mut self, roots: Vec<PathBuf>) {
        tracing::info!(target: "file_scan", "walker: started");
        self.emit_log("Starting discovery…");
        std::thread::sleep(Duration::from_millis(220));

        // Pull installed applications up front — these are cheap (single
        // directory read per root) and give us strong workflow signal.
        for app_root in application_roots() {
            scan_applications_shallow(&app_root, &mut self.applications);
        }
        if !self.applications.is_empty() {
            self.emit_log(&format!(
                "Found {} installed application{}.",
                self.applications.len(),
                if self.applications.len() == 1 { "" } else { "s" }
            ));
            self.force_emit();
        }

        // Note: $HOME is pushed by `user_roots()` on Linux/macOS, so we
        // don't need to add it again here.

        tracing::info!(target: "file_scan", roots = ?roots, "walker: {} roots queued", roots.len());

        if roots.is_empty() {
            tracing::warn!(target: "file_scan", "walker: no roots found; nothing to scan");
            self.emit_log("No user directories to scan — skipping.");
            std::thread::sleep(Duration::from_millis(300));
        }

        for root in roots {
            if !self.running.load(Ordering::Relaxed) {
                tracing::info!(target: "file_scan", "walker: cancelled");
                break;
            }
            if !root.is_dir() {
                tracing::debug!(target: "file_scan", path = %root.display(), "walker: root missing, skipping");
                self.emit_log(&format!(
                    "Skipped ~/{} (not found)",
                    root.file_name()
                        .and_then(|n| n.to_str())
                        .unwrap_or("?")
                ));
                continue;
            }
            tracing::info!(target: "file_scan", path = %root.display(), "walker: entering root");
            self.update_current_root(&root);
            // Small beat per root so the live feed visibly advances even on
            // fast local filesystems.
            std::thread::sleep(Duration::from_millis(180));
            self.walk_dir(&root, 0);
            tracing::info!(
                target: "file_scan",
                path = %root.display(),
                files = self.file_count,
                "walker: finished root"
            );
            if self.file_count >= MAX_FILES {
                tracing::warn!(target: "file_scan", limit = MAX_FILES, "walker: hit file limit");
                self.emit_log(&format!("Reached {} file limit — stopping.", MAX_FILES));
                break;
            }
        }

        // Small pause so the user sees the final state for a beat before the
        // UI flips to "Continue enabled".
        std::thread::sleep(Duration::from_millis(300));
        self.emit_log(&format!(
            "Done. {} files · {} projects.",
            self.file_count,
            self.project_names.len()
        ));

        let snapshot = self.build_snapshot(true, None);
        if let Ok(mut s) = self.state.lock() {
            *s = snapshot.clone();
        }
        tracing::info!(
            target: "file_scan",
            files = snapshot.file_count,
            projects = snapshot.project_names.len(),
            "walker: complete"
        );
        if let Err(err) = self.app.emit("file_scan:complete", &snapshot) {
            tracing::warn!(target: "file_scan", error = %err, "emit file_scan:complete failed");
        }
    }

    fn update_current_root(&mut self, root: &Path) {
        let label = root
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("")
            .to_string();
        if let Ok(mut s) = self.state.lock() {
            s.current_root = Some(label.clone());
        }
        self.emit_log(&format!("Scanning ~/{}", label));
        // Force a progress event so the UI updates immediately on root change,
        // even if the root has very few files.
        self.force_emit();
    }

    fn emit_log(&self, message: &str) {
        #[derive(Serialize, Clone)]
        struct LogEvent {
            message: String,
            file_count: u64,
        }
        tracing::info!(
            target: "file_scan",
            files = self.file_count,
            "{}",
            message,
        );
        if let Err(err) = self.app.emit(
            "file_scan:log",
            LogEvent {
                message: message.to_string(),
                file_count: self.file_count,
            },
        ) {
            tracing::warn!(target: "file_scan", error = %err, "emit file_scan:log failed");
        }
    }

    fn force_emit(&mut self) {
        self.last_emit = Instant::now();
        self.last_emit_files = self.file_count;
        let snapshot = self.build_snapshot(false, None);
        if let Ok(mut s) = self.state.lock() {
            *s = snapshot.clone();
        }
        tracing::debug!(
            target: "file_scan",
            files = snapshot.file_count,
            projects = snapshot.project_names.len(),
            root = ?snapshot.current_root,
            "emit progress"
        );
        if let Err(err) = self.app.emit("file_scan:progress", &snapshot) {
            tracing::warn!(target: "file_scan", error = %err, "emit file_scan:progress failed");
        }
    }

    fn walk_dir(&mut self, dir: &Path, depth: usize) {
        if !self.running.load(Ordering::Relaxed) {
            return;
        }
        if self.file_count >= MAX_FILES {
            return;
        }
        if depth > MAX_DEPTH {
            return;
        }

        let read = match std::fs::read_dir(dir) {
            Ok(r) => r,
            Err(e) => {
                tracing::debug!(
                    target: "file_scan",
                    path = %dir.display(),
                    error = %e,
                    "read_dir failed"
                );
                return;
            }
        };

        let mut subdirs: Vec<PathBuf> = Vec::new();
        let mut is_project = false;

        for entry in read.flatten() {
            if !self.running.load(Ordering::Relaxed) {
                return;
            }
            let name = match entry.file_name().into_string() {
                Ok(s) => s,
                Err(_) => continue,
            };

            // Cheap file_type check (doesn't stat again).
            let Ok(ft) = entry.file_type() else { continue };

            if ft.is_dir() {
                // macOS application bundles live as `*.app` directories.
                // Record the base name and don't descend into them — they're
                // huge and the content isn't user work.
                if let Some(app_name) = name.strip_suffix(".app") {
                    if self.applications.len() < 128 {
                        self.applications.insert(app_name.to_string());
                    }
                    continue;
                }
                if is_skipped_dir(&name) {
                    continue;
                }
                subdirs.push(entry.path());
            } else if ft.is_file() || ft.is_symlink() {
                self.file_count = self.file_count.saturating_add(1);
                if project_marker(&name) {
                    is_project = true;
                }
                // Linux: `.desktop` entries describe installed apps.
                if let Some(app_name) = name.strip_suffix(".desktop") {
                    if self.applications.len() < 128 {
                        self.applications.insert(app_name.to_string());
                    }
                }
                if let Some(ext) = file_extension(&name) {
                    *self.ext_counts.entry(ext).or_insert(0) += 1;
                }
                self.maybe_emit();
                // Cooperative yield so we never monopolize CPU or saturate
                // the IPC channel into the webview.
                if self.file_count % YIELD_EVERY_N_FILES == 0 {
                    std::thread::sleep(Duration::from_micros(YIELD_MICROS));
                }
                if self.file_count >= MAX_FILES {
                    return;
                }
            }
        }

        // If this directory looks like a project root, record its name and
        // skip descending — we don't need src/ internals.
        if is_project {
            if let Some(dir_name) = dir.file_name().and_then(|n| n.to_str()) {
                if self.project_names.len() < MAX_PROJECT_NAMES
                    && self.project_names.insert(dir_name.to_string())
                {
                    self.emit_log(&format!("Found project: {}", dir_name));
                    self.force_emit();
                }
            }
            return;
        }

        for sub in subdirs {
            self.walk_dir(&sub, depth + 1);
            if self.file_count >= MAX_FILES {
                return;
            }
        }
    }

    fn maybe_emit(&mut self) {
        let delta_files = self.file_count - self.last_emit_files;
        let elapsed = self.last_emit.elapsed();
        if delta_files < EMIT_EVERY_N_FILES && elapsed < Duration::from_millis(EMIT_INTERVAL_MS) {
            return;
        }
        self.last_emit = Instant::now();
        self.last_emit_files = self.file_count;
        let snapshot = self.build_snapshot(false, None);
        if let Ok(mut s) = self.state.lock() {
            *s = snapshot.clone();
        }
        if let Err(err) = self.app.emit("file_scan:progress", &snapshot) {
            tracing::warn!(target: "file_scan", error = %err, "emit file_scan:progress failed");
        }
    }

    fn build_snapshot(&self, complete: bool, current_root: Option<String>) -> ScanSnapshot {
        let mut names: Vec<String> = self.project_names.iter().cloned().collect();
        names.sort();

        // Rank technologies by observed frequency, then map to friendly
        // names. Keep only the top few — a user's primary stacks are what
        // matter, not every extension their machine has ever seen.
        let mut ext_vec: Vec<(String, u64)> = self
            .ext_counts
            .iter()
            .map(|(k, v)| (k.clone(), *v))
            .collect();
        ext_vec.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
        let mut technologies: Vec<String> = Vec::new();
        let mut seen_tech: HashSet<&str> = HashSet::new();
        for (ext, _) in &ext_vec {
            if let Some(tech) = technology_name(ext) {
                if seen_tech.insert(tech) {
                    technologies.push(tech.to_string());
                    if technologies.len() >= 8 {
                        break;
                    }
                }
            }
        }

        let mut applications: Vec<String> =
            self.applications.iter().cloned().collect();
        applications.sort();
        applications.truncate(32);

        ScanSnapshot {
            file_count: self.file_count,
            project_names: names,
            applications,
            technologies,
            complete,
            current_root: current_root.or_else(|| {
                self.state
                    .lock()
                    .ok()
                    .and_then(|s| s.current_root.clone())
            }),
        }
    }
}

#[tauri::command]
pub async fn start_file_scan<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, ScanState>,
) -> Result<(), String> {
    // If a scan is already running, do nothing — the UI will pick up events.
    if state.running.load(Ordering::Relaxed) {
        tracing::info!(target: "file_scan", "start_file_scan: already running, ignored");
        return Ok(());
    }

    tracing::info!(target: "file_scan", "start_file_scan: invoked");

    // Reset snapshot for a fresh run.
    if let Ok(mut s) = state.snapshot.lock() {
        *s = ScanSnapshot::default();
    }
    state.running.store(true, Ordering::Relaxed);

    let snapshot = Arc::clone(&state.snapshot);
    let running = Arc::clone(&state.running);
    let app_handle = app.clone();

    std::thread::spawn(move || {
        let walker = Walker::new(app_handle, snapshot, Arc::clone(&running));
        walker.walk(user_roots());
        running.store(false, Ordering::Relaxed);
        tracing::info!(target: "file_scan", "start_file_scan: thread exited");
    });

    Ok(())
}

#[tauri::command]
pub async fn cancel_file_scan(state: State<'_, ScanState>) -> Result<(), String> {
    tracing::info!(target: "file_scan", "cancel_file_scan: invoked");
    state.running.store(false, Ordering::Relaxed);
    Ok(())
}

#[tauri::command]
pub async fn get_file_scan_status(state: State<'_, ScanState>) -> Result<ScanSnapshot, String> {
    state
        .snapshot
        .lock()
        .map(|s| s.clone())
        .map_err(|e| format!("scan state poisoned: {}", e))
}

// ----------------- user prefs / goal (best-effort backend sync) -----------------

#[tauri::command]
pub async fn set_user_preferred_name(_name: String) -> Result<(), String> {
    // TODO(backend): POST to embedded backend /user/preferences.
    Ok(())
}

#[tauri::command]
pub async fn set_user_language(_language: String) -> Result<(), String> {
    // TODO(backend): POST to embedded backend /user/preferences.
    Ok(())
}

#[tauri::command]
pub async fn set_onboarding_goal(_goal: String) -> Result<(), String> {
    // TODO(backend): POST to embedded backend /goals once the endpoint exists.
    Ok(())
}

#[tauri::command]
pub async fn set_onboarding_completed(_completed: bool) -> Result<(), String> {
    // TODO(backend): POST to embedded backend /user/preferences.
    Ok(())
}

// ----------------- web research (DuckDuckGo) -----------------
//
// Port of desktop/Sources/OnboardingWebResearchService.swift. Pulls a couple
// of HTML result pages from DuckDuckGo, regex-parses titles + snippets, and
// returns them to the caller. No AI synthesis — the UI renders the first
// snippet as the "From the web" summary, matching the Swift fallback.

#[derive(Serialize, Clone)]
pub struct WebSearchResult {
    pub query: String,
    pub title: String,
    pub url: String,
    pub snippet: String,
}

#[derive(Serialize, Clone)]
pub struct WebResearchOutcome {
    pub summary: String,
    pub results: Vec<WebSearchResult>,
}

fn emit_research_log<R: Runtime>(app: &AppHandle<R>, message: &str) {
    #[derive(Serialize, Clone)]
    struct LogEvent {
        message: String,
        ts_ms: u128,
    }
    let ts_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    if let Err(err) = app.emit(
        "onboarding_research:log",
        LogEvent {
            message: message.to_string(),
            ts_ms,
        },
    ) {
        tracing::warn!(target: "onboarding_research", error = %err, "emit log failed");
    }
}

/// Derives a human-readable org name from an email domain, mirroring
/// `organizationHint()` in the Swift coordinator.
/// Consumer email providers that tell us nothing about the user's org.
/// We skip the "organization hint" for these so we don't run nonsense
/// queries like "Matheus Gmail" against the web search.
const CONSUMER_EMAIL_DOMAINS: &[&str] = &[
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "yahoo.co.uk",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
    "protonmail.com",
    "proton.me",
    "pm.me",
    "duck.com",
    "tutanota.com",
    "fastmail.com",
    "zoho.com",
    "gmx.com",
    "gmx.de",
    "web.de",
    "mail.com",
    "hey.com",
    "yandex.ru",
    "qq.com",
    "163.com",
    "126.com",
];

fn organization_hint(email: Option<&str>) -> Option<String> {
    let domain = email?.split('@').nth(1)?.trim().to_ascii_lowercase();
    if domain.is_empty() {
        return None;
    }
    if CONSUMER_EMAIL_DOMAINS.iter().any(|d| *d == domain) {
        return None;
    }
    let cleaned = domain
        .replace(".com", "")
        .replace(".io", "")
        .replace(".ai", "")
        .replace('-', " ")
        .replace('.', " ");
    let trimmed = cleaned.trim();
    if trimmed.is_empty() {
        return None;
    }
    // Capitalize each word.
    let capitalized: String = trimmed
        .split_whitespace()
        .map(|w| {
            let mut chars = w.chars();
            match chars.next() {
                Some(c) => c.to_uppercase().collect::<String>() + chars.as_str(),
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ");
    Some(capitalized)
}

fn build_web_queries(
    preferred_name: &str,
    email: Option<&str>,
    project_names: &[String],
) -> Vec<String> {
    let mut queries: Vec<String> = Vec::new();
    let org = organization_hint(email);
    let name = preferred_name.trim();
    let has_name = name.len() >= 2;

    // Best signal: name + work organization (skipped for consumer email).
    if let Some(o) = &org {
        if has_name {
            queries.push(format!("{} {}", name, o));
        } else {
            queries.push(o.clone());
        }
    }

    // Second signal: first detected local project, paired with org or name.
    if let Some(project) = project_names.first().filter(|p| !p.is_empty()) {
        let q = match (&org, has_name) {
            (Some(o), _) => format!("{} {}", o, project),
            (None, true) => format!("{} {}", name, project),
            (None, false) => project.clone(),
        };
        if !queries.contains(&q) {
            queries.push(q);
        }
    }

    // Last-ditch: if we still have nothing (consumer email, no projects
    // detected) search the user's name alone. Better than returning
    // zero queries — the UI can at least attempt real research.
    if queries.is_empty() && has_name {
        queries.push(name.to_string());
    }

    queries.into_iter().take(2).collect()
}

fn clean_html(text: &str) -> String {
    // Strip tags, then decode a small set of common entities. Good enough
    // for DuckDuckGo's snippet markup.
    let tag_re = regex::Regex::new(r"<[^>]+>").unwrap();
    let ws_re = regex::Regex::new(r"\s+").unwrap();
    let stripped = tag_re.replace_all(text, " ");
    let decoded = stripped
        .replace("&amp;", "&")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ");
    ws_re.replace_all(&decoded, " ").trim().to_string()
}

fn unwrap_ddg_redirect(raw: &str) -> String {
    // DDG HTML wraps results as /l/?uddg=<percent-encoded-target>.
    if let Some(idx) = raw.find("uddg=") {
        let tail = &raw[idx + 5..];
        let end = tail.find('&').unwrap_or(tail.len());
        let encoded = &tail[..end];
        if let Ok(decoded) = percent_decode(encoded) {
            return decoded;
        }
    }
    raw.to_string()
}

fn percent_decode(input: &str) -> Result<String, std::string::FromUtf8Error> {
    let bytes = input.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hi = (bytes[i + 1] as char).to_digit(16);
            let lo = (bytes[i + 2] as char).to_digit(16);
            if let (Some(h), Some(l)) = (hi, lo) {
                out.push(((h << 4) | l) as u8);
                i += 3;
                continue;
            }
        }
        if bytes[i] == b'+' {
            out.push(b' ');
        } else {
            out.push(bytes[i]);
        }
        i += 1;
    }
    String::from_utf8(out)
}

async fn ddg_search_one(
    query: &str,
    max_results: usize,
) -> Result<Vec<WebSearchResult>, String> {
    if query.trim().is_empty() {
        return Ok(Vec::new());
    }

    // DDG's HTML endpoint returns a result page on POST with form-encoded
    // body. GET often serves a lite landing page without the result markup.
    let url = "https://html.duckduckgo.com/html/";

    let client = reqwest::Client::builder()
        .user_agent(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        )
        .connect_timeout(Duration::from_secs(2))
        .timeout(Duration::from_secs(6))
        .build()
        .map_err(|e| format!("client build: {}", e))?;

    let body = format!("q={}&kl=us-en", urlencoding::encode(query));
    let resp = client
        .post(url)
        .header("Content-Type", "application/x-www-form-urlencoded")
        .header("Referer", "https://html.duckduckgo.com/")
        .body(body)
        .send()
        .await
        .map_err(|e| format!("send: {}", e))?;

    let status = resp.status();
    // 202 is DDG's anti-bot signal: they serve a "please wait" landing page
    // instead of real search markup. Treat it as a distinct error so the
    // caller can explain what's happening to the user.
    if status.as_u16() == 202 {
        return Err("rate-limited (DDG served anti-bot response)".to_string());
    }
    if !status.is_success() {
        return Err(format!("http {}", status.as_u16()));
    }
    let html = resp.text().await.map_err(|e| format!("body: {}", e))?;

    let title_re = regex::Regex::new(
        r#"(?is)<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>"#,
    )
    .map_err(|e| format!("regex title: {}", e))?;
    let snippet_re = regex::Regex::new(
        r#"(?is)<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>"#,
    )
    .map_err(|e| format!("regex snippet: {}", e))?;

    let snippets: Vec<String> = snippet_re
        .captures_iter(&html)
        .map(|c| {
            c.get(1)
                .or_else(|| c.get(2))
                .map(|m| m.as_str().to_string())
                .unwrap_or_default()
        })
        .collect();

    Ok(title_re
        .captures_iter(&html)
        .take(max_results)
        .enumerate()
        .filter_map(|(i, cap)| {
            let raw_url = cap.get(1)?.as_str();
            let raw_title = cap.get(2)?.as_str();
            let resolved_url = unwrap_ddg_redirect(raw_url);
            let title = clean_html(raw_title);
            if title.is_empty() || resolved_url.is_empty() {
                return None;
            }
            let snippet = snippets
                .get(i)
                .map(|s| clean_html(s))
                .unwrap_or_default();
            Some(WebSearchResult {
                query: query.to_string(),
                title,
                url: resolved_url,
                snippet,
            })
        })
        .collect())
}

/// Run a small handful of DDG searches driven by the user's name, email
/// domain, and first detected project. Returns up to ~6 deduped results
/// plus a short summary (first non-empty snippet or title) for the UI.
#[tauri::command]
pub async fn onboarding_web_research<R: Runtime>(
    app: AppHandle<R>,
    preferred_name: String,
    email: Option<String>,
    project_names: Vec<String>,
) -> Result<WebResearchOutcome, String> {
    // Stdout proof-of-life so we can see from the `cargo tauri dev` terminal
    // whether the command was actually invoked. If this prints but the UI
    // still shows nothing, the emit channel is the problem, not invoke.
    eprintln!(
        "[onboarding_web_research] ENTERED command (name={:?}, email={:?}, projects={})",
        preferred_name,
        email,
        project_names.len()
    );
    // Proof-of-life: this line MUST appear in the UI log. If it doesn't,
    // the running binary is stale (Rust edits need a full `cargo tauri dev`
    // restart — the webview HMR alone doesn't rebuild Rust).
    emit_research_log(&app, "web_research: entered Rust command");

    let queries = build_web_queries(&preferred_name, email.as_deref(), &project_names);
    tracing::info!(
        target: "onboarding_research",
        query_count = queries.len(),
        "web research start"
    );
    emit_research_log(&app, &format!("Planned {} search queries.", queries.len()));

    let mut seen: HashSet<String> = HashSet::new();
    let mut all: Vec<WebSearchResult> = Vec::new();
    let mut rate_limited = false;

    if !queries.is_empty() {
        // Hard overall budget so the command always returns quickly, even
        // if every reqwest call stalls. Anything not done in 10s is
        // sacrificed for responsiveness.
        let loop_future = async {
            for q in &queries {
                emit_research_log(&app, &format!("Searching DuckDuckGo: \"{}\"", q));
                tracing::info!(target: "onboarding_research", query = %q, "ddg: searching");
                match ddg_search_one(q, 3).await {
                    Ok(batch) => {
                        emit_research_log(
                            &app,
                            &format!(
                                "→ got {} result{} for \"{}\"",
                                batch.len(),
                                if batch.len() == 1 { "" } else { "s" },
                                q
                            ),
                        );
                        tracing::info!(
                            target: "onboarding_research",
                            query = %q,
                            got = batch.len(),
                            "ddg: done"
                        );
                        for r in batch {
                            if seen.insert(r.url.clone()) {
                                all.push(r);
                            }
                        }
                    }
                    Err(e) => {
                        if e.contains("rate-limited") {
                            rate_limited = true;
                        }
                        emit_research_log(
                            &app,
                            &format!("DDG error for \"{}\": {}", q, e),
                        );
                        tracing::warn!(
                            target: "onboarding_research",
                            query = %q,
                            error = %e,
                            "ddg: query failed"
                        );
                    }
                }
            }
        };

        if tokio::time::timeout(Duration::from_secs(10), loop_future)
            .await
            .is_err()
        {
            emit_research_log(
                &app,
                "Overall search budget (10s) exhausted — returning partial results",
            );
        }
    } else {
        emit_research_log(&app, "No signals to search for — skipping web lookup.");
    }

    emit_research_log(
        &app,
        &format!(
            "Done — {} unique result{} total.",
            all.len(),
            if all.len() == 1 { "" } else { "s" }
        ),
    );

    // Graceful-degrade: never return an empty summary. Shape the fallback
    // to match what we actually know — "From the web" should either quote
    // a real DDG result, explain that DDG throttled us, or admit that we
    // simply don't have enough signal to search usefully.
    let summary = if !all.is_empty() {
        all.iter()
            .find(|r| !r.snippet.is_empty())
            .map(|r| r.snippet.clone())
            .or_else(|| all.first().map(|r| r.title.clone()))
            .unwrap_or_default()
    } else if rate_limited {
        "DuckDuckGo is rate-limiting us right now. Nooto will start with local signals and enrich later.".to_string()
    } else if let Some(hint) = organization_hint(email.as_deref()) {
        format!(
            "No public signals found yet — we'll lean on your work email signal ({}) for now.",
            hint
        )
    } else if let Some(project) = project_names.first().filter(|p| !p.is_empty()) {
        format!(
            "No public signals found yet — we'll lean on local signals like {} for now.",
            project
        )
    } else {
        "No public signals found yet — Nooto will work from local signals as you use it.".to_string()
    };

    emit_research_log(
        &app,
        &format!(
            "web_research: returning {} results, summary_len={}",
            all.len(),
            summary.len()
        ),
    );

    Ok(WebResearchOutcome {
        summary,
        results: all,
    })
}

/// Surface the email-domain organization hint to the UI so the Research
/// step can render the Swift "Identity hint" fallback row.
#[tauri::command]
pub async fn onboarding_organization_hint(email: Option<String>) -> Result<Option<String>, String> {
    Ok(organization_hint(email.as_deref()))
}

// ----------------- Gemini-grounded web research -----------------
//
// Replaces the DDG HTML scraper with Gemini 2.5 Flash + the google_search
// grounding tool. Returns both a model-written summary and the grounded
// source URIs / titles the UI can render under "From the web". Much higher
// signal than DDG HTML scraping, and the google_search tool's retrieval is
// free of the anti-bot throttling that made DDG unusable in practice.

fn build_gemini_prompt(
    preferred_name: &str,
    email: Option<&str>,
    project_names: &[String],
    applications: &[String],
    technologies: &[String],
) -> String {
    let mut bio_lines: Vec<String> = Vec::new();
    if !preferred_name.trim().is_empty() {
        bio_lines.push(format!("Name: {}", preferred_name.trim()));
    }
    if let Some(e) = email.map(str::trim).filter(|e| !e.is_empty()) {
        bio_lines.push(format!("Email: {}", e));
    }
    if let Some(hint) = organization_hint(email) {
        bio_lines.push(format!(
            "Likely organization (inferred from email domain): {}",
            hint
        ));
    }
    if !project_names.is_empty() {
        bio_lines.push(format!(
            "Local project folders on their machine: {}",
            project_names
                .iter()
                .take(8)
                .cloned()
                .collect::<Vec<_>>()
                .join(", ")
        ));
    }
    if !technologies.is_empty() {
        bio_lines.push(format!(
            "Primary technologies/languages on their machine: {}",
            technologies.join(", ")
        ));
    }
    if !applications.is_empty() {
        bio_lines.push(format!(
            "Notable installed applications: {}",
            applications
                .iter()
                .take(20)
                .cloned()
                .collect::<Vec<_>>()
                .join(", ")
        ));
    }
    let bio = if bio_lines.is_empty() {
        "No details provided.".to_string()
    } else {
        bio_lines.join("\n")
    };

    format!(
        "You are writing a short \"From the web\" card for a new user of \
Nooto, a personal AI assistant. You have both public-web access (via \
Google Search) and private signals from the user's own machine. Combine \
both to build a rich, accurate picture.\n\n\
## Research plan\n\
Issue **multiple Google Search queries** across these surfaces before \
writing anything. Do not stop at the first result. Aim to cross-reference \
at least 3 different sources:\n\
1. Professional identity: \"<name> <org>\", \"<name> linkedin\", \
\"<name> <org> site:linkedin.com\".\n\
2. Technical footprint: \"<name> github\", \"<name> <org> site:github.com\", \
\"<first project> <name>\".\n\
3. Social presence: \"<name> twitter\", \"<name> <org> site:x.com\", \
\"<name> bluesky\", \"<name> mastodon\".\n\
4. Publications / company: \"<name> <org> blog\", \"<org> about\", \
\"<name> interview\", \"<name> site:medium.com\".\n\
5. Location / context: add \"<city>\" or \"<country>\" inferred from \
earlier matches to disambiguate common names.\n\n\
Skip any surface when the signal isn't worth searching for — e.g. if \
there's no org hint, don't bother with LinkedIn.\n\n\
## Hard rules\n\
- Ground EVERY factual claim in either a Google Search result you \
actually retrieved or the local signals below. No inventions, no \
plausible-sounding guesses.\n\
- Do NOT conflate the user with unrelated people who share their name. \
Only cite findings when the match is anchored by at least two of: \
organization, project name, city, email domain, or a linked profile.\n\
- Prefer concrete specifics (role, company, one or two notable projects \
or posts) over generic platitudes (\"passionate about tech\").\n\
- Address the user in second person (\"you\"). Never write their name.\n\
- Output 2–3 short sentences, plain prose. No lists, headings, or \
markdown. No sign-off.\n\n\
## USER SIGNALS\n{}\n\n\
## Output shape (pick what fits)\n\
• Strong web match across ≥2 surfaces: \"You're the <role> at <org> \
working on <specific thing> — and on GitHub/LinkedIn/X we can see \
<another specific detail>.\"\n\
• Only one surface matched: weave that single finding with the local \
signals. \"Your LinkedIn shows <role> at <org>, and locally you're \
juggling <projects/tech>.\"\n\
• No web match but rich local signal: skip the web entirely and \
describe them from what's on their machine.\n\
• Nothing to go on: one warm, forward-looking sentence. Never \
apologize, never say \"I couldn't find you.\"",
        bio
    )
}

#[derive(serde::Deserialize)]
struct GeminiResponse {
    #[serde(default)]
    candidates: Vec<GeminiCandidate>,
}

#[derive(serde::Deserialize)]
struct GeminiCandidate {
    #[serde(default)]
    content: Option<GeminiContent>,
    #[serde(default, rename = "groundingMetadata")]
    grounding_metadata: Option<GeminiGroundingMetadata>,
}

#[derive(serde::Deserialize)]
struct GeminiContent {
    #[serde(default)]
    parts: Vec<GeminiPart>,
}

#[derive(serde::Deserialize)]
struct GeminiPart {
    #[serde(default)]
    text: Option<String>,
}

#[derive(serde::Deserialize)]
struct GeminiGroundingMetadata {
    #[serde(default, rename = "groundingChunks")]
    grounding_chunks: Vec<GeminiGroundingChunk>,
    #[serde(default, rename = "webSearchQueries")]
    web_search_queries: Vec<String>,
}

#[derive(serde::Deserialize)]
struct GeminiGroundingChunk {
    #[serde(default)]
    web: Option<GeminiWebChunk>,
}

#[derive(serde::Deserialize)]
struct GeminiWebChunk {
    #[serde(default)]
    uri: Option<String>,
    #[serde(default)]
    title: Option<String>,
}

async fn call_gemini_grounded(
    api_key: &str,
    prompt: &str,
) -> Result<GeminiResponse, String> {
    let url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent";

    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(3))
        .timeout(Duration::from_secs(40))
        .build()
        .map_err(|e| format!("client build: {}", e))?;

    let body = serde_json::json!({
        "contents": [
            { "parts": [ { "text": prompt } ] }
        ],
        "tools": [
            { "google_search": {} }
        ],
        "generationConfig": {
            "temperature": 0.3,
            // Multi-query grounded research needs more output budget —
            // Gemini 2.5's internal reasoning + a 2-3 sentence synthesis
            // across ≥3 sources can easily use 800+ tokens.
            "maxOutputTokens": 1024
        }
    });

    let resp = client
        .post(url)
        .header("x-goog-api-key", api_key)
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("send: {}", e))?;

    let status = resp.status();
    if !status.is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(format!(
            "http {}: {}",
            status.as_u16(),
            body.chars().take(200).collect::<String>()
        ));
    }

    resp.json::<GeminiResponse>()
        .await
        .map_err(|e| format!("parse: {}", e))
}

#[tauri::command]
pub async fn gemini_onboarding_research<R: Runtime>(
    app: AppHandle<R>,
    preferred_name: String,
    email: Option<String>,
    project_names: Vec<String>,
    applications: Option<Vec<String>>,
    technologies: Option<Vec<String>>,
) -> Result<WebResearchOutcome, String> {
    let applications = applications.unwrap_or_default();
    let technologies = technologies.unwrap_or_default();
    eprintln!(
        "[gemini_onboarding_research] ENTERED (name={:?}, email={:?}, projects={}, apps={}, techs={})",
        preferred_name,
        email,
        project_names.len(),
        applications.len(),
        technologies.len(),
    );
    emit_research_log(&app, "web_research: entered Gemini grounded search");
    emit_research_log(
        &app,
        &format!(
            "Signals: {} project{}, {} app{}, {} tech{}.",
            project_names.len(),
            if project_names.len() == 1 { "" } else { "s" },
            applications.len(),
            if applications.len() == 1 { "" } else { "s" },
            technologies.len(),
            if technologies.len() == 1 { "" } else { "s" },
        ),
    );

    let api_key = match std::env::var("GEMINI_API_KEY").ok().filter(|s| !s.is_empty()) {
        Some(k) => k,
        None => {
            emit_research_log(
                &app,
                "GEMINI_API_KEY not configured — falling back to local signals only.",
            );
            let summary = match organization_hint(email.as_deref()) {
                Some(hint) => format!(
                    "No Gemini key set — using your work email signal ({}) as a starting point.",
                    hint
                ),
                None => "No Gemini key set — Nooto will work from local signals.".to_string(),
            };
            return Ok(WebResearchOutcome {
                summary,
                results: Vec::new(),
            });
        }
    };

    let prompt = build_gemini_prompt(
        &preferred_name,
        email.as_deref(),
        &project_names,
        &applications,
        &technologies,
    );
    emit_research_log(&app, "Asking Gemini + Google Search for public context…");

    let response_future = call_gemini_grounded(&api_key, &prompt);
    let response = match tokio::time::timeout(Duration::from_secs(42), response_future).await {
        Ok(Ok(r)) => r,
        Ok(Err(e)) => {
            emit_research_log(&app, &format!("Gemini error: {}", e));
            tracing::warn!(target: "onboarding_research", error = %e, "gemini call failed");
            return Ok(WebResearchOutcome {
                summary: degraded_summary(&preferred_name, email.as_deref(), &project_names),
                results: Vec::new(),
            });
        }
        Err(_) => {
            emit_research_log(&app, "Gemini request timed out after 42s.");
            return Ok(WebResearchOutcome {
                summary: degraded_summary(&preferred_name, email.as_deref(), &project_names),
                results: Vec::new(),
            });
        }
    };

    let cand = response.candidates.into_iter().next();
    let (summary_text, grounding) = match cand {
        Some(c) => {
            let text = c
                .content
                .map(|content| {
                    content
                        .parts
                        .into_iter()
                        .filter_map(|p| p.text)
                        .collect::<Vec<_>>()
                        .join("")
                })
                .unwrap_or_default();
            (text, c.grounding_metadata)
        }
        None => (String::new(), None),
    };

    let (chunks, queries): (Vec<GeminiGroundingChunk>, Vec<String>) = grounding
        .map(|g| (g.grounding_chunks, g.web_search_queries))
        .unwrap_or_default();

    let results: Vec<WebSearchResult> = chunks
        .into_iter()
        .filter_map(|c| c.web)
        .filter_map(|w| {
            let uri = w.uri.unwrap_or_default();
            let title = w.title.unwrap_or_default();
            if uri.is_empty() && title.is_empty() {
                None
            } else {
                Some(WebSearchResult {
                    query: queries.first().cloned().unwrap_or_default(),
                    title,
                    url: uri,
                    snippet: String::new(),
                })
            }
        })
        .collect();

    emit_research_log(
        &app,
        &format!(
            "Gemini returned {} grounded source{} from {} search quer{}.",
            results.len(),
            if results.len() == 1 { "" } else { "s" },
            queries.len(),
            if queries.len() == 1 { "y" } else { "ies" },
        ),
    );

    let summary = if !summary_text.trim().is_empty() {
        summary_text.trim().to_string()
    } else {
        degraded_summary(&preferred_name, email.as_deref(), &project_names)
    };

    emit_research_log(
        &app,
        &format!(
            "web_research: returning {} results, summary_len={}",
            results.len(),
            summary.len()
        ),
    );

    Ok(WebResearchOutcome { summary, results })
}

fn degraded_summary(
    preferred_name: &str,
    email: Option<&str>,
    project_names: &[String],
) -> String {
    if let Some(hint) = organization_hint(email) {
        format!(
            "Couldn't reach Gemini just now — we'll lean on your work email signal ({}) for now.",
            hint
        )
    } else if let Some(project) = project_names.first().filter(|p| !p.is_empty()) {
        format!(
            "Couldn't reach Gemini just now — we'll lean on local signals like {} for now.",
            project
        )
    } else if !preferred_name.trim().is_empty() {
        format!(
            "Couldn't reach Gemini just now — Nooto will get to know {} as you use it.",
            preferred_name.trim()
        )
    } else {
        "Couldn't reach Gemini just now — Nooto will work from local signals.".to_string()
    }
}
