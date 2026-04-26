//! tauri-plugin-tts — wraps the `speech-helper` Swift sidecar.
//!
//! The sidecar (`swift-helpers/speech/main.swift`) holds one
//! `AVSpeechSynthesizer` for its process lifetime and communicates via
//! line-delimited JSON on stdin/stdout.  This plugin manages the child
//! process, forwards commands, and re-emits sidecar events as Tauri events
//! (`tts:didStart`, `tts:willSpeakRange`, `tts:didFinish`, `tts:didCancel`,
//! `tts:error`).

pub mod commands;

use tauri::{plugin::Builder, plugin::TauriPlugin, Runtime};

pub use commands::TtsVoice;

pub fn init<R: Runtime>() -> TauriPlugin<R> {
    Builder::<R>::new("tts")
        .invoke_handler(tauri::generate_handler![
            commands::tts_speak,
            commands::tts_stop,
            commands::tts_list_voices,
        ])
        .build()
}
