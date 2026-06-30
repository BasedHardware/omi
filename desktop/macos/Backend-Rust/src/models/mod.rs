// Models module

pub mod action_item;
pub mod advice;
pub mod agent;
pub mod app;
pub mod category;
pub mod chat_completions;
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
pub mod screen_activity;
pub mod user_settings;

pub use action_item::ActionItemDB;
pub use advice::{AdviceCategory, AdviceDB};
pub use app::{App, AppReview, AppSummary, TriggerEvent};
pub use category::{Category, MemoryCategory};
pub use chat_session::ChatSessionDB;
pub use conversation::{
    ActionItem, AppResult, Conversation, ConversationPhoto, Event, Geolocation, Structured,
    TranscriptSegment,
};
pub use focus_session::{DistractionEntry, FocusSessionDB, FocusStats, FocusStatus};
pub use folder::Folder;
pub use goal::{GoalDB, GoalHistoryEntry, GoalType};
pub use knowledge_graph::{KnowledgeGraphEdge, KnowledgeGraphNode, NodeType};
pub use memory::{Memory, MemoryDB};
pub use message::MessageDB;
pub use person::Person;
pub use persona::PersonaDB;
pub use user_settings::{
    AIUserProfile, AdviceSettingsData, AssistantSettingsData, DailySummarySettings,
    FloatingBarSettingsData, FocusSettingsData, MemorySettingsData, NotificationSettings,
    SharedAssistantSettingsData, TaskSettingsData, TranscriptionPreferences, UserProfile,
};
