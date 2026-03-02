// User settings models - stored in Firestore user document
// Path: users/{uid}

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Daily summary notification settings
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct DailySummarySettings {
    /// Whether daily summary notifications are enabled
    #[serde(default = "default_daily_summary_enabled")]
    pub enabled: bool,
    /// Preferred hour in local timezone (0-23)
    #[serde(default = "default_daily_summary_hour")]
    pub hour: i32,
}

fn default_daily_summary_enabled() -> bool {
    true
}

fn default_daily_summary_hour() -> i32 {
    22 // 10 PM
}

/// Request to update daily summary settings
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateDailySummaryRequest {
    pub enabled: Option<bool>,
    pub hour: Option<i32>,
}

/// Transcription preferences
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TranscriptionPreferences {
    /// Whether to use single language mode (disables translation)
    #[serde(default)]
    pub single_language_mode: bool,
    /// Custom vocabulary words for better transcription accuracy
    #[serde(default)]
    pub vocabulary: Vec<String>,
}

/// Request to update transcription preferences
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateTranscriptionPreferencesRequest {
    pub single_language_mode: Option<bool>,
    pub vocabulary: Option<Vec<String>>,
}

/// User language preference
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserLanguage {
    /// Language code (e.g., "en", "es", "vi")
    pub language: String,
}

/// Request to update language
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateLanguageRequest {
    pub language: String,
}

/// Recording permission status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecordingPermission {
    /// Whether the user has granted permission to store recordings
    pub enabled: bool,
}

/// Private cloud sync settings
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrivateCloudSync {
    /// Whether private cloud sync is enabled
    #[serde(default = "default_private_cloud_sync")]
    pub enabled: bool,
}

fn default_private_cloud_sync() -> bool {
    true
}

/// Notification settings
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NotificationSettings {
    /// Global notifications toggle
    #[serde(default = "default_notifications_enabled")]
    pub enabled: bool,
    /// Notification frequency (0-5: Off, Minimal, Low, Balanced, High, Maximum)
    #[serde(default = "default_notification_frequency")]
    pub frequency: i32,
}

fn default_notifications_enabled() -> bool {
    true
}

fn default_notification_frequency() -> i32 {
    3 // Balanced
}

/// Request to update notification settings
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateNotificationSettingsRequest {
    pub enabled: Option<bool>,
    pub frequency: Option<i32>,
}

/// User profile from Firestore
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserProfile {
    /// User ID
    pub uid: String,
    /// User's email
    #[serde(default)]
    pub email: Option<String>,
    /// User's display name
    #[serde(default)]
    pub name: Option<String>,
    /// User's timezone
    #[serde(default)]
    pub time_zone: Option<String>,
    /// When the user was created
    #[serde(default)]
    pub created_at: Option<String>,
    /// Onboarding: user's motivation for using OMI
    #[serde(default)]
    pub motivation: Option<String>,
    /// Onboarding: user's primary use case
    #[serde(default)]
    pub use_case: Option<String>,
    /// Onboarding: user's job title
    #[serde(default)]
    pub job: Option<String>,
    /// Onboarding: user's company
    #[serde(default)]
    pub company: Option<String>,
    /// Desktop Sparkle update channel (staging, beta, stable)
    #[serde(default)]
    pub desktop_update_channel: Option<String>,
}

/// Complete user settings response (aggregated)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserSettingsResponse {
    pub daily_summary: DailySummarySettings,
    pub transcription: TranscriptionPreferences,
    pub language: String,
    pub recording_permission: bool,
    pub private_cloud_sync: bool,
    pub notifications: NotificationSettings,
}

/// Generic status response
#[derive(Debug, Clone, Serialize)]
pub struct UserSettingsStatusResponse {
    pub status: String,
}

/// AI-generated profile of the user (distinct from PersonaDB which is user-created AI characters)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AIUserProfile {
    pub profile_text: String,
    pub generated_at: DateTime<Utc>,
    pub data_sources_used: i32,
}

/// Request to update AI-generated user profile
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateAIUserProfileRequest {
    pub profile_text: String,
    pub generated_at: String,
    pub data_sources_used: i32,
}

/// Request to update user profile (onboarding data)
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateUserProfileRequest {
    pub name: Option<String>,
    pub motivation: Option<String>,
    pub use_case: Option<String>,
    pub job: Option<String>,
    pub company: Option<String>,
}

// MARK: - Assistant Settings (synced to Firestore)

/// Shared assistant settings
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SharedAssistantSettingsData {
    pub cooldown_interval: Option<i32>,
    pub glow_overlay_enabled: Option<bool>,
    pub analysis_delay: Option<i32>,
    pub screen_analysis_enabled: Option<bool>,
}

/// Focus assistant settings
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct FocusSettingsData {
    pub enabled: Option<bool>,
    pub analysis_prompt: Option<String>,
    pub cooldown_interval: Option<i32>,
    pub notifications_enabled: Option<bool>,
    pub excluded_apps: Option<Vec<String>>,
}

/// Task extraction assistant settings
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TaskSettingsData {
    pub enabled: Option<bool>,
    pub analysis_prompt: Option<String>,
    pub extraction_interval: Option<f64>,
    pub min_confidence: Option<f64>,
    pub notifications_enabled: Option<bool>,
    pub allowed_apps: Option<Vec<String>>,
    pub browser_keywords: Option<Vec<String>>,
}

/// Advice assistant settings
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AdviceSettingsData {
    pub enabled: Option<bool>,
    pub analysis_prompt: Option<String>,
    pub extraction_interval: Option<f64>,
    pub min_confidence: Option<f64>,
    pub notifications_enabled: Option<bool>,
    pub excluded_apps: Option<Vec<String>>,
}

/// Memory extraction assistant settings
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MemorySettingsData {
    pub enabled: Option<bool>,
    pub analysis_prompt: Option<String>,
    pub extraction_interval: Option<f64>,
    pub min_confidence: Option<f64>,
    pub notifications_enabled: Option<bool>,
    pub excluded_apps: Option<Vec<String>>,
}

/// All assistant settings (response and request — all fields optional for partial updates)
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AssistantSettingsData {
    pub shared: Option<SharedAssistantSettingsData>,
    pub focus: Option<FocusSettingsData>,
    pub task: Option<TaskSettingsData>,
    pub advice: Option<AdviceSettingsData>,
    pub memory: Option<MemorySettingsData>,
    /// Remote override for the Sparkle update channel (top-level field on user doc, not in assistant_settings sub-map)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub update_channel: Option<String>,
}
