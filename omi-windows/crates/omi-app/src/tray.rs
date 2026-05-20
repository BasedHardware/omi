/// System tray icon + menu for Omi.
///
/// Call `init()` from `main()` (before Dioxus launches) to create the tray.
/// The returned `OmiTray` must be kept alive for the whole process lifetime.
///
/// On Windows the tray is implemented via Shell_NotifyIconW.  The `TrayIcon`
/// drop implementation calls Shell_NotifyIconW(NIM_DELETE) automatically.

use anyhow::Result;
use tray_icon::menu::{Menu, MenuItem, PredefinedMenuItem, MenuEvent};
use tray_icon::{TrayIcon, TrayIconBuilder, TrayIconEvent};
use std::sync::OnceLock;
use tokio::sync::broadcast;

// ── Menu item IDs stored as static strings ────────────────────────────────────

static OPEN_ID: OnceLock<String> = OnceLock::new();
static TOGGLE_RECORD_ID: OnceLock<String> = OnceLock::new();
static QUIT_ID: OnceLock<String> = OnceLock::new();

/// Actions that the tray sends into the app.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrayAction {
    OpenWindow,
    ToggleRecord,
    Quit,
}

pub struct OmiTray {
    _icon: TrayIcon,
    _menu: Menu,
    _open_item: MenuItem,
    _toggle_item: MenuItem,
    _quit_item: MenuItem,
}

/// Create the system-tray icon + menu.  Must be called from `main()`.
pub fn init() -> Result<OmiTray> {
    let menu = Menu::new();

    let open_item = MenuItem::new("Open Omi", true, None);
    let toggle_item = MenuItem::new("Start / Stop Recording", true, None);
    let quit_item = MenuItem::new("Quit", true, None);

    let _ = OPEN_ID.set(open_item.id().0.to_string());
    let _ = TOGGLE_RECORD_ID.set(toggle_item.id().0.to_string());
    let _ = QUIT_ID.set(quit_item.id().0.to_string());

    menu.append_items(&[
        &open_item,
        &toggle_item,
        &PredefinedMenuItem::separator(),
        &quit_item,
    ])
    .map_err(|e| anyhow::anyhow!("Failed to build tray menu: {e:?}"))?;

    // 16×16 RGBA icon — a simple purple square as placeholder
    let icon_size: u32 = 16;
    let mut rgba = Vec::with_capacity((icon_size * icon_size * 4) as usize);
    for _ in 0..(icon_size * icon_size) {
        // #6c5ce7 — matches app accent color
        rgba.extend_from_slice(&[0x6c, 0x5c, 0xe7, 0xff]);
    }
    let icon = tray_icon::Icon::from_rgba(rgba, icon_size, icon_size)
        .map_err(|e| anyhow::anyhow!("Failed to create tray icon: {e:?}"))?;

    // Pass the menu as Box<dyn ContextMenu> — use tray_icon::menu::Menu which
    // satisfies the internal muda version expected by tray-icon.
    let tray = TrayIconBuilder::new()
        .with_menu(Box::new(menu.clone()))
        .with_tooltip("Omi")
        .with_icon(icon)
        .build()
        .map_err(|e| anyhow::anyhow!("Failed to build tray icon: {e:?}"))?;

    tracing::info!("[TRAY] System tray icon created");

    // Keep menu items alive so their IDs remain valid
    Ok(OmiTray { _icon: tray, _menu: menu, _open_item: open_item, _toggle_item: toggle_item, _quit_item: quit_item })
}

/// Spawn a Tokio task that polls tray/menu events and forwards decoded
/// `TrayAction` values on `tx`.
pub fn start_listener(tx: broadcast::Sender<TrayAction>) {
    // Menu click events
    let tx_menu = tx.clone();
    tokio::spawn(async move {
        loop {
            let result = tokio::task::spawn_blocking(|| MenuEvent::receiver().recv()).await;

            match result {
                Ok(Ok(event)) => {
                    let id_str = event.id.0.to_string();
                    let action = if Some(&id_str) == OPEN_ID.get() {
                        Some(TrayAction::OpenWindow)
                    } else if Some(&id_str) == TOGGLE_RECORD_ID.get() {
                        Some(TrayAction::ToggleRecord)
                    } else if Some(&id_str) == QUIT_ID.get() {
                        Some(TrayAction::Quit)
                    } else {
                        None
                    };

                    if let Some(action) = action {
                        tracing::debug!("[TRAY] Menu action: {action:?}");
                        let _ = tx_menu.send(action);
                    }
                }
                Ok(Err(e)) => {
                    tracing::error!("[TRAY] Menu channel error: {e}");
                    break;
                }
                Err(e) => {
                    tracing::error!("[TRAY] spawn_blocking panicked: {e}");
                    break;
                }
            }
        }
    });

    // Tray icon click → show window.
    // TrayIconEvent is an enum in tray-icon 0.19; any event triggers open-window.
    tokio::spawn(async move {
        loop {
            let result = tokio::task::spawn_blocking(|| TrayIconEvent::receiver().recv()).await;

            match result {
                Ok(Ok(_event)) => {
                    tracing::debug!("[TRAY] Tray icon event — opening window");
                    let _ = tx.send(TrayAction::OpenWindow);
                }
                Ok(Err(e)) => {
                    tracing::error!("[TRAY] Icon event channel error: {e}");
                    break;
                }
                Err(e) => {
                    tracing::error!("[TRAY] spawn_blocking panicked: {e}");
                    break;
                }
            }
        }
    });
}
