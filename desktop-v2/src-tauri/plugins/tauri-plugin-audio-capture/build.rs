const COMMANDS: &[&str] = &[
    "list_devices",
    "start_recording",
    "stop_recording",
    "get_capture_state",
];

fn main() {
    tauri_plugin::Builder::new(COMMANDS).build();
}
