const COMMANDS: &[&str] = &[
    "list_devices",
    "start_recording",
    "stop_recording",
    "get_capture_state",
    "probe_system_audio",
    "probe_live_capture",
    "request_system_audio_permission",
];

fn main() {
    tauri_plugin::Builder::new(COMMANDS).build();
}
