#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
fn relay_contract_probe() -> String {
    "omi-relay-contract:v1|native-seam:rust|payload:bounded|gap:explicit".to_string()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![greet, relay_contract_probe])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
