import OmiDesign
import SwiftUI

/// One searchable setting (Flutter `settings_search_index`): what it is called and the screen
/// that holds it.
struct SettingsSearchEntry: Identifiable, Hashable {
    let title: String
    let topic: SettingsTopic
    var id: String { "\(topic.rawValue).\(title)" }

    /// Every setting by the name it shows under, in the screen that holds it.
    static var all: [SettingsSearchEntry] {
        let titles: [(SettingsTopic, [String])] = [
            (.account, [
                L("account"), L("profile"), L("name"), L("email"), L("nativeRedoOnboarding"), L("nativeSignOut"),
                L("nativeDeleteAccount"),
            ]),
            (.planUsage, [
                L("nativeSettingsPlanUsage"), L("nativePlan"), L("upgrade"), L("managePlan"), L("cancelSubscription"),
                L("nativeUsage"), L("nativeSettingsActivity"), L("fairUsePolicy"),
            ]),
            (.referral, [L("nativeSettingsInviteFriends"), L("referralProgram"), L("nativeYourInviteLink")]),
            (.devices, [L("nativeSettingsMyOmi"), L("nativeMyDevices")]),
            (.listening, [
                L("nativeSettingsListening"), L("language"), L("nativeSpokenLanguage"), L("nativeDetectLanguages"),
                L("nativeSettingsVocabulary"), L("nativeCustomVocabulary"), L("nativeSettingsEndsAfter"),
                L("conversationTimeout"), L("nativeSettingsAdvanced"), L("nativeSpeechModel"), L("nativeOnDeviceTranscription"),
                L("nativeTranscribeLater"), L("nativeTranscriptionLog"), L("nativeRecordingsOnPhone"),
            ]),
            (.voices, [
                L("nativeSettingsVoices"), L("people"), L("nativeRecordYourVoiceAgain"),
                L("nativeSettingsAskWhoSpoke"), L("nativeSettingsRememberVoices"), L("nativeSettingsIgnoredVoices"),
                L("nativeSettingsCleanUp"),
            ]),
            (.memory, [
                L("nativeSettingsMemory"), L("nativeWhatIKnowAboutYou"), L("memories"), L("memoryGraph"),
                L("nativeSettingsImportHistory"), L("importData"), L("nativeDeleteAllMemories"),
            ]),
            (.assistant, [
                L("nativeAssistant"), L("nativeSpokenReplies"), L("nativeAssistantVoice"),
                L("nativeProactiveNotifications"), L("notificationFrequency"), L("nativeDailyRecap"), L("nativeDailySummary"),
            ]),
            (.apps, [
                L("nativeSettingsApps"), L("nativeCapabilities"), L("nativeAppsKindIntegrations"), "Google Calendar", "Gmail",
                "Todoist", "Asana", "ClickUp", "Google Tasks", "Apple Health", L("nativeRemindersName"),
                L("nativeSettingsInstalledApps"),
            ]),
            (.browseApps, [L("nativeBrowseApps"), L("nativeOmiApps")]),
            (.connectAI, [L("nativeConnectAI"), "Claude", "ChatGPT", "MCP"]),
            (.phoneCalls, [L("nativeSettingsPhoneCalls")]),
            (.appearance, [
                L("appearance"), L("nativeAppearanceSystem"), L("nativeAppearanceLight"), L("nativeAppearanceDark"),
                L("nativeAppLanguage"),
            ]),
            (.notifications, [L("notifications"), L("nativeNotificationsAllow")]),
            (.privacy, [
                L("nativeSettingsPrivacy"), L("dataAndPrivacy"), L("nativeStoreRecordings"), L("nativeSettingsAudioOnPhone"),
                L("location"), L("nativePermissions"), L("nativeSettingsAppAccess"), L("exportAllData"), L("privacyPolicy"),
            ]),
            (.help, [
                L("nativeSettingsHelp"), L("helpCenter"), L("whatsNew"), L("nativeSendFeedback"), L("nativeReplayIntroduction"),
                L("nativeDeveloperMode"),
            ]),
        ]
        return titles.flatMap { topic, names in names.map { SettingsSearchEntry(title: $0, topic: topic) } }
    }

    /// Case- and accent-insensitive match on the setting's name (a screen's own name is one of its
    /// entries); one row per name and screen.
    static func matching(_ query: String) -> [SettingsSearchEntry] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !needle.isEmpty else { return [] }
        var seen = Set<String>()
        return all.filter { entry in
            entry.title.localizedStandardContains(needle) && seen.insert(entry.id).inserted
        }
    }
}

/// The results list under the Settings search field; picking one opens its screen.
struct SettingsSearchResults: View {
    let query: String
    let onOpen: (SettingsTopic) -> Void

    var body: some View {
        let results = SettingsSearchEntry.matching(query)
        if results.isEmpty {
            ContentUnavailableView.search(text: query)
        } else {
            ForEach(results) { entry in
                Button {
                    DSHaptics.selection()
                    onOpen(entry.topic)
                } label: {
                    HStack(spacing: DS.Spacing.md) {
                        Image(systemName: entry.topic.systemImage)
                            .foregroundStyle(DS.Palette.inkSecondary)
                            .frame(width: 28)
                        VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                            Text(entry.title).foregroundStyle(DS.Palette.ink)
                            Text(entry.topic.title).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                        }
                    }
                }
                .accessibilityIdentifier("settings.search.\(entry.topic.rawValue)")
            }
        }
    }
}
