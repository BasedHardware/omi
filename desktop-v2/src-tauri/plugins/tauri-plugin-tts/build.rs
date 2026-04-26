const COMMANDS: &[&str] = &["tts_speak", "tts_stop", "tts_list_voices"];

fn main() {
    tauri_plugin::Builder::new(COMMANDS).build();
}
