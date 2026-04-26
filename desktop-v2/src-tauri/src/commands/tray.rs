//! System tray / menu bar icon.
//!
//! Mirrors the Swift desktop app's NSStatusBar menu: quick toggles for Aura
//! (screen capture) and Audio Recording, plus Ask Nooto / Open Nooto / Quit.
//!
//! State flows one-way: the frontend is source of truth for Aura and
//! recording status (they live in Zustand + the audio-capture plugin). On
//! state change, the frontend calls `update_tray_menu` to refresh the check
//! marks. Menu clicks emit `tray:*` events that the frontend handles by
//! calling the same store actions the sidebar uses — so pre-flight checks
//! (Gemini API key, commercial-hours gate) still run.

use std::sync::Mutex;

use tauri::{
    command,
    menu::{CheckMenuItem, Menu, MenuEvent, MenuItem, PredefinedMenuItem},
    tray::TrayIconBuilder,
    AppHandle, Emitter, Manager, Wry,
};

/// Menu item IDs.
const ID_AURA: &str = "tray_aura";
const ID_RECORDING: &str = "tray_recording";
const ID_ASK: &str = "tray_ask";
const ID_OPEN: &str = "tray_open";
const ID_QUIT: &str = "tray_quit";

/// Handles to menu items so we can update their state from Tauri commands.
pub struct TrayMenuItems {
    pub aura: CheckMenuItem<Wry>,
    pub recording: CheckMenuItem<Wry>,
    /// The "Ask Nooto" / "Companion" menu item — label is updated at runtime
    /// when the Companion cutover flag is active.
    pub ask: MenuItem<Wry>,
}

pub struct TrayMenuState(pub Mutex<Option<TrayMenuItems>>);

pub fn build(app: &AppHandle) -> tauri::Result<()> {
    let aura = CheckMenuItem::with_id(app, ID_AURA, "Rewind", true, false, None::<&str>)?;
    let recording = CheckMenuItem::with_id(
        app,
        ID_RECORDING,
        "Audio Recording",
        true,
        false,
        None::<&str>,
    )?;
    // Default label: "Ask Nooto" (legacy). The frontend replaces this with
    // "Companion" at boot when COMPANION_CUTOVER_ENABLED is true.
    let ask = MenuItem::with_id(app, ID_ASK, "Ask Nooto", true, None::<&str>)?;
    let open = MenuItem::with_id(app, ID_OPEN, "Open Nooto", true, None::<&str>)?;
    let sep1 = PredefinedMenuItem::separator(app)?;
    let sep2 = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, ID_QUIT, "Quit", true, None::<&str>)?;

    // Clone `ask` so we can both put it in the menu AND store the handle for
    // later mutation (update_tray_menu can rename it at runtime).
    let ask_clone = ask.clone();
    let menu = Menu::with_items(
        app,
        &[&aura, &recording, &sep1, &ask_clone, &open, &sep2, &quit],
    )?;

    app.manage(TrayMenuState(Mutex::new(Some(TrayMenuItems {
        aura,
        recording,
        ask,
    }))));

    // Reuse the window icon for the tray. On macOS, mark it as a template
    // so the system renders it with menu-bar-appropriate colors (matches the
    // Swift app's `isTemplate = true`).
    let icon = app
        .default_window_icon()
        .cloned()
        .ok_or_else(|| tauri::Error::AssetNotFound("default window icon".into()))?;

    TrayIconBuilder::with_id("main")
        .icon(icon)
        .icon_as_template(true)
        .tooltip("Nooto")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(handle_menu_event)
        .build(app)?;

    Ok(())
}

fn handle_menu_event(app: &AppHandle, event: MenuEvent) {
    match event.id().as_ref() {
        ID_AURA => {
            let _ = app.emit("tray:toggle-aura", ());
        }
        ID_RECORDING => {
            let _ = app.emit("tray:toggle-recording", ());
        }
        ID_ASK => {
            let _ = app.emit("tray:ask-nooto", ());
        }
        ID_OPEN => {
            let _ = app.emit("tray:open-main", ());
        }
        ID_QUIT => {
            app.exit(0);
        }
        _ => {}
    }
}

#[command]
pub fn update_tray_menu(
    app: AppHandle,
    aura_on: bool,
    recording_on: bool,
) -> Result<(), String> {
    let state = app.state::<TrayMenuState>();
    let guard = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(items) = guard.as_ref() {
        items.aura.set_checked(aura_on).map_err(|e| e.to_string())?;
        items
            .recording
            .set_checked(recording_on)
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Rename the "Ask Nooto" tray menu item. Called by the frontend at boot when
/// the Companion cutover flag is active (passes "Companion"); called with
/// "Ask Nooto" when the flag is off to preserve the rollback path.
#[command]
pub fn set_tray_ask_label(app: AppHandle, label: String) -> Result<(), String> {
    let state = app.state::<TrayMenuState>();
    let guard = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(items) = guard.as_ref() {
        items.ask.set_text(&label).map_err(|e| e.to_string())?;
    }
    Ok(())
}
