package com.friend.ios.network

import com.friend.ios.core.AppConfiguration
import com.friend.ios.network.endpoints.AuthAPI
import com.friend.ios.network.endpoints.AuthEndpoints
import com.friend.ios.network.endpoints.ChatAPI
import com.friend.ios.network.endpoints.ChatEndpoints
import com.friend.ios.network.endpoints.MemoriesAPI
import com.friend.ios.network.endpoints.MemoriesEndpoints
// port-home
import com.friend.ios.network.endpoints.ConversationsAPI
import com.friend.ios.network.endpoints.ConversationsEndpoints
import com.friend.ios.network.endpoints.DiscoverAPI
import com.friend.ios.network.endpoints.DiscoverEndpoints
import com.friend.ios.network.endpoints.GoalsAPI
import com.friend.ios.network.endpoints.GoalsEndpoints
import com.friend.ios.network.endpoints.TasksAPI
import com.friend.ios.network.endpoints.TasksEndpoints
// Settings (port-settings)
import com.friend.ios.network.endpoints.AnnouncementsAPI
import com.friend.ios.network.endpoints.AppsAPI
import com.friend.ios.network.endpoints.AppsEndpoints
import com.friend.ios.network.endpoints.AnnouncementsEndpoints
import com.friend.ios.network.endpoints.PaymentsAPI
import com.friend.ios.network.endpoints.PaymentsEndpoints
import com.friend.ios.network.endpoints.ProfileAPI
import com.friend.ios.network.endpoints.ProfileEndpoints
import com.friend.ios.network.endpoints.SettingsAPI
import com.friend.ios.network.endpoints.SettingsEndpoints

/**
 * Port of `APIClient.swift`. Swift spreads one protocol over `APIClient+<Domain>.swift`
 * extensions; Kotlin can't add members from another file, so each domain is its own interface
 * (`endpoints/<Domain>.kt`) and the client delegates to it. Stores depend on
 * [APIClientProtocol], never on [APIClient], so they test against a fake.
 */
interface APIClientProtocol :
    AuthAPI,
    MemoriesAPI,
    // Chat (port-chat)
    ChatAPI,
    // port-home
    ConversationsAPI,
    TasksAPI,
    GoalsAPI,
    DiscoverAPI,
    // Settings (port-settings)
    SettingsAPI,
    PaymentsAPI,
    ProfileAPI,
    AnnouncementsAPI,
    AppsAPI,
    com.friend.ios.network.endpoints.DeveloperAPI,
    // Settings: Voices & people, Listening, Memory (port-settings A)
    com.friend.ios.network.endpoints.SpeakersAPI,
    com.friend.ios.network.endpoints.ImportsAPI,
    com.friend.ios.network.endpoints.KnowledgeGraphAPI,
    // Agent runs and recommendations (android-taskcard)
    com.friend.ios.network.endpoints.AgentAPI,
    // Memory review queue (and-onboarding)
    com.friend.ios.network.endpoints.MemoryReviewAPI,
    com.friend.ios.network.endpoints.SpeakerPromptsAPI,
    // Push token (and-onboarding system)
    com.friend.ios.network.endpoints.NotificationsAPI,
    // Onboarding voice sample (and-onboarding)
    com.friend.ios.network.endpoints.VoiceAPI,
    // The Omi wearable (and-device)
    com.friend.ios.network.endpoints.FirmwareAPI,
    com.friend.ios.network.endpoints.SyncAPI,
    com.friend.ios.network.endpoints.DeviceDiagnosticsAPI,
    // Capture (and-capture)
    com.friend.ios.network.endpoints.ListenAPI,
    // Conversations: detail, search, transcript labels, task extras (port-conversations)
    com.friend.ios.network.endpoints.ConversationExtrasAPI,
    com.friend.ios.network.endpoints.SearchAPI,
    com.friend.ios.network.endpoints.TranscriptLabelsAPI,
    com.friend.ios.network.endpoints.TaskExtrasAPI,
    // Phone calls (and-calls)
    com.friend.ios.network.endpoints.PhoneCallsAPI,
    // Ask Omi from the Omi, spoken answers (and-askomi)
    com.friend.ios.network.endpoints.VoiceMessagesAPI,
    // Health Connect, location, custom STT (and-transcribe)
    com.friend.ios.network.endpoints.HealthAPI,
    com.friend.ios.network.endpoints.LocationAPI,
    // Conversation content: editing the summary, folder drafts, capture gaps (and-w1-conversations)
    com.friend.ios.network.endpoints.ConversationContentAPI

class APIClient(http: HttpCore) :
    APIClientProtocol,
    AuthAPI by AuthEndpoints(http),
    MemoriesAPI by MemoriesEndpoints(http),
    // Chat (port-chat)
    ChatAPI by ChatEndpoints(http),
    // port-home
    ConversationsAPI by ConversationsEndpoints(http),
    TasksAPI by TasksEndpoints(http),
    GoalsAPI by GoalsEndpoints(http),
    DiscoverAPI by DiscoverEndpoints(http),
    // Settings (port-settings)
    SettingsAPI by SettingsEndpoints(http),
    PaymentsAPI by PaymentsEndpoints(http),
    ProfileAPI by ProfileEndpoints(http),
    AnnouncementsAPI by AnnouncementsEndpoints(http),
    AppsAPI by AppsEndpoints(http),
    com.friend.ios.network.endpoints.DeveloperAPI by com.friend.ios.network.endpoints.DeveloperEndpoints(http),
    // Settings: Voices & people, Listening, Memory (port-settings A)
    com.friend.ios.network.endpoints.SpeakersAPI by com.friend.ios.network.endpoints.SpeakersEndpoints(http),
    com.friend.ios.network.endpoints.ImportsAPI by com.friend.ios.network.endpoints.ImportsEndpoints(http),
    com.friend.ios.network.endpoints.KnowledgeGraphAPI by com.friend.ios.network.endpoints.ImportsEndpoints(http),
    // Agent runs and recommendations (android-taskcard)
    com.friend.ios.network.endpoints.AgentAPI by com.friend.ios.network.endpoints.AgentEndpoints(http),
    // Memory review queue (and-onboarding)
    com.friend.ios.network.endpoints.MemoryReviewAPI by com.friend.ios.network.endpoints.MemoryReviewEndpoints(http),
    com.friend.ios.network.endpoints.SpeakerPromptsAPI by com.friend.ios.network.endpoints.SpeakerPromptsEndpoints(http),
    // Push token (and-onboarding system)
    com.friend.ios.network.endpoints.NotificationsAPI by com.friend.ios.network.endpoints.NotificationsEndpoints(http),
    // Onboarding voice sample (and-onboarding)
    com.friend.ios.network.endpoints.VoiceAPI by com.friend.ios.network.endpoints.VoiceEndpoints(http),
    // The Omi wearable (and-device)
    com.friend.ios.network.endpoints.FirmwareAPI by com.friend.ios.network.endpoints.FirmwareEndpoints(http),
    com.friend.ios.network.endpoints.SyncAPI by com.friend.ios.network.endpoints.SyncEndpoints(http),
    com.friend.ios.network.endpoints.DeviceDiagnosticsAPI by com.friend.ios.network.endpoints.DeviceDiagnosticsEndpoints(http),
    // Capture (and-capture)
    com.friend.ios.network.endpoints.ListenAPI by com.friend.ios.network.endpoints.ListenEndpoints(http),
    // Conversations: detail, search, transcript labels, task extras (port-conversations)
    com.friend.ios.network.endpoints.ConversationExtrasAPI by com.friend.ios.network.endpoints.ConversationExtrasEndpoints(http),
    com.friend.ios.network.endpoints.SearchAPI by com.friend.ios.network.endpoints.SearchEndpoints(http),
    com.friend.ios.network.endpoints.TranscriptLabelsAPI by com.friend.ios.network.endpoints.TranscriptLabelsEndpoints(http),
    com.friend.ios.network.endpoints.TaskExtrasAPI by com.friend.ios.network.endpoints.TaskExtrasEndpoints(http),
    // Phone calls (and-calls)
    com.friend.ios.network.endpoints.PhoneCallsAPI by com.friend.ios.network.endpoints.PhoneCallsEndpoints(http),
    // Ask Omi from the Omi, spoken answers (and-askomi)
    com.friend.ios.network.endpoints.VoiceMessagesAPI by com.friend.ios.network.endpoints.VoiceMessagesEndpoints(http),
    // Health Connect, location, custom STT (and-transcribe)
    com.friend.ios.network.endpoints.HealthAPI by com.friend.ios.network.endpoints.HealthEndpoints(http),
    com.friend.ios.network.endpoints.LocationAPI by com.friend.ios.network.endpoints.LocationEndpoints(http),
    // Conversation content: editing the summary, folder drafts, capture gaps (and-w1-conversations)
    com.friend.ios.network.endpoints.ConversationContentAPI by com.friend.ios.network.endpoints.ConversationContentEndpoints(http) {
    constructor(configuration: AppConfiguration, tokens: AuthTokenProviding) : this(HttpCore(configuration, tokens))
}
