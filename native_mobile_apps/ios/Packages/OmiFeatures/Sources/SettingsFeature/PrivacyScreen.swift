import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// App › Privacy & data: what is kept (audio in the cloud, on this iPhone), location and iOS
/// permissions, which apps see what, and exporting everything. Importing history and deleting all
/// memories live in Memory.
struct PrivacyScreen: View {
    @Environment(SettingsStore.self) private var settings
    @Environment(LocationStore.self) private var location
    @Environment(\.openURL) private var openURL
    @State private var profile: ProfileStore?
    @State private var confirmAudioOnPhone = false

    var body: some View {
        SettingsList {
            Section {
                Toggle(isOn: Binding(
                    get: { settings.storesRecordings },
                    set: { value in Task { await settings.setStoresRecordings(value) } }
                )) {
                    SettingsRowLabel(title: L("nativeStoreRecordings"), systemImage: "icloud")
                }
                if let profile {
                    Toggle(isOn: Binding(
                        get: { profile.storesAudioOnPhone },
                        set: { value in
                            if value { confirmAudioOnPhone = true } else { profile.storesAudioOnPhone = false }
                        }
                    )) {
                        SettingsRowLabel(title: L("nativeSettingsAudioOnPhone"), systemImage: "iphone")
                    }
                    .accessibilityIdentifier("privacy.audioOnPhone")
                }
            } footer: {
                Text(L("nativeStoreRecordingsFooter"))
            }
            Section {
                locationRow
                Button {
                    if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                } label: {
                    HStack {
                        SettingsRowLabel(title: L("nativePermissions"), systemImage: "checkmark.shield")
                        Spacer()
                        Image(systemName: "arrow.up.right").font(.footnote.weight(.semibold)).foregroundStyle(DS.Palette.inkTertiary)
                    }
                }
            } footer: {
                Text(L("locationAccessDesc"))
            }
            if let profile {
                Section {
                    NavigationLink {
                        AppAccessScreen(profile: profile)
                    } label: {
                        SettingsRowLabel(
                            title: L("nativeSettingsAppAccess"), systemImage: "square.grid.2x2",
                            value: profile.appsWithAccess.map { String($0.count) }
                        )
                    }
                    .accessibilityIdentifier("privacy.appAccess")
                    ExportDataRow(store: profile)
                }
            }
            Section {
                Link(L("privacyPolicy"), destination: URL(string: "https://www.omi.me/pages/privacy")!)
                Link(L("termsOfService"), destination: URL(string: "https://www.omi.me/pages/terms-of-service")!)
            }
            .tint(DS.Palette.ink)
        }
        .omiPage(L("nativeSettingsPrivacy"))
        .task { await settings.loadPrivacy() }
        .task {
            let store = profile ?? settings.makeProfileStore()
            profile = store
            await store.loadAppsWithAccess()
        }
        .onAppear { location.refresh() }
        .alert(L("privacyNotice"), isPresented: $confirmAudioOnPhone) {
            Button(L("cancel"), role: .cancel) {}
            Button(L("nativeKeepOnPhone")) { profile?.storesAudioOnPhone = true }
        } message: {
            Text(L("nativeRecordingsMayCaptureOthers"))
        }
    }

    /// Where conversations happen (When In Use). Never asked: the system prompt; denied: the Settings app.
    private var locationRow: some View {
        HStack {
            SettingsRowLabel(title: L("location"), systemImage: "location")
            Spacer()
            switch location.access {
            case .notDetermined:
                Button(L("nativeAllow")) { Task { await location.requestAccess() } }
                    .buttonStyle(.omiPill)
                    .accessibilityIdentifier("privacy.location.allow")
            case .allowed, .denied:
                Button(location.access == .allowed ? L("nativeLocationOn") : L("nativeLocationOff")) {
                    if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                }
                .foregroundStyle(DS.Palette.inkSecondary)
                .accessibilityIdentifier("privacy.location.status")
            }
        }
    }

    /// "Conversations, memories · when a conversation is created" (Flutter's access line).
    static func accessSummary(_ app: AppDataAccess) -> String {
        let reads = [app.readsConversations ? L("conversations") : nil, app.readsMemories ? L("memories") : nil].compactMap(\.self)
        let trigger: String? = switch app.trigger {
        case "memory_creation": L("nativeTriggerConversationCreated")
        case "transcript_processed": L("nativeTriggerTranscript")
        case "audio_bytes": L("nativeTriggerAudio")
        default: nil
        }
        let parts = [reads.isEmpty ? nil : reads.joined(separator: ", "), trigger].compactMap(\.self)
        return parts.isEmpty ? L("nativeNoSpecificAccess") : parts.joined(separator: " · ")
    }
}

/// Privacy & data › Which apps see what: installed apps that read your conversations or memories,
/// and when they run.
private struct AppAccessScreen: View {
    let profile: ProfileStore

    var body: some View {
        SettingsList {
            Section {
                if let apps = profile.appsWithAccess {
                    if apps.isEmpty {
                        Text(L("nativeNoAppsAccessData")).foregroundStyle(DS.Palette.inkSecondary)
                    }
                    ForEach(apps) { app in
                        HStack(spacing: DS.Spacing.md) {
                            AppIcon(url: app.imageURL, name: app.name, size: 32)
                            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                                Text(app.name)
                                Text(PrivacyScreen.accessSummary(app)).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                            }
                        }
                    }
                } else {
                    ProgressView().frame(maxWidth: .infinity)
                }
            } footer: {
                Text(L("nativeAppAccessFooter"))
            }
        }
        .omiPage(L("nativeSettingsAppAccess"))
        .task { await profile.loadAppsWithAccess() }
    }
}

/// Export all data: downloads one JSON file with everything Omi stores, then the share sheet.
struct ExportDataRow: View {
    let store: ProfileStore

    var body: some View {
        switch store.exportPhase {
        case .idle, .failed:
            Button {
                store.export()
            } label: {
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    SettingsRowLabel(title: L("nativeSettingsExport"), systemImage: "square.and.arrow.up")
                    if store.exportPhase == .failed {
                        Text(L("exportFailedTryAgain")).font(DS.Typography.caption).foregroundStyle(DS.Palette.live)
                    }
                }
            }
            .accessibilityIdentifier("privacy.export")
        case .exporting:
            HStack {
                ProgressView()
                Text(L("exportingAllData")).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                Spacer()
                Button(L("cancel")) { store.cancelExport() }
            }
        case let .ready(url):
            ShareLink(item: url) {
                SettingsRowLabel(title: L("nativeShareExport"), systemImage: "square.and.arrow.up", tint: DS.Palette.agent)
            }
                // The temporary file goes once the row does (leaving Data & Privacy).
                .onDisappear { store.finishExport() }
        }
    }
}
