import OmiKit
import SwiftUI

// Port of `DesktopSettings.tsx` (nav + panes over the store's preference /
// account / connector surfaces), `ConnectionGallery.tsx` (device pairing
// list), and the AppsPage tiles from `DesktopPages.tsx`. Backend switching
// persists through `AppStore.setPreference(omi.backend.softwarePlane)`; the
// same control exists under AI & Automation, per docs/desktop-app.md.

struct DesktopSettingsPage: View {
    @EnvironmentObject var store: AppStore

    @Environment(\.desktopTokens) private var tokens
    @State private var pane: DesktopSettingsPane = .general

    var body: some View {
        HStack(alignment: .top, spacing: 24) {
            settingsNav
                .frame(width: 190)
            paneBody
                .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .padding(.horizontal, 8)
        .accessibilityLabel("Settings")
    }

    // MARK: Nav (DesktopSettings.tsx SettingsNav, sliding pane pill feel)

    private var settingsNav: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(DesktopSettingsPane.allCases, id: \.self) { candidate in
                let selected = candidate == pane
                Button {
                    withAnimation(DesktopMotion.navAnimation(reduceMotion)) {
                        pane = candidate
                    }
                } label: {
                    HStack(spacing: 10) {
                        paneIcon(candidate)
                            .frame(width: 15, height: 15)
                            .foregroundStyle(selected ? tokens.ink : tokens.inkMuted)
                        Text(candidate.rawValue)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(selected ? tokens.ink : tokens.inkMuted)
                            .lineLimit(1)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 10)
                    .frame(height: 40)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(selected ? tokens.glassSelected : Color.clear)
                    )
                }
                .buttonStyle(GlassPressableStyle())
                .accessibilityLabel(candidate.rawValue)
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
        }
    }

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @ViewBuilder
    private func paneIcon(_ pane: DesktopSettingsPane) -> some View {
        switch pane {
        case .general: DesktopIcon.gear
        case .account: DesktopIcon.home
        case .transcription: DesktopIcon.sparkles
        case DesktopSettingsPane.rewind: DesktopIcon.history
        case .alertsPrivacy: CheckCircleGlyph()
        case .aiAutomation: DesktopIcon.chatBubble
        case .apps: DesktopIcon.checklist
        case .about: DesktopIcon.timeline
        }
    }

    // MARK: Panes

    @ViewBuilder
    private var paneBody: some View {
        FadedScrollView {
            VStack(alignment: .leading, spacing: 0) {
                switch pane {
                case .general: generalPane
                case .account: accountPane
                case .transcription: transcriptionPane
                case DesktopSettingsPane.rewind: rewindPane
                case .alertsPrivacy: alertsPrivacyPane
                case .aiAutomation: aiAutomationPane
                case .apps: appsPane
                case .about: aboutPane
                }
            }
            .padding(.bottom, 24)
            .frame(maxWidth: 620, alignment: .leading)
        }
    }

    private var generalPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            PageHeading(title: "General", subtitle: "Appearance, interface, and devices.")
            themeRow
            interfaceRow
            deviceSection
        }
    }

    private var themeRow: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Appearance")
            DesktopSegmented(
                options: [DesktopAppearance.dark, DesktopAppearance.light],
                label: { $0 == DesktopAppearance.light ? "Light" : "Dark" },
                selection: store.preferences.appearance,
                onChange: { value in
                    Task {
                        await store.setPreference(desktopPreferenceKeys.appearance, PreferenceValue.string(value.rawValue))
                    }
                }
            )
        }
        .padding(.bottom, 20)
    }

    private var interfaceRow: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Interface")
            // v5.1 Activity IA vs the v5 pages IA — both ship in this surface.
            DesktopSegmented(
                options: [DesktopUiVersion.v51, DesktopUiVersion.v5],
                label: { $0 == DesktopUiVersion.v51 ? "v5.1 (Activity)" : "v5 (Pages)" },
                selection: store.preferences.uiVersion,
                onChange: { value in
                    Task {
                        await store.setPreference(desktopPreferenceKeys.uiVersion, PreferenceValue.string(value.rawValue))
                    }
                }
            )
        }
        .padding(.bottom, 20)
    }

    /// Device connection lives in Settings (docs/desktop-app.md).
    private var deviceSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Device")
            ConnectionGalleryView()
        }
        .padding(.bottom, 20)
    }

    private var accountPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            PageHeading(title: "Account & Plan", subtitle: "Who you are signed in as, and your plan.")
            backendPlaneRow
            if let profile = store.accountSettings?.profile {
                VStack(alignment: .leading, spacing: 6) {
                    settingRow("Name", profile.name ?? "—")
                    settingRow("Email", profile.email ?? "—")
                }
                .padding(.bottom, 20)
            }
            if let profileError = store.accountSettings?.profileError {
                errorCopy(profileError)
            }
            Button {
                Task { await store.signOut() }
            } label: {
                Text("Sign out")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(tokens.red)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(RoundedRectangle(cornerRadius: 10).fill(tokens.glassQuiet))
            }
            .buttonStyle(GlassPressableStyle())
        }
    }

    /// Settings → General/AI → Backend: Old backend (api.omi.me account) or
    /// New backend (the configured v5 origin). Unconfigured new origins fail
    /// in the store, never silently fall back.
    private var backendPlaneRow: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Backend")
            DesktopSegmented(
                options: [SoftwarePlane.old, SoftwarePlane.new],
                label: { $0 == SoftwarePlane.new ? "New backend" : "Old backend" },
                selection: store.preferences.softwarePlane,
                onChange: { value in
                    Task {
                        await store.setPreference(
                            desktopPreferenceKeys.softwarePlane, PreferenceValue.string(value.rawValue)
                        )
                    }
                }
            )
        }
        .padding(.bottom, 20)
    }

    private var transcriptionPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            PageHeading(title: "Transcription", subtitle: "How speech becomes text.")
            GlassToggleRow(
                label: "Auto-detect language",
                value: store.preferences.transcriptionAutoDetect
            ) { value in
                Task {
                    await store.setPreference(desktopPreferenceKeys.transcriptionAutoDetect, PreferenceValue.bool(value))
                }
            }
            GlassToggleRow(
                label: "Voice activity gate",
                value: store.preferences.vadGate
            ) { value in
                Task {
                    await store.setPreference(desktopPreferenceKeys.vadGate, PreferenceValue.bool(value))
                }
            }
            audioModeRow
        }
    }

    private var audioModeRow: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Microphone recording")
            DesktopSegmented(
                options: [AudioRecordingMode.off, AudioRecordingMode.always, AudioRecordingMode.meetings],
                label: { mode in
                    switch mode {
                    case AudioRecordingMode.always: return "Always"
                    case AudioRecordingMode.meetings: return "Meetings"
                    case AudioRecordingMode.off: return "Off"
                    }
                },
                selection: store.preferences.audioMode,
                onChange: { value in
                    Task {
                        await store.setPreference(desktopPreferenceKeys.audioMode, PreferenceValue.string(value.rawValue))
                    }
                }
            )
        }
        .padding(.bottom, 20)
    }

    private var rewindPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            PageHeading(title: "Rewind", subtitle: "Local screen memory and its storage.")
            GlassToggleRow(
                label: "Screen capture",
                value: store.preferences.screenCapture
            ) { value in
                Task {
                    if value {
                        await store.requestPermission(PermissionKind.screen)
                    }
                    await store.setPreference(desktopPreferenceKeys.screenCapture, PreferenceValue.bool(value))
                }
            }
            retentionRow
        }
    }

    private var retentionRow: some View {
        Stepper(
            onIncrement: {
                Task {
                    await store.setPreference(
                        desktopPreferenceKeys.rewindRetentionDays,
                        PreferenceValue.integer(min(90, store.preferences.rewindRetentionDays + 7))
                    )
                }
            },
            onDecrement: {
                Task {
                    await store.setPreference(
                        desktopPreferenceKeys.rewindRetentionDays,
                        PreferenceValue.integer(max(1, store.preferences.rewindRetentionDays - 7))
                    )
                }
            },
            onEditingChanged: { _ in },
            label: {
                settingRow(
                    "Keep captures",
                    "\(store.preferences.rewindRetentionDays) days"
                )
            }
        )
        .padding(.bottom, 20)
    }

    private var alertsPrivacyPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            PageHeading(title: "Alerts & Privacy", subtitle: "Notifications and what leaves your Mac.")
            GlassToggleRow(
                label: "Notifications",
                value: store.preferences.notificationsEnabled
            ) { value in
                Task {
                    if value {
                        await store.requestPermission(PermissionKind.notifications)
                    }
                    await store.setPreference(desktopPreferenceKeys.notificationsEnabled, PreferenceValue.bool(value))
                }
            }
            GlassToggleRow(
                label: "Interface sounds",
                value: store.preferences.interfaceSounds
            ) { value in
                Task {
                    await store.setPreference(desktopPreferenceKeys.interfaceSounds, PreferenceValue.bool(value))
                }
            }
            GlassToggleRow(
                label: "Store recordings in cloud",
                value: store.accountSettings?.storeRecordingPermission ?? false
            ) { value in
                Task { await store.setStoreRecordingPermission(value) }
            }
            GlassToggleRow(
                label: "Private cloud sync",
                value: store.accountSettings?.privateCloudSync ?? false
            ) { value in
                Task { await store.setPrivateCloudSync(value) }
            }
            GlassToggleRow(
                label: "Improve Omi with my data",
                value: store.accountSettings?.trainingOptedIn ?? false
            ) { _ in
                Task { await store.optInTrainingData() }
            }
        }
    }

    private var aiAutomationPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            PageHeading(title: "AI & Automation", subtitle: "Live voice, shortcuts, and the backend plane.")
            backendPlaneRow
            GlassToggleRow(
                label: "Ask Omi shortcut",
                value: store.preferences.openOmiShortcut
            ) { value in
                Task {
                    await store.setPreference(desktopPreferenceKeys.openOmiShortcut, PreferenceValue.bool(value))
                }
            }
            GlassToggleRow(
                label: "Push to talk",
                value: store.preferences.pushToTalk
            ) { value in
                Task {
                    await store.setPreference(desktopPreferenceKeys.pushToTalk, PreferenceValue.bool(value))
                }
            }
            GlassToggleRow(
                label: "Floating Ask bar",
                value: store.preferences.floatingBar
            ) { value in
                Task {
                    await store.setPreference(desktopPreferenceKeys.floatingBar, PreferenceValue.bool(value))
                }
            }
        }
    }

    /// AppsPage: connectors over the production Omi API.
    private var appsPane: some View {
        VStack(alignment: .leading, spacing: 12) {
            PageHeading(title: "Apps", subtitle: "Connectors for your connected world.")
            if let snapshot = store.connectors {
                ForEach(snapshot.apps) { app in
                    appTile(app)
                }
                if let error = snapshot.enabledError {
                    errorCopy(error)
                }
                if snapshot.apps.isEmpty {
                    EmptyCopy("No apps installed yet.")
                }
            } else {
                HStack(spacing: 8) {
                    OmiLoadingMark(size: 18, ink: tokens.ink)
                    EmptyCopy(store.cloudLoading ? "Loading apps…" : "Sign in to load your apps.")
                }
            }
        }
        .onAppear {
            Task { await store.refreshConnectors() }
        }
    }

    private func appTile(_ app: CloudApp) -> some View {
        let enabled: Bool
        if let enabledIds = store.connectors?.enabledIds {
            enabled = enabledIds.contains(app.id)
        } else {
            enabled = app.enabled
        }
        return HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(app.name)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(tokens.ink)
                Text(app.category.isEmpty ? app.author : app.category)
                    .font(.system(size: 12))
                    .foregroundStyle(tokens.inkMuted)
                Text(app.description)
                    .font(.system(size: 12))
                    .foregroundStyle(tokens.inkMuted)
                    .lineLimit(2)
                    .padding(.top, 2)
            }
            Spacer(minLength: 0)
            GlassToggle(
                label: "\(enabled ? "Disable" : "Enable") \(app.name)",
                value: enabled
            ) { value in
                Task {
                    if value {
                        await store.enableConnector(appId: app.id)
                    } else {
                        await store.disableConnector(appId: app.id)
                    }
                }
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 14).fill(tokens.glassQuiet))
    }

    private var aboutPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            PageHeading(title: "About", subtitle: "Omi for Mac — the v5 Swift client.")
            settingRow("Interface version", store.preferences.uiVersion.rawValue)
            if let origin = store.preferences.stampedV5Origin {
                settingRow("New backend origin", origin)
            }
        }
    }

    // MARK: Small pieces

    private func settingRow(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title)
                .font(.system(size: 14))
                .foregroundStyle(tokens.ink)
            Spacer(minLength: 0)
            Text(value)
                .font(.system(size: 13))
                .foregroundStyle(tokens.inkMuted)
        }
        .frame(minHeight: 40)
    }

    private func errorCopy(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 12))
            .foregroundStyle(tokens.red)
            .padding(.bottom, 12)
    }
}

/// Toggle row layout shared by the panes.
struct GlassToggleRow: View {
    let label: String
    let value: Bool
    let onChange: (Bool) -> Void

    var body: some View {
        HStack {
            Text(label)
                .font(.system(size: 14))
            Spacer(minLength: 0)
            GlassToggle(label: label, value: value, onValueChange: onChange)
        }
        .frame(minHeight: 44)
    }
}

// MARK: - ConnectionGallery (ConnectionGallery.tsx)

/// Device pairing gallery: scan, list discovered Omis, connect/disconnect,
/// and live status from the store's device state.
struct ConnectionGalleryView: View {
    @EnvironmentObject var store: AppStore

    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            statusLine
            if store.scanning {
                HStack(spacing: 8) {
                    OmiLoadingMark(size: 16, ink: tokens.ink)
                    Button("Stop scan") {
                        store.stopScan()
                    }
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(tokens.blue)
                }
            } else {
                Button("Scan for Omi") {
                    Task { await store.startScan() }
                }
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(tokens.blue)
            }
            ForEach(store.discoveredDevices) { device in
                deviceRow(device)
            }
            if let error = store.deviceErrorCopy {
                Text(error)
                    .font(.system(size: 12))
                    .foregroundStyle(tokens.red)
            }
        }
    }

    private var statusLine: some View {
        let connected = store.connectedDeviceName != nil
        let battery = store.batteryLevel.map { "\($0)%" } ?? "—"
        return HStack(spacing: 8) {
            Circle()
                .fill(connected ? tokens.blue : tokens.inkFaint)
                .frame(width: 8, height: 8)
            Text(connectedStatusText)
                .font(.system(size: 13))
                .foregroundStyle(tokens.ink)
            if connected {
                Text("Battery \(battery)")
                    .font(.system(size: 12))
                    .foregroundStyle(tokens.inkMuted)
                Button("Disconnect") {
                    Task { await store.disconnectDevice() }
                }
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(tokens.red)
            }
        }
    }

    private var connectedStatusText: String {
        switch store.connectedDeviceName {
        case let name?:
            switch store.captureStage {
            case CaptureStage.waiting: return "\(name) — waiting for audio"
            case CaptureStage.active: return "\(name) — listening"
            default: return "\(name) connected"
            }
        case nil:
            return "No Omi connected"
        }
    }

    private func deviceRow(_ device: DiscoveredDevice) -> some View {
        let connecting = store.connectingDeviceId == device.id
        return HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(device.name.isEmpty ? "Omi" : device.name)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(tokens.ink)
                if let rssi = device.rssi {
                    Text("Signal \(rssi) dBm")
                        .font(.system(size: 11))
                        .foregroundStyle(tokens.inkMuted)
                }
            }
            Spacer(minLength: 0)
            if connecting {
                OmiLoadingMark(size: 16, ink: tokens.ink)
            } else {
                Button("Connect") {
                    Task { await store.connect(device) }
                }
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(tokens.blue)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 12).fill(tokens.glassQuiet))
    }
}
