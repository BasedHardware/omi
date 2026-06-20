/// Global hotkey registration and static IDs.
///
/// Call `init()` once from `main()` before launching Dioxus.  The returned
/// `HotkeyManager` must stay alive for the whole process life-time.
///
/// In the Dioxus `App` component use `start_listener()` to spawn a Tokio task
/// that translates raw `GlobalHotKeyEvent`s into `HotkeyAction` values and
/// writes them to a provided channel.

use anyhow::Result;
use global_hotkey::{
    GlobalHotKeyManager, GlobalHotKeyEvent,
    hotkey::{HotKey, Code, Modifiers},
    HotKeyState,
};
use std::sync::OnceLock;
use tokio::sync::broadcast;

// ── Static IDs (set once by init()) ──────────────────────────────────────────

static TOGGLE_BAR_ID: OnceLock<u32> = OnceLock::new();
static TOGGLE_RECORD_ID: OnceLock<u32> = OnceLock::new();
static TOGGLE_VOICE_CHAT_ID: OnceLock<u32> = OnceLock::new();
static PTT_ID: OnceLock<u32> = OnceLock::new();

pub fn toggle_bar_id() -> Option<u32> {
    TOGGLE_BAR_ID.get().copied()
}

pub fn toggle_record_id() -> Option<u32> {
    TOGGLE_RECORD_ID.get().copied()
}

pub fn toggle_voice_chat_id() -> Option<u32> {
    TOGGLE_VOICE_CHAT_ID.get().copied()
}

pub fn ptt_id() -> Option<u32> {
    PTT_ID.get().copied()
}

// ── Action enum ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HotkeyAction {
    ToggleBar,
    StartRecord,
    StopRecord,
    ToggleVoiceChat,
    PttPressed,
    PttReleased,
}

// ── Manager (kept alive by caller) ────────────────────────────────────────────

pub struct HotkeyManager {
    _inner: GlobalHotKeyManager,
}

/// Register all application hotkeys.  Must be called from `main()`.
///
/// Hotkeys registered:
/// - `Ctrl+Shift+Space`  → toggle floating control bar
/// - `Ctrl+Shift+R`      → start / stop recording
pub fn init() -> Result<HotkeyManager> {
    let manager = GlobalHotKeyManager::new()
        .map_err(|e| anyhow::anyhow!("Failed to create hotkey manager: {e:?}"))?;

    let toggle_bar = HotKey::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::Space);
    let toggle_rec = HotKey::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyR);
    let toggle_vc = HotKey::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyV);
    let ptt = HotKey::new(Some(Modifiers::CONTROL), Code::Space);

    manager.register(toggle_bar)
        .map_err(|e| anyhow::anyhow!("Failed to register toggle-bar hotkey: {e:?}"))?;
    manager.register(toggle_rec)
        .map_err(|e| anyhow::anyhow!("Failed to register toggle-record hotkey: {e:?}"))?;
    manager.register(toggle_vc)
        .map_err(|e| anyhow::anyhow!("Failed to register voice-chat hotkey: {e:?}"))?;
    manager.register(ptt)
        .map_err(|e| anyhow::anyhow!("Failed to register PTT hotkey: {e:?}"))?;

    let _ = TOGGLE_BAR_ID.set(toggle_bar.id());
    let _ = TOGGLE_RECORD_ID.set(toggle_rec.id());
    let _ = TOGGLE_VOICE_CHAT_ID.set(toggle_vc.id());
    let _ = PTT_ID.set(ptt.id());

    tracing::info!(
        "[HOTKEY] Registered hotkeys: bar={} rec={} vc={} ptt={}",
        toggle_bar.id(),
        toggle_rec.id(),
        toggle_vc.id(),
        ptt.id()
    );

    Ok(HotkeyManager { _inner: manager })
}

/// Spawn a Tokio task that polls `GlobalHotKeyEvent::receiver()` and sends
/// decoded `HotkeyAction` values on `tx`.  The task runs forever.
pub fn start_listener(tx: broadcast::Sender<HotkeyAction>) {
    tokio::spawn(async move {
        loop {
            // recv() is blocking — offload to a blocking thread so we don't
            // stall the async executor.
            let result = tokio::task::spawn_blocking(|| {
                GlobalHotKeyEvent::receiver().recv()
            })
            .await;

            match result {
                Ok(Ok(event)) => {
                    let action = if Some(event.id) == toggle_bar_id() && event.state == HotKeyState::Pressed {
                        Some(HotkeyAction::ToggleBar)
                    } else if Some(event.id) == toggle_record_id() {
                        if event.state == HotKeyState::Pressed {
                            Some(HotkeyAction::StartRecord)
                        } else {
                            Some(HotkeyAction::StopRecord)
                        }
                    } else if Some(event.id) == toggle_voice_chat_id() && event.state == HotKeyState::Pressed {
                        Some(HotkeyAction::ToggleVoiceChat)
                    } else if Some(event.id) == ptt_id() {
                        if event.state == HotKeyState::Pressed {
                            Some(HotkeyAction::PttPressed)
                        } else {
                            Some(HotkeyAction::PttReleased)
                        }
                    } else {
                        None
                    };

                    if let Some(action) = action {
                        tracing::debug!("[HOTKEY] Action: {action:?}");
                        let _ = tx.send(action);
                    }
                }
                Ok(Err(e)) => {
                    tracing::error!("[HOTKEY] Channel error: {e}");
                    break;
                }
                Err(e) => {
                    tracing::error!("[HOTKEY] spawn_blocking panicked: {e}");
                    break;
                }
            }
        }
        tracing::warn!("[HOTKEY] Listener task exited");
    });
}
