import OmiComponents
import OmiDesign
import OmiDevice
import OmiService
import SwiftUI

/// My Omi, laid out like AirPods in iOS Settings: the pendant itself large in the middle with its
/// name and one status line (dot, listening or paused, battery), three round quick buttons (pause,
/// find, light), the few settings people change as flat rows, recordings waiting on the Omi as one
/// row, then this Omi's software, About this Omi and help. Away: the same page with the pendant
/// faded, a Connect button and the quick buttons dimmed. Never paired: the Omis nearby as rows and
/// "Get an Omi" as one quiet row.
public struct DeviceScreen: View {
    @Environment(DeviceStore.self) private var devices
    @Environment(CaptureStore.self) private var capture
    @Environment(FirmwareStore.self) private var firmware
    @Environment(SyncStore.self) private var sync
    /// `-omiDevicePage help|diagnostics|light` (Debug): opens that page for simulator QA.
    @State private var opensHelp = DeviceDebug.page == "help"
    @State private var opensDiagnostics = DeviceDebug.page == "diagnostics"
    /// My Devices › How to use your Omi (the shell hands in the onboarding lessons).
    private let tutorial: AnyView?

    public init(tutorial: AnyView? = nil) {
        self.tutorial = tutorial
    }

    public var body: some View {
        OmiFlatList {
            if let paired = devices.paired {
                Section {
                    hero(title: paired.name)
                    DeviceQuickButtons().omiPlainRow()
                }
                if devices.connection == .connected { DeviceControlsSection() }
                if sync.status != .hidden { DeviceRecordingsRow() }
                Section {
                    softwareRow
                    NavigationLink {
                        DeviceInfoScreen(device: paired, codec: devices.codec?.listenValue)
                    } label: {
                        DeviceRow(L("nativeAboutThisOmi"), systemImage: "info.circle")
                    }
                    .accessibilityIdentifier("device.info")
                    help(deviceName: paired.name)
                } footer: {
                    VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                        if firmware.phase == .idle, let notes = firmware.available?.notes { Text(notes).lineLimit(3) }
                        // Already has one: where to get another stays a quiet link at the very end.
                        Link(L("nativeGetAnotherOmi"), destination: Self.shopURL)
                            .font(DS.Typography.caption.weight(.semibold))
                            .foregroundStyle(DS.Palette.inkSecondary)
                    }
                    .padding(.top, DS.Spacing.xs)
                }
            } else {
                Section { neverPairedHero }
                nearby
                Section {
                    Link(destination: Self.shopURL) {
                        HStack {
                            DeviceRow(L("nativeGetAnOmi"), systemImage: "bag")
                            Spacer()
                            Image(systemName: "arrow.up.right").font(DS.Typography.caption).foregroundStyle(DS.Palette.inkTertiary)
                        }
                    }
                    .accessibilityIdentifier("device.getOmi")
                } footer: {
                    Text(L("nativeNoOmiFooter"))
                }
            }
        }
        .omiPage(L("nativeQuickActionMyOmi"))
        .task {
            // Opening the page counts as "Try again" for a paired Omi that is not connected.
            if devices.paired == nil { devices.scan() } else if devices.connection == .disconnected { devices.start() }
            await firmware.checkIfDue()
        }
        .onDisappear { devices.stopScan() }
        .navigationDestination(isPresented: $opensHelp) { OmiHelpScreen(deviceName: devices.paired?.name ?? "Omi", tutorial: tutorial) }
        .navigationDestination(isPresented: $opensDiagnostics) { DeviceDiagnosticsScreen() }
    }

    private var state: SettingsHub.OmiState {
        SettingsHub.omiState(
            isPaired: devices.paired != nil, connection: devices.connection, battery: devices.battery,
            isMuted: capture.isDeviceMuted, isListening: capture.source == .device && capture.isLive
        )
    }

    /// The pendant large in the middle, its name, the status line; away, a Connect button.
    private func hero(title: String) -> some View {
        VStack(spacing: DS.Spacing.sm) {
            OmiPendantPhoto(size: 150, isFaded: !state.isConnected)
                .padding(.bottom, DS.Spacing.sm)
            Text(title)
                .font(DS.Typography.title)
                .foregroundStyle(DS.Palette.ink)
                .lineLimit(1)
                .accessibilityAddTraits(.isHeader)
            statusLine
            if !state.isConnected, !devices.isUpdatingFirmware { connect }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, DS.Spacing.sm)
        .padding(.bottom, DS.Spacing.lg)
        .omiPlainRow()
    }

    /// ● Listening · 76% ▮▮▮▯ (red while listening, green connected, gray away).
    private var statusLine: some View {
        HStack(spacing: DS.Spacing.sm) {
            OmiStatusDot(dot: state.dot, size: 8, ring: .clear, showsOff: true)
            Text(statusText)
            if let battery = state.battery {
                Text(verbatim: "·")
                BatteryBadge(level: battery)
                if devices.isCharging == true {
                    Image(systemName: "bolt.fill").accessibilityLabel(L("charging"))
                }
            }
        }
        .font(DS.Typography.callout)
        .foregroundStyle(DS.Palette.inkSecondary)
        .lineLimit(1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("device.status")
    }

    private var statusText: String {
        switch state {
        case .connected(_, .listening): L("nativeOmiListening")
        case .connected(_, .paused): L("nativePaused")
        case .connected: L("nativeConnected")
        case .connecting: L("nativeConnecting")
        case .none, .notConnected: L("nativeNotConnected")
        }
    }

    /// Away: one Connect button (tries right away; the app keeps waiting in the background either
    /// way) and what to check, in one line.
    private var connect: some View {
        VStack(spacing: DS.Spacing.sm) {
            Button {
                devices.start()
            } label: {
                HStack(spacing: DS.Spacing.sm) {
                    if devices.connection == .connecting { ProgressView().tint(DS.Palette.onAccent) }
                    Text(L("connect"))
                }
            }
            .buttonStyle(.omiPill)
            .disabled(devices.connection == .connecting)
            .accessibilityIdentifier("device.retry")
            Group {
                if devices.bluetooth == .poweredOff || devices.bluetooth == .unauthorized {
                    Label(L("nativeBluetoothOff"), systemImage: "exclamationmark.triangle").foregroundStyle(DS.Palette.warning)
                } else {
                    Text(L("nativeOmiOnAndNearby")).foregroundStyle(DS.Palette.inkTertiary)
                }
            }
            .font(DS.Typography.caption)
            .multilineTextAlignment(.center)
            .lineLimit(2)
        }
        .padding(.top, DS.Spacing.sm)
    }

    /// Never paired: the pendant faded, "Connect your Omi" and how.
    private var neverPairedHero: some View {
        VStack(spacing: DS.Spacing.sm) {
            OmiPendantPhoto(size: 130, isFaded: true).padding(.bottom, DS.Spacing.sm)
            Text(L("nativeConnectYourOmi"))
                .font(DS.Typography.title)
                .foregroundStyle(DS.Palette.ink)
                .multilineTextAlignment(.center)
            Text(L("nativePairingHint"))
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.inkSecondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, DS.Spacing.lg)
        .padding(.horizontal, DS.Spacing.lg)
        .omiPlainRow()
    }

    /// The Omis nearby, one row each; a tap pairs.
    private var nearby: some View {
        Section {
            if devices.bluetooth == .poweredOff || devices.bluetooth == .unauthorized {
                DeviceRow(L("nativeBluetoothOff"), systemImage: "exclamationmark.triangle", tint: DS.Palette.warning)
            }
            ForEach(devices.discovered) { discovery in
                Button { devices.pair(discovery) } label: {
                    HStack(spacing: DS.Spacing.md) {
                        OmiPendantThumbnail(size: 28).frame(width: 28)
                        Text(discovery.name).foregroundStyle(DS.Palette.ink)
                        Image(systemName: "wifi", variableValue: signal(discovery.rssi))
                            .font(DS.Typography.caption)
                            .foregroundStyle(DS.Palette.inkTertiary)
                            .accessibilityHidden(true)
                        Spacer(minLength: DS.Spacing.sm)
                        Text(L("connect")).font(.subheadline.weight(.semibold)).foregroundStyle(DS.Palette.ink)
                    }
                }
                .accessibilityHint(L("nativeTapToConnect"))
                .accessibilityIdentifier("device.pair.\(discovery.name)")
            }
            if devices.isScanning || devices.discovered.isEmpty {
                HStack(spacing: DS.Spacing.md) {
                    ProgressView().frame(width: 28)
                    Text(L("nativeLookingForOmi")).foregroundStyle(DS.Palette.inkSecondary)
                }
                .accessibilityElement(children: .combine)
            }
        } header: {
            OmiSectionLabel(L("nativeNearbyDevices"))
        }
    }

    /// "Software: up to date", or the update on offer / under way (FirmwareUpdateRow).
    @ViewBuilder
    private var softwareRow: some View {
        if firmware.phase == .idle, firmware.available == nil {
            HStack {
                DeviceRow(L("nativeSoftware"), systemImage: "checkmark.seal")
                Spacer(minLength: DS.Spacing.sm)
                Text(L("nativeUpToDate")).foregroundStyle(DS.Palette.inkSecondary)
            }
            .accessibilityElement(children: .combine)
        } else {
            FirmwareUpdateRow()
        }
    }

    /// Help with this Omi: the button tutorial and charging help (`OmiHelpScreen`).
    private func help(deviceName: String) -> some View {
        NavigationLink { OmiHelpScreen(deviceName: deviceName, tutorial: tutorial) } label: {
            DeviceRow(L("nativeHelpWithYourOmi"), systemImage: "questionmark.circle")
        }
        .accessibilityIdentifier("device.help")
    }

    static let shopURL = URL(string: "https://www.omi.me/?_ref=omi_connect_device")!

    static func chargingHelpURL(_ deviceName: String) -> URL {
        let page = switch deviceName {
        case "Omi DevKit 2": "charging-devkit2"
        case "Omi": "charging-omi"
        default: "charging"
        }
        return URL(string: "https://www.omi.me/pages/\(page)")!
    }

    /// "3 min", "1 hr, 5 min" in the user's language; under a minute reads as a minute.
    static func duration(_ seconds: Int) -> String {
        let minutes = max(1, (seconds + 59) / 60)
        return Duration.seconds(minutes * 60).formatted(.units(allowed: [.hours, .minutes], width: .abbreviated))
    }

    private func signal(_ rssi: Int) -> Double {
        min(1, max(0, Double(rssi + 100) / 50))
    }
}

/// Battery percentage with a matching symbol.
public struct BatteryBadge: View {
    let level: Int

    public init(level: Int) {
        self.level = level
    }

    public var body: some View {
        // Not a Label: inside a List row a Label may drop its title and show only the symbol.
        HStack(spacing: DS.Spacing.xs) {
            Text(verbatim: "\(level)%")
            Image(systemName: symbol)
        }
        .font(DS.Typography.callout.monospacedDigit())
        .foregroundStyle(LowBatteryAlert.isLow(level) ? DS.Palette.warning : DS.Palette.inkSecondary)
        .accessibilityElement(children: .combine)
    }

    private var symbol: String {
        switch level {
        case ..<13: "battery.0percent"
        case ..<38: "battery.25percent"
        case ..<63: "battery.50percent"
        case ..<88: "battery.75percent"
        default: "battery.100percent"
        }
    }
}

/// A My Omi row: a thin line glyph in a fixed column, then the title (Settings' row look).
struct DeviceRow: View {
    let title: String
    let systemImage: String
    var tint: Color = DS.Palette.ink

    init(_ title: String, systemImage: String, tint: Color = DS.Palette.ink) {
        self.title = title
        self.systemImage = systemImage
        self.tint = tint
    }

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            Image(systemName: systemImage).omiRowGlyph()
            Text(title).foregroundStyle(tint)
        }
    }
}
