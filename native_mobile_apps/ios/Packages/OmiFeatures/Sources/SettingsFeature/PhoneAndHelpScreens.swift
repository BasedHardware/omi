import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

// Phone Calls moved to PhoneCallsScreen.swift (the whole phone surface).

/// Help: the help center, feedback, what's new, replaying the introduction, and developer mode.
struct HelpScreen: View {
    @Environment(SettingsStore.self) private var settings
    @Environment(DeveloperStore.self) private var developer
    /// Closes Settings and shows the short introduction to the app again.
    let onReplayIntroduction: () -> Void

    var body: some View {
        @Bindable var developer = developer
        SettingsList {
            Section {
                Link(destination: URL(string: "https://help.omi.me/\(Self.helpLanguage)/")!) {
                    linkRow(L("helpCenter"), systemImage: "book")
                }
                Link(destination: URL(string: "https://feedback.omi.me/")!) {
                    linkRow(L("nativeSendFeedback"), systemImage: "bubble.left")
                }
                SupportChatRow() // Intercom support chat, only when configured
                NavigationLink { WhatsNewScreen(store: settings.makeAnnouncementsStore()) } label: {
                    SettingsRowLabel(title: L("whatsNew"), systemImage: "gift")
                }
                .accessibilityIdentifier("help.whatsNew")
            }
            Section {
                Button(action: onReplayIntroduction) {
                    SettingsRowLabel(title: L("nativeReplayIntroduction"), systemImage: "play.rectangle")
                }
                .accessibilityIdentifier("settings.replayIntroduction")
            }
            Section {
                Toggle(isOn: $developer.isDeveloperMode) {
                    SettingsRowLabel(title: L("nativeDeveloperMode"), systemImage: "chevron.left.forwardslash.chevron.right")
                }
                .accessibilityIdentifier("help.developerMode")
            } footer: {
                Text(L("nativeDeveloperModeFooter"))
            }
        }
        .omiPage(L("nativeSettingsHelp"))
    }

    private func linkRow(_ title: String, systemImage: String) -> some View {
        HStack {
            SettingsRowLabel(title: title, systemImage: systemImage)
            Spacer()
            Image(systemName: "arrow.up.right").font(.footnote.weight(.semibold)).foregroundStyle(DS.Palette.inkTertiary)
        }
    }

    /// Help center languages (Flutter `settings_destinations.dart`), English otherwise.
    static var helpLanguage: String {
        let supported = ["en", "de", "es", "fr", "it", "pt", "ja", "ko", "zh", "nl", "pl", "ru", "tr"]
        let code = Locale.current.language.languageCode?.identifier ?? "en"
        return supported.contains(code) ? code : "en"
    }
}
