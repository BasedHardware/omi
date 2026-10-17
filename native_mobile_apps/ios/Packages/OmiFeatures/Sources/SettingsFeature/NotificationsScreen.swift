import OmiComponents
import OmiDesign
import OmiService
import SwiftUI
import UserNotifications

/// App › Notifications: whether iOS lets Omi notify you, and what Omi notifies about. The daily
/// recap and tips are chosen in Assistant (one place); this screen links there.
struct NotificationsScreen: View {
    @Environment(SettingsStore.self) private var settings
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var scenePhase
    @State private var status: UNAuthorizationStatus?

    var body: some View {
        SettingsList {
            Section {
                permissionRow
            } footer: {
                if status == .denied { Text(L("nativeNotificationsDeniedFooter")) }
            }
            Section {
                NavigationLink(value: SettingsTopic.assistant) {
                    SettingsRowLabel(
                        title: L("nativeDailyRecap"), systemImage: "sun.horizon",
                        value: settings.dailySummaryEnabled ? AssistantScreen.hourLabel(settings.dailySummaryHour) : L("off")
                    )
                }
                NavigationLink(value: SettingsTopic.assistant) {
                    SettingsRowLabel(
                        title: L("nativeProactiveNotifications"), systemImage: "lightbulb",
                        value: AssistantScreen.frequencyTitle(settings.notificationFrequency)
                    )
                }
            } header: {
                SettingsHeader(L("nativeNotificationsWhat"))
            } footer: {
                Text(L("nativeNotificationsAlsoFooter"))
            }
        }
        .omiPage(L("notifications"))
        .task { await settings.loadNotifications() }
        .task(id: scenePhase) { await refreshStatus() }
    }

    @ViewBuilder
    private var permissionRow: some View {
        HStack {
            SettingsRowLabel(title: L("nativeNotificationsAllow"), systemImage: "bell.badge")
            Spacer()
            switch status {
            case .notDetermined?:
                Button(L("nativeAllow")) {
                    Task {
                        _ = try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound])
                        await refreshStatus()
                    }
                }
                .buttonStyle(.omiPill)
                .accessibilityIdentifier("notifications.allow")
            case .denied?:
                Button(L("openSettings")) {
                    if let url = URL(string: UIApplication.openNotificationSettingsURLString) { openURL(url) }
                }
                .buttonStyle(.omiPill)
                .accessibilityIdentifier("notifications.openSettings")
            case nil:
                ProgressView()
            default:
                Text(L("nativeOn")).foregroundStyle(DS.Palette.inkSecondary)
            }
        }
    }

    private func refreshStatus() async {
        status = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }
}
