import AuthenticationServices
import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Connections › Apps & integrations: what is connected (calendar, mail, task apps, Apple Health,
/// Reminders), what can be added, the Omi apps you installed, and the app store.
struct CapabilitiesScreen: View {
    @Environment(CapabilitiesStore.self) private var store
    @Environment(AppleHealthStore.self) private var health
    @Environment(RemindersSyncStore.self) private var reminders

    var body: some View {
        let connected = store.integrations.filter(\.isConnected)
        let available = store.integrations.filter { !$0.isConnected }
        SettingsList {
            if !connected.isEmpty || health.isConnected || reminders.isEnabled {
                Section(L("nativeConnected")) {
                    ForEach(connected) { IntegrationRow(integration: $0) }
                    if health.isAvailable, health.isConnected { healthRow }
                    if reminders.isEnabled { RemindersRow() }
                }
            }
            if !available.isEmpty || (health.isAvailable && !health.isConnected) || !reminders.isEnabled {
                Section {
                    ForEach(available) { IntegrationRow(integration: $0) }
                    if health.isAvailable, !health.isConnected { healthRow }
                    if !reminders.isEnabled { RemindersRow() }
                } header: {
                    SettingsHeader(L("nativeSettingsAddIntegration"))
                } footer: {
                    Text(L("nativeCapabilitiesOnboardingReason"))
                }
            }
            if !store.installedApps.isEmpty {
                Section(L("nativeSettingsInstalledApps")) {
                    ForEach(store.installedApps) { AppRow(app: $0) }
                }
            }
            Section {
                NavigationLink(value: SettingsTopic.browseApps) {
                    SettingsRowLabel(title: L("nativeBrowseApps"), systemImage: "sparkle.magnifyingglass")
                }
                .accessibilityIdentifier("apps.browse")
            } footer: {
                Text(L("nativeOmiAppsFooter"))
            }
        }
        .omiPage(L("nativeSettingsApps"))
        .task { await store.load() }
        .task { await store.loadApps() }
        .task { await health.load() }
        .task { await reminders.refresh() }
        .alert(L("appleHealthDeniedTitle"), isPresented: Binding(
            get: { health.notice == .denied }, set: { if !$0 { health.notice = nil } }
        )) {
            Button(L("ok"), role: .cancel) {}
        } message: {
            Text(L("appleHealthDeniedBody"))
        }
    }

    /// Connected: opens its page (sync, disconnect). Not yet: Connect asks iOS right here.
    @ViewBuilder
    private var healthRow: some View {
        let label = HStack(spacing: DS.Spacing.md) {
            AppleHealthIcon(size: 28)
            Text("Apple Health")
        }
        if health.isConnected {
            NavigationLink(value: SettingsTopic.appleHealth) { label }
                .accessibilityIdentifier("capability.apple_health")
        } else {
            HStack {
                label
                Spacer()
                if health.phase == .connecting {
                    ProgressView()
                } else {
                    Button(L("nativeConnect")) { Task { await health.connect() } }
                        .buttonStyle(.omiPillSubtle)
                        .accessibilityIdentifier("capability.connect.apple_health")
                }
            }
        }
    }
}

/// One integration on one line: logo, name, and Connect, or the menu (and the task app's settings)
/// once connected.
private struct IntegrationRow: View {
    @Environment(CapabilitiesStore.self) private var store
    @Environment(\.webAuthenticationSession) private var webAuthentication
    let integration: Integration

    var body: some View {
        if integration.isConnected, integration.kind == .taskApp {
            NavigationLink { TaskAppSettingsScreen(integration: integration) } label: { label }
                .accessibilityIdentifier("capability.settings.\(integration.id)")
        } else {
            HStack {
                label
                Spacer()
                trailing
            }
        }
    }

    private var label: some View {
        HStack(spacing: DS.Spacing.md) {
            IntegrationLogo(id: integration.id)
            Text(CapabilitiesList.name(integration.id))
        }
    }

    @ViewBuilder
    private var trailing: some View {
        if store.connecting == integration.id {
            ProgressView()
        } else if integration.isConnected {
            Menu {
                Button(L("nativeDisconnect"), role: .destructive) { Task { await store.disconnect(integration) } }
            } label: {
                Image(systemName: "ellipsis")
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .frame(width: 32, height: 32)
                    .contentShape(Rectangle())
            }
            .accessibilityLabel(L("nativeMore"))
        } else {
            Button(L("nativeConnect")) { Task { await connect() } }
                .buttonStyle(.omiPillSubtle)
                .accessibilityIdentifier("capability.connect.\(integration.id)")
        }
    }

    private func connect() async {
        guard let url = await store.authorizationURL(for: integration) else { return }
        // The backend's callback page redirects to omi://<key>/callback?success=true.
        _ = try? await webAuthentication.authenticate(using: url, callbackURLScheme: "omi", preferredBrowserSession: .ephemeral)
        await store.load()
    }
}

/// Apple Reminders on one line: turn the two-way task sync on, or off from the menu.
private struct RemindersRow: View {
    @Environment(RemindersSyncStore.self) private var reminders

    var body: some View {
        HStack {
            HStack(spacing: DS.Spacing.md) {
                SettingsIcon(systemImage: "checklist")
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    Text(L("nativeRemindersName"))
                    if reminders.accessDenied {
                        Text(L("nativeSettingsRemindersDenied")).font(DS.Typography.caption).foregroundStyle(DS.Palette.live)
                    }
                }
            }
            Spacer()
            if reminders.isSyncing {
                ProgressView()
            } else if reminders.isEnabled {
                Menu {
                    Button(L("nativeSettingsTurnOff"), role: .destructive) { Task { _ = await reminders.setEnabled(false) } }
                } label: {
                    Image(systemName: "ellipsis")
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .frame(width: 32, height: 32)
                        .contentShape(Rectangle())
                }
                .accessibilityLabel(L("nativeMore"))
            } else {
                Button(L("nativeConnect")) { Task { _ = await reminders.setEnabled(true) } }
                    .buttonStyle(.omiPillSubtle)
                    .accessibilityIdentifier("capability.connect.reminders")
            }
        }
    }
}

/// A brand logo on white (logos are made for white), or a glyph for the ones without one.
private struct IntegrationLogo: View {
    let id: String

    var body: some View {
        Group {
            if let logo = OmiMedia.logo(id) {
                logo.resizable().scaledToFit().padding(5)
            } else {
                Image(systemName: id == "gmail" ? "envelope" : id == "google_calendar" ? "calendar" : "checklist")
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.agent)
            }
        }
        .frame(width: 28, height: 28)
        .background(.white, in: RoundedRectangle(cornerRadius: 7, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous).strokeBorder(DS.Palette.hairline.opacity(0.5), lineWidth: 0.5))
        .accessibilityHidden(true)
    }
}
