const COMMANDS: &[&str] = &[
    "take_screenshot",
    "take_screenshot_with_ocr",
    "start_screen_capture",
    "stop_screen_capture",
    "get_active_window_info",
    "get_screen_capture_state",
    "save_screenshot",
    "search_screenshots",
    "get_recent_screenshots",
    "get_screenshot_image",
    "get_screenshot_by_id",
    "delete_old_screenshots",
    "delete_screenshot_by_id",
    "delete_all_screenshots",
    "save_screenshot_embedding",
    "search_screenshots_semantic",
    "screenshots_missing_embeddings",
];

fn main() {
    tauri_plugin::Builder::new(COMMANDS).build();
}
