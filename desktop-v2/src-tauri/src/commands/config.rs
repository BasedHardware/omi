/// Commands for reading app configuration (API keys, etc.)
///
/// API keys are read from environment variables or a .env file in the
/// Tauri app directory. They never leave the local machine.

use tauri::command;

/// Return the Gemini API key from the environment.
///
/// The key is loaded from `GEMINI_API_KEY` env var (set via .env or shell).
/// Returns `None` if the key is not configured.
#[command]
pub async fn get_gemini_api_key() -> Option<String> {
    std::env::var("GEMINI_API_KEY").ok().filter(|s| !s.is_empty())
}
