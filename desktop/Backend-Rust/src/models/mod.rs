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
pub mod persona;
pub mod request;
pub mod user_settings;

pub use action_item::{AcceptTasksRequest, AcceptTasksResponse, ActionItemDB, ActionItemsListResponse, ActionItemStatusResponse, BatchCreateActionItemsRequest, BatchUpdateScoresRequest, CreateActionItemRequest, PromoteResponse, ShareTasksRequest, ShareTasksResponse, SharedTaskInfo, SharedTasksResponse, UpdateActionItemRequest};
pub use advice::{AdviceCategory, AdviceDB, AdviceStatusResponse, CreateAdviceRequest, GetAdviceQuery, UpdateAdviceRequest};
pub use app::{
    App, AppCapabilityDef, AppCategory, AppGroup, AppReview, AppSummary, AppsV2Meta, AppsV2Query,
    AppsV2Response, CapabilityInfo, ListAppsQuery, PaginationMeta, SearchAppsQuery,
    SubmitReviewRequest, ToggleAppRequest, ToggleAppResponse, TriggerEvent, get_app_capabilities,
    get_app_categories, get_v2_capabilities,
};
pub use category::{Category, MemoryCategory};
pub use conversation::{
    ActionItem, AppResult, Conversation, ConversationPhoto, ConversationSource, ConversationStatus,
    Event, Geolocation, Structured, TranscriptSegment,
};
pub use folder::{
    BulkMoveRequest, BulkMoveResponse, CreateFolderRequest, DeleteFolderQuery, Folder,
    MoveToFolderRequest, ReorderFoldersRequest, UpdateFolderRequest,
};
pub use memory::{
    CreateMemoryRequest, CreateMemoryResponse, EditMemoryRequest, GetMemoriesQuery, Memory,
    MemoryDB, MemoryStatusResponse, ReviewMemoryRequest, UpdateMemoryReadRequest,
    UpdateVisibilityRequest,
};
pub use message::{
    DeleteMessagesQuery, GetMessagesQuery, MessageDB, MessageStatusResponse, RateMessageRequest,
    SaveMessageRequest, SaveMessageResponse,
};
pub use request::{CreateConversationRequest, CreateConversationResponse};
pub use focus_session::{
    CreateFocusSessionRequest, DistractionEntry, FocusSessionDB, FocusSessionStatusResponse,
    FocusStats, FocusStatus, GetFocusSessionsQuery, GetFocusStatsQuery,
};
pub use user_settings::{
    DailySummarySettings, NotificationSettings, PrivateCloudSync, RecordingPermission,
    AIUserProfile, TranscriptionPreferences, UpdateAIUserProfileRequest, UpdateDailySummaryRequest,
    UpdateLanguageRequest, UpdateNotificationSettingsRequest, UpdateTranscriptionPreferencesRequest,
    UpdateUserProfileRequest, UserLanguage, UserProfile, UserSettingsStatusResponse,
    AssistantSettingsData, SharedAssistantSettingsData, FocusSettingsData, TaskSettingsData,
    AdviceSettingsData, MemorySettingsData,
};
pub use chat_session::{
    ChatSessionDB, ChatSessionStatusResponse, CreateChatSessionRequest, GetChatSessionsQuery,
    UpdateChatSessionRequest,
};
pub use goal::{
    CreateGoalRequest, DailyScore, DailyScoreQuery, GoalDB, GoalHistoryEntry, GoalHistoryQuery,
    GoalHistoryResponse, GoalStatusResponse, GoalType, GoalsListResponse, ScoreData, ScoreResponse,
    UpdateGoalProgressQuery, UpdateGoalRequest,
};
pub use persona::{
    CheckUsernameQuery, CreatePersonaRequest, GeneratePromptRequest, GeneratePromptResponse,
    PersonaDB, PersonaResponse, PersonaStatusResponse, UpdatePersonaRequest,
    UsernameAvailableResponse,
};
pub use knowledge_graph::{
    ExtractedKnowledge, KnowledgeGraphEdge,
    KnowledgeGraphNode, KnowledgeGraphResponse, KnowledgeGraphStatusResponse, NodeType,
    RebuildGraphResponse,
};
