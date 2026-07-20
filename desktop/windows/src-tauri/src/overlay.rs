use std::sync::Mutex;

#[cfg(target_os = "macos")]
use std::sync::{
    atomic::{AtomicBool, Ordering},
    OnceLock,
};

use serde::Serialize;
use tauri::{
    AppHandle, Emitter, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent,
};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

#[cfg(target_os = "macos")]
use objc2::MainThreadMarker;
#[cfg(target_os = "macos")]
use objc2_app_kit::{
    NSBackingStoreType, NSColor, NSPanel, NSScreen, NSWindow, NSWindowCollectionBehavior,
    NSWindowLevel, NSWindowStyleMask,
};
#[cfg(target_os = "macos")]
use objc2_foundation::{NSPoint, NSRect, NSSize};

const DEFAULT_ACCELERATOR: &str = "Shift+Space";
const OVERLAY_LABEL: &str = "overlay";
const SHOWN: &str = "omi://overlay-shown";
const WILL_HIDE: &str = "omi://overlay-will-hide";
const SUMMONED: &str = "omi://overlay-summoned";
const ACTIVE: &str = "omi://overlay-active";
const VISIBILITY: &str = "omi://overlay-visibility";
const VOICE_CAPTURED: &str = "omi://overlay-voice-captured";
const ASKED: &str = "omi://overlay-asked";
const ERROR: &str = "omi://overlay-error";

#[cfg(target_os = "macos")]
const NOTCH_WINDOW_LEVEL: NSWindowLevel = 27;
#[cfg(target_os = "macos")]
static NOTCH_PANEL: OnceLock<usize> = OnceLock::new();
#[cfg(target_os = "macos")]
static NOTCH_INSTALLED: AtomicBool = AtomicBool::new(false);

#[derive(Debug)]
struct OverlayConfig {
    accelerator: String,
    #[cfg(target_os = "macos")]
    height: f64,
    enabled: bool,
    suspended: bool,
    visible: bool,
}

pub struct OverlayState(Mutex<OverlayConfig>);

impl Default for OverlayState {
    fn default() -> Self {
        Self(Mutex::new(OverlayConfig {
            accelerator: DEFAULT_ACCELERATOR.into(),
            #[cfg(target_os = "macos")]
            height: 190.0,
            enabled: false,
            suspended: false,
            visible: false,
        }))
    }
}

#[derive(Clone, Serialize)]
struct Visibility {
    open: bool,
    active: bool,
}

fn with_config<T>(app: &AppHandle, callback: impl FnOnce(&mut OverlayConfig) -> T) -> T {
    let state = app.state::<OverlayState>();
    let mut config = state.0.lock().unwrap_or_else(|error| error.into_inner());
    callback(&mut config)
}

fn shortcut_for(accelerator: &str) -> String {
    let modifier = if cfg!(target_os = "macos") {
        "super"
    } else {
        "control"
    };
    accelerator
        .split('+')
        .map(str::trim)
        .map(|token| match token {
            "CommandOrControl" | "CmdOrCtrl" => modifier,
            "Command" | "Cmd" | "Super" | "Meta" => "super",
            "Control" | "Ctrl" => "control",
            "Return" => "enter",
            "Space" => "space",
            "Escape" => "escape",
            "ArrowUp" | "Up" => "up",
            "ArrowDown" | "Down" => "down",
            "ArrowLeft" | "Left" => "left",
            "ArrowRight" | "Right" => "right",
            token => token,
        })
        .collect::<Vec<_>>()
        .join("+")
        .to_lowercase()
}

fn parse_shortcut(accelerator: &str) -> Result<Shortcut, String> {
    shortcut_for(accelerator)
        .parse::<Shortcut>()
        .map_err(|error| error.to_string())
}

fn overlay_height(px: f64) -> Result<f64, String> {
    if !px.is_finite() || px <= 0.0 {
        return Err("overlay height must be a positive finite number".into());
    }
    Ok(px.clamp(120.0, 700.0))
}

#[cfg(target_os = "macos")]
fn panel_frame(screen_frame: NSRect, width: f64, height: f64) -> NSRect {
    NSRect::new(
        NSPoint::new(
            screen_frame.origin.x + (screen_frame.size.width - width) / 2.0,
            screen_frame.origin.y + screen_frame.size.height - height,
        ),
        NSSize::new(width, height),
    )
}

#[cfg(target_os = "macos")]
fn install_notch_panel(window: &WebviewWindow) -> Result<(), String> {
    if NOTCH_INSTALLED.load(Ordering::Acquire) {
        return Ok(());
    }
    let raw_window = window.ns_window().map_err(|error| error.to_string())?;
    if raw_window.is_null() {
        return Err("notch window is unavailable".into());
    }
    let raw_window = raw_window as usize;
    window
        .run_on_main_thread(move || {
            let Some(mtm) = MainThreadMarker::new() else {
                return;
            };
            let window = unsafe { &*(raw_window as *mut NSWindow) };
            let Some(content_view) = window.contentView() else {
                return;
            };
            let panel = NSPanel::initWithContentRect_styleMask_backing_defer(
                mtm.alloc(),
                window.frame(),
                NSWindowStyleMask::Borderless | NSWindowStyleMask::NonactivatingPanel,
                NSBackingStoreType::Buffered,
                false,
            );
            panel.setFloatingPanel(true);
            panel.setBecomesKeyOnlyIfNeeded(false);
            panel.setWorksWhenModal(true);
            panel.setMovable(false);
            panel.setHasShadow(false);
            panel.setOpaque(false);
            panel.setIgnoresMouseEvents(false);
            panel.setAcceptsMouseMovedEvents(true);
            panel.setBackgroundColor(Some(&NSColor::clearColor()));
            panel.setLevel(NOTCH_WINDOW_LEVEL);
            panel.setCollectionBehavior(
                NSWindowCollectionBehavior::CanJoinAllSpaces
                    | NSWindowCollectionBehavior::Stationary
                    | NSWindowCollectionBehavior::IgnoresCycle
                    | NSWindowCollectionBehavior::FullScreenAuxiliary,
            );
            panel.setContentView(Some(&content_view));
            window.setContentView(None);
            window.orderOut(None);
            let _ = NOTCH_PANEL.set(objc2::rc::Retained::into_raw(panel) as usize);
            NOTCH_INSTALLED.store(true, Ordering::Release);
        })
        .map_err(|error| error.to_string())?;
    for _ in 0..20 {
        if NOTCH_INSTALLED.load(Ordering::Acquire) {
            return Ok(());
        }
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
    Err("notch panel could not be created".into())
}

#[cfg(target_os = "macos")]
fn resize_notch_panel(window: &WebviewWindow, width: f64, height: f64) -> Result<(), String> {
    let raw_panel = NOTCH_PANEL.get().copied().ok_or("no notch panel")?;
    window
        .run_on_main_thread(move || {
            let Some(mtm) = MainThreadMarker::new() else {
                return;
            };
            let panel = unsafe { &*(raw_panel as *mut NSPanel) };
            if let Some(screen) = panel.screen().or_else(|| NSScreen::mainScreen(mtm)) {
                panel.setFrame_display(panel_frame(screen.frame(), width, height), true);
            }
            panel.orderFrontRegardless();
        })
        .map_err(|error| error.to_string())
}

#[cfg(target_os = "macos")]
fn show_notch_panel(window: &WebviewWindow, height: f64) -> Result<(), String> {
    install_notch_panel(window)?;
    resize_notch_panel(window, 640.0, height)
}

#[cfg(target_os = "macos")]
fn hide_notch_panel(window: &WebviewWindow) -> Result<(), String> {
    if let Some(raw_panel) = NOTCH_PANEL.get().copied() {
        window
            .run_on_main_thread(move || {
                let panel = unsafe { &*(raw_panel as *mut NSPanel) };
                panel.orderOut(None);
            })
            .map_err(|error| error.to_string())?;
    }
    window.hide().map_err(|error| error.to_string())
}

fn overlay(app: &AppHandle) -> tauri::Result<WebviewWindow> {
    if let Some(window) = app.get_webview_window(OVERLAY_LABEL) {
        return Ok(window);
    }
    let app_handle = app.clone();
    let window = WebviewWindowBuilder::new(
        app,
        OVERLAY_LABEL,
        WebviewUrl::App("index.html#/overlay".into()),
    )
    .title("Omi")
    .inner_size(
        if cfg!(target_os = "macos") {
            640.0
        } else {
            480.0
        },
        200.0,
    )
    .min_inner_size(336.0, 120.0)
    .resizable(false)
    .decorations(false)
    .always_on_top(true)
    .skip_taskbar(true)
    .transparent(cfg!(target_os = "macos"))
    .visible(false)
    .build()?;
    window.on_window_event(move |event| match event {
        WindowEvent::CloseRequested { api, .. } => {
            api.prevent_close();
            if let Err(error) = hide(&app_handle) {
                report_error(&app_handle, error.to_string());
            }
        }
        WindowEvent::Focused(active) => {
            if let Err(error) = app_handle.emit(ACTIVE, active) {
                report_error(&app_handle, error.to_string());
            }
            if let Err(error) = broadcast_visibility(&app_handle) {
                report_error(&app_handle, error.to_string());
            }
        }
        _ => {}
    });
    Ok(window)
}

fn broadcast_visibility(app: &AppHandle) -> tauri::Result<()> {
    let Some(window) = app.get_webview_window(OVERLAY_LABEL) else {
        return app.emit(
            VISIBILITY,
            Visibility {
                open: false,
                active: false,
            },
        );
    };
    let open = if cfg!(target_os = "macos") {
        with_config(app, |config| config.visible)
    } else {
        window.is_visible()?
    };
    app.emit(
        VISIBILITY,
        Visibility {
            open,
            active: open && window.is_focused()?,
        },
    )
}

fn show(app: &AppHandle) -> tauri::Result<()> {
    let window = overlay(app)?;
    #[cfg(target_os = "macos")]
    show_notch_panel(&window, with_config(app, |config| config.height))
        .map_err(|error| tauri::Error::Anyhow(anyhow::Error::msg(error)))?;
    #[cfg(not(target_os = "macos"))]
    {
        window.center()?;
        window.show()?;
        window.set_focus()?;
    }
    with_config(app, |config| config.visible = true);
    app.emit(SHOWN, ())?;
    broadcast_visibility(app)
}

fn hide(app: &AppHandle) -> tauri::Result<()> {
    let Some(window) = app.get_webview_window(OVERLAY_LABEL) else {
        return Ok(());
    };
    let visible = if cfg!(target_os = "macos") {
        with_config(app, |config| config.visible)
    } else {
        window.is_visible()?
    };
    if visible {
        app.emit(WILL_HIDE, ())?;
    }
    #[cfg(target_os = "macos")]
    hide_notch_panel(&window).map_err(|error| tauri::Error::Anyhow(anyhow::Error::msg(error)))?;
    #[cfg(not(target_os = "macos"))]
    window.hide()?;
    with_config(app, |config| config.visible = false);
    broadcast_visibility(app)
}

fn toggle(app: &AppHandle) -> tauri::Result<()> {
    if !with_config(app, |config| config.enabled) {
        return Ok(());
    }
    let visible = if cfg!(target_os = "macos") {
        with_config(app, |config| config.visible)
    } else {
        app.get_webview_window(OVERLAY_LABEL)
            .map(|window| window.is_visible())
            .transpose()?
            .unwrap_or(false)
    };
    if visible {
        hide(app)
    } else {
        show(app)?;
        app.emit(SUMMONED, ())
    }
}

fn register(app: &AppHandle, accelerator: &str) -> Result<(), String> {
    let shortcut = parse_shortcut(accelerator)?;
    app.global_shortcut()
        .on_shortcut(shortcut, |app, _, event| {
            if event.state == ShortcutState::Pressed {
                if let Err(error) = toggle(app) {
                    report_error(app, error.to_string());
                }
            }
        })
        .map_err(|error| error.to_string())
}

fn unregister(app: &AppHandle, accelerator: &str) -> Result<(), String> {
    let shortcut = parse_shortcut(accelerator)?;
    app.global_shortcut()
        .unregister(shortcut)
        .map_err(|error| error.to_string())
}

pub fn register_default(app: &AppHandle) {
    if let Err(error) = register(app, DEFAULT_ACCELERATOR) {
        report_error(app, error);
    }
}

fn report_error(app: &AppHandle, error: String) {
    eprintln!("Omi overlay failed: {error}");
    if let Err(emit_error) = app.emit(ERROR, error) {
        eprintln!("Omi overlay could not report its failure: {emit_error}");
    }
}

#[tauri::command]
pub fn overlay_set_enabled(app: AppHandle, enabled: bool) -> Result<(), String> {
    with_config(&app, |config| config.enabled = enabled);
    if enabled {
        overlay(&app).map_err(|error| error.to_string())?;
    } else {
        hide(&app).map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn overlay_set_height(app: AppHandle, px: f64) -> Result<(), String> {
    let px = overlay_height(px)?;
    #[cfg(target_os = "macos")]
    {
        with_config(&app, |config| config.height = px);
        if NOTCH_INSTALLED.load(Ordering::Acquire) {
            let window = overlay(&app).map_err(|error| error.to_string())?;
            resize_notch_panel(&window, 640.0, px)?;
        }
        Ok(())
    }
    #[cfg(not(target_os = "macos"))]
    {
        let window = overlay(&app).map_err(|error| error.to_string())?;
        window
            .set_size(tauri::LogicalSize::new(480.0, px))
            .map_err(|error| error.to_string())
    }
}

#[tauri::command]
pub fn overlay_hide(app: AppHandle) -> Result<(), String> {
    hide(&app).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn overlay_focus_main(app: AppHandle) -> Result<(), String> {
    hide(&app).map_err(|error| error.to_string())?;
    let main = app
        .get_webview_window("main")
        .ok_or_else(|| "main window is unavailable".to_string())?;
    main.show().map_err(|error| error.to_string())?;
    main.set_focus().map_err(|error| error.to_string())
}

#[tauri::command]
pub fn overlay_set_accelerator(app: AppHandle, accelerator: String) -> Result<bool, String> {
    if accelerator.trim().is_empty() {
        return Err("shortcut cannot be empty".into());
    }
    let previous = with_config(&app, |config| config.accelerator.clone());
    if accelerator == previous
        && parse_shortcut(&accelerator)
            .map(|shortcut| app.global_shortcut().is_registered(shortcut))
            .unwrap_or(false)
    {
        return Ok(true);
    }
    unregister(&app, &previous)?;
    if let Err(error) = register(&app, &accelerator) {
        if let Err(restore_error) = register(&app, &previous) {
            return Err(format!(
                "could not register shortcut: {error}; could not restore previous shortcut: {restore_error}"
            ));
        }
        return Err(format!("could not register shortcut: {error}"));
    }
    with_config(&app, |config| config.accelerator = accelerator);
    Ok(true)
}

#[tauri::command]
pub fn overlay_suspend_shortcut(app: AppHandle) -> Result<(), String> {
    if let Some(accelerator) = with_config(&app, |config| {
        if config.suspended {
            None
        } else {
            config.suspended = true;
            Some(config.accelerator.clone())
        }
    }) {
        unregister(&app, &accelerator)?;
    }
    Ok(())
}

#[tauri::command]
pub fn overlay_resume_shortcut(app: AppHandle) -> Result<bool, String> {
    let accelerator = with_config(&app, |config| config.accelerator.clone());
    if parse_shortcut(&accelerator)
        .map(|shortcut| app.global_shortcut().is_registered(shortcut))
        .unwrap_or(false)
    {
        with_config(&app, |config| config.suspended = false);
        return Ok(true);
    }
    register(&app, &accelerator)?;
    with_config(&app, |config| config.suspended = false);
    Ok(true)
}

#[tauri::command]
pub fn overlay_notify_voice_captured(app: AppHandle) -> Result<(), String> {
    app.emit(VOICE_CAPTURED, ())
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn overlay_notify_asked(app: AppHandle) -> Result<(), String> {
    app.emit(ASKED, ()).map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn translates_electron_accelerators_for_tauri() {
        assert_eq!(shortcut_for("Shift+Space"), "shift+space");
        assert_eq!(
            shortcut_for("CommandOrControl+Return"),
            if cfg!(target_os = "macos") {
                "super+enter"
            } else {
                "control+enter"
            }
        );
        assert_eq!(shortcut_for("Super+ArrowUp"), "super+up");
    }

    #[test]
    fn rejects_invalid_overlay_heights() {
        assert!(overlay_height(0.0).is_err());
        assert!(overlay_height(f64::NAN).is_err());
        assert_eq!(overlay_height(1_000.0), Ok(700.0));
    }
}
