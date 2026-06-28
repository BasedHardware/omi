// Models module

pub mod action_item;
pub mod advice;
pub mod agent;
pub mod app;
pub mod category;
pub mod chat_session;
pub mod conversation;
pub mod focus_session;
pub mod folder;
pub mod goal;
pub mod knowledge_graph;
pub mod memory;
pub mod message;
pub mod person;
pub mod persona;
pub mod chat_completions;
pub mod screen_activity;
pub mod user_settings;

pub use action_item::ActionItemDB;
pub use advice::{AdviceCategory, AdviceDB};
pub use app::{App, AppReview, AppSummary, TriggerEvent};
pub use category::{Category, MemoryCategory};
pub use conversation::{
    ActionItem, AppResult, Conversation, ConversationPhoto,
    Event, Geolocation, Structured, TranscriptSegment,
};
pub use folder::Folder;
pub use memory::{Memory, MemoryDB};
pub use message::MessageDB;
pub use focus_session::{DistractionEntry, FocusSessionDB, FocusStats, FocusStatus};
pub use user_settings::{
    DailySummarySettings, NotificationSettings, AIUserProfile, TranscriptionPreferences,
    UserProfile, AssistantSettingsData, SharedAssistantSettingsData, FocusSettingsData,
    TaskSettingsData, AdviceSettingsData, MemorySettingsData, FloatingBarSettingsData,
};
pub use chat_session::ChatSessionDB;
pub use goal::{GoalDB, GoalHistoryEntry, GoalType};
pub use person::Person;
pub use persona::PersonaDB;
pub use knowledge_graph::{KnowledgeGraphEdge, KnowledgeGraphNode, NodeType};
