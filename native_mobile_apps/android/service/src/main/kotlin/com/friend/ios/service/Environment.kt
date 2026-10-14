package com.friend.ios.service

import androidx.compose.runtime.staticCompositionLocalOf
import com.friend.ios.persistence.Preferences
import com.friend.ios.service.stores.MemoriesStore

/**
 * The `.environment(store)` injections of `OmiApp.swift`: one CompositionLocal per store, provided
 * once by the app's `AppEnvironment`. `@Environment(MemoriesStore.self) var store` becomes
 * `val store = LocalMemoriesStore.current`.
 */
val LocalPreferences = staticCompositionLocalOf<Preferences> { error("Preferences not provided") }
val LocalMemoriesStore = staticCompositionLocalOf<MemoriesStore> { error("MemoriesStore not provided") }
val LocalSessionStore = staticCompositionLocalOf<com.friend.ios.service.stores.SessionStore> { error("SessionStore not provided") }

// Chat (port-chat)
val LocalChatStore = staticCompositionLocalOf<com.friend.ios.service.stores.ChatStore> { error("ChatStore not provided") }
val LocalAgentStore = staticCompositionLocalOf<com.friend.ios.service.stores.AgentStore> { error("AgentStore not provided") }
// port-home
val LocalConversationsStore = staticCompositionLocalOf<com.friend.ios.service.stores.ConversationsStore> { error("ConversationsStore not provided") }
val LocalTasksStore = staticCompositionLocalOf<com.friend.ios.service.stores.TasksStore> { error("TasksStore not provided") }
val LocalGoalsStore = staticCompositionLocalOf<com.friend.ios.service.stores.GoalsStore> { error("GoalsStore not provided") }
// Settings (port-settings)
val LocalSettingsStore = staticCompositionLocalOf<com.friend.ios.service.stores.SettingsStore> { error("SettingsStore not provided") }
val LocalDeveloperStore = staticCompositionLocalOf<com.friend.ios.service.stores.DeveloperStore> { error("DeveloperStore not provided") }
// Settings: Voices & people (port-settings A)
val LocalVoicesStore = staticCompositionLocalOf<com.friend.ios.service.stores.VoicesStore> { error("VoicesStore not provided") }
// Settings > Apps (port-settings fork B)
val LocalCapabilitiesStore = staticCompositionLocalOf<com.friend.ios.service.stores.CapabilitiesStore> { error("CapabilitiesStore not provided") }
val LocalAppCatalogStore = staticCompositionLocalOf<com.friend.ios.service.stores.AppCatalogStore> { error("AppCatalogStore not provided") }
// Chat dictation (and-onboarding): iOS passes `AppEnvironment.dictation` to ChatScreen; null hides the mic.
val LocalDictation = staticCompositionLocalOf<com.friend.ios.service.stores.VoiceIntroStore?> { null }
// The Omi wearable (and-device)
val LocalDeviceStore = staticCompositionLocalOf<com.friend.ios.service.stores.DeviceStore> { error("DeviceStore not provided") }
val LocalFirmwareStore = staticCompositionLocalOf<com.friend.ios.service.stores.FirmwareStore> { error("FirmwareStore not provided") }
val LocalSyncStore = staticCompositionLocalOf<com.friend.ios.service.stores.SyncStore> { error("SyncStore not provided") }
val LocalButtonTutorialStore = staticCompositionLocalOf<com.friend.ios.service.stores.ButtonTutorialStore> { error("ButtonTutorialStore not provided") }
val LocalDiagnosticsReportStore = staticCompositionLocalOf<com.friend.ios.service.stores.DiagnosticsReportStore> { error("DiagnosticsReportStore not provided") }
// Capture (and-capture)
val LocalCaptureStore = staticCompositionLocalOf<com.friend.ios.service.stores.CaptureStore> { error("CaptureStore not provided") }
val LocalLiveSpeakersStore = staticCompositionLocalOf<com.friend.ios.service.stores.LiveSpeakersStore> { error("LiveSpeakersStore not provided") }
// The watch (and-wear)
val LocalWatchStore = staticCompositionLocalOf<com.friend.ios.service.watch.WatchStore?> { null }
// Phone calls (and-calls)
val LocalPhoneCallStore = staticCompositionLocalOf<com.friend.ios.service.stores.PhoneCallStore> { error("PhoneCallStore not provided") }
// Ask Omi, spoken answers, read aloud (and-askomi). Null: nothing is read aloud (previews).
val LocalVoicePlaybackStore = staticCompositionLocalOf<com.friend.ios.service.stores.VoicePlaybackStore?> { null }
val LocalAskOmiStore = staticCompositionLocalOf<com.friend.ios.service.stores.AskOmiStore?> { null }
// Health Connect, location (and-transcribe)
val LocalAppleHealthStore = staticCompositionLocalOf<com.friend.ios.service.stores.AppleHealthStore> { error("AppleHealthStore not provided") }
val LocalLocationStore = staticCompositionLocalOf<com.friend.ios.service.stores.LocationStore> { error("LocationStore not provided") }
val LocalCustomSTTSettings = staticCompositionLocalOf<com.friend.ios.service.customstt.CustomSTTSettings> { error("CustomSTTSettings not provided") }
