use serde::{Deserialize, Serialize};
use std::path::PathBuf;

const CONFIG_DIR: &str = "omi";
const CONFIG_FILE: &str = "config.json";

/// Persisted application configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    /// Rust sidecar backend URL
    #[serde(default = "default_backend_url")]
    pub backend_url: String,

    /// Self-hosted Python backend URL
    #[serde(default = "default_python_backend_url")]
    pub python_backend_url: String,

    /// Deepgram API key for speech-to-text
    #[serde(default)]
    pub deepgram_api_key: String,

    /// Gemini API key for LLM
    #[serde(default)]
    pub gemini_api_key: String,

    /// OpenAI / Azure OpenAI API key
    #[serde(default)]
    pub openai_api_key: String,

    /// OpenAI base URL (set to Azure endpoint for Azure OpenAI)
    /// e.g. https://YOUR-RESOURCE.openai.azure.com/openai/deployments/YOUR-DEPLOYMENT
    #[serde(default = "default_openai_base_url")]
    pub openai_base_url: String,

    /// OpenAI model name (or Azure deployment name)
    #[serde(default = "default_openai_model")]
    pub openai_model: String,

    /// Groq API key (fast inference)
    #[serde(default)]
    pub groq_api_key: String,

    /// Screen capture interval in seconds
    #[serde(default = "default_capture_interval")]
    pub capture_interval_secs: u64,

    /// Whether screen capture is enabled
    #[serde(default)]
    pub screen_capture_enabled: bool,

    /// Whether OCR is enabled on captured screenshots
    #[serde(default = "default_true")]
    pub ocr_enabled: bool,

    /// How many recent screenshots to include when summarizing screen context
    #[serde(default = "default_screen_context_count")]
    pub screen_context_count: usize,

    /// Max chars to include from each OCR snippet when summarizing
    #[serde(default = "default_ocr_summary_max_chars")]
    pub ocr_summary_max_chars: usize,

    /// Whether screenshots should be sent through the auto-extraction pipeline.
    #[serde(default = "default_true")]
    pub screenshot_auto_extract_enabled: bool,

    /// Whether extracted screenshot summaries should be saved as memories.
    #[serde(default)]
    pub screenshot_auto_save_memory: bool,

    /// Whether extracted screenshot action items should be saved as tasks.
    #[serde(default)]
    pub screenshot_auto_save_action_items: bool,

    /// Whether system audio capture is enabled
    #[serde(default)]
    pub system_audio_enabled: bool,

    /// Whether mic capture is enabled
    #[serde(default = "default_true")]
    pub mic_enabled: bool,

    /// Enable speaker diarization (multi-speaker). Off by default — single speaker
    /// mode avoids Deepgram incorrectly splitting one voice into multiple speakers.
    #[serde(default)]
    pub diarize_speakers: bool,

    /// Firebase ID token (set after auth)
    #[serde(default)]
    pub firebase_id_token: String,

    /// Firebase refresh token
    #[serde(default)]
    pub firebase_refresh_token: String,

    /// User display name
    #[serde(default)]
    pub user_display_name: String,

    /// User email
    #[serde(default)]
    pub user_email: String,

    // ── Agent / M9 ────────────────────────────────────────────────────────────

    /// Whether the local Node.js agent runtime is enabled.
    #[serde(default)]
    pub agent_enabled: bool,

    /// Override path to the Node.js executable (empty = auto-detect).
    #[serde(default)]
    pub node_path: String,

    /// Override path to the agent dist/index.js script (empty = auto-detect).
    #[serde(default)]
    pub agent_script_path: String,

    /// Whether proactive suggestions are enabled.
    #[serde(default = "default_true")]
    pub proactive_agent_enabled: bool,

    /// How often (in minutes) the proactive engine polls for idle reminders.
    #[serde(default = "default_proactive_tick_mins")]
    pub proactive_tick_mins: u64,
}

fn default_backend_url() -> String {
    "http://localhost:10201".to_string()
}

fn default_python_backend_url() -> String {
    "http://localhost:8000".to_string()
}

fn default_capture_interval() -> u64 {
    5
}

fn default_true() -> bool {
    true
}

fn default_screen_context_count() -> usize { 5 }

fn default_ocr_summary_max_chars() -> usize { 800 }

fn default_openai_base_url() -> String {
    "https://api.openai.com/v1".to_string()
}

fn default_openai_model() -> String {
    "gpt-4o-mini".to_string()
}

fn default_proactive_tick_mins() -> u64 { 5 }

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            backend_url: default_backend_url(),
            python_backend_url: default_python_backend_url(),
            deepgram_api_key: String::new(),
            gemini_api_key: String::new(),
            openai_api_key: String::new(),
            openai_base_url: default_openai_base_url(),
            openai_model: default_openai_model(),
            groq_api_key: String::new(),
            capture_interval_secs: default_capture_interval(),
            screen_capture_enabled: false,
            ocr_enabled: true,
            screen_context_count: default_screen_context_count(),
            ocr_summary_max_chars: default_ocr_summary_max_chars(),
            screenshot_auto_extract_enabled: true,
            screenshot_auto_save_memory: false,
            screenshot_auto_save_action_items: false,
            system_audio_enabled: false,
            mic_enabled: true,
            diarize_speakers: false,
            firebase_id_token: String::new(),
            firebase_refresh_token: String::new(),
            user_display_name: String::new(),
            user_email: String::new(),
            agent_enabled: false,
            node_path: String::new(),
            agent_script_path: String::new(),
            proactive_agent_enabled: true,
            proactive_tick_mins: default_proactive_tick_mins(),
        }
    }
}

impl AppConfig {
    /// Path to the config file: %APPDATA%/omi/config.json
    pub fn config_path() -> PathBuf {
        let base = std::env::var("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| {
                dirs_fallback()
            });
        base.join(CONFIG_DIR).join(CONFIG_FILE)
    }

    /// Load config from disk, or return defaults if not found.
    pub fn load() -> Self {
        let path = Self::config_path();
        match std::fs::read_to_string(&path) {
            Ok(contents) => {
                serde_json::from_str(&contents).unwrap_or_else(|e| {
                    tracing::warn!("Failed to parse config at {}: {e}, using defaults", path.display());
                    Self::default()
                })
            }
            Err(_) => {
                tracing::info!("No config found at {}, using defaults", path.display());
                Self::default()
            }
        }
    }

    /// Save config to disk.
    pub fn save(&self) -> anyhow::Result<()> {
        let path = Self::config_path();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let json = serde_json::to_string_pretty(self)?;
        std::fs::write(&path, json)?;
        tracing::info!("Config saved to {}", path.display());
        Ok(())
    }

    /// Check if user is authenticated.
    pub fn is_authenticated(&self) -> bool {
        !self.firebase_id_token.is_empty()
    }

    /// Clear auth tokens (sign out).
    pub fn sign_out(&mut self) {
        self.firebase_id_token.clear();
        self.firebase_refresh_token.clear();
        self.user_display_name.clear();
        self.user_email.clear();
    }
}

/// Fallback config directory when %APPDATA% isn't set.
fn dirs_fallback() -> PathBuf {
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}
