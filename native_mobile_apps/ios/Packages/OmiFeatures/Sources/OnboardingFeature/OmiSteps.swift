import AVFoundation
import OmiComponents
import OmiDesign
import OmiService
import SwiftUI
import UserNotifications

/// "Do you have an Omi?" Two big cards side by side, a picture and one line each; a tap moves on.
struct HasOmiStep: View {
    let store: OnboardingStore

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerYourOmi"), title: L("nativeDoYouHaveOmi"), subtitle: L("nativeDoYouHaveOmiShort")
        ) {
            HStack(spacing: DS.Spacing.md) {
                OmiChoiceCard(title: L("nativeYesIHaveOmi"), selected: store.hasOmi == true) {
                    OmiMedia.device.resizable().scaledToFit().frame(width: 92, height: 92)
                } action: { store.chooseOmi(true) }
                .accessibilityIdentifier("onboarding.hasOmi.yes")
                OmiChoiceCard(title: L("nativeNoUseIphone"), selected: store.hasOmi == false) {
                    Image(systemName: "iphone")
                        .font(.system(size: 54, weight: .ultraLight))
                        .foregroundStyle(DS.Palette.ink)
                        .frame(width: 92, height: 92)
                } action: { store.chooseOmi(false) }
                .accessibilityIdentifier("onboarding.hasOmi.no")
            }
            .padding(.horizontal, DS.Spacing.gutter)
            Link(destination: URL(string: "https://www.omi.me")!) {
                Label(L("nativeGetAnOmi"), systemImage: "arrow.up.right")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .labelStyle(TrailingIconLabelStyle())
            }
            .frame(maxWidth: .infinity)
        }
    }
}

/// A large tappable card: a picture on top, one line under it.
private struct OmiChoiceCard<Picture: View>: View {
    let title: String
    let selected: Bool
    @ViewBuilder let picture: Picture
    let action: () -> Void

    var body: some View {
        Button {
            DSHaptics.selection()
            action()
        } label: {
            VStack(spacing: DS.Spacing.lg) {
                picture
                Text(title)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(DS.Palette.ink)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, minHeight: 196)
            .padding(.horizontal, DS.Spacing.md)
            .background(
                DS.Palette.ink.opacity(selected ? 0.12 : 0.05),
                in: RoundedRectangle(cornerRadius: DS.Radius.hero, style: .continuous)
            )
            .overlay {
                RoundedRectangle(cornerRadius: DS.Radius.hero, style: .continuous)
                    .strokeBorder(selected ? DS.Palette.ink.opacity(0.5) : DS.Palette.ink.opacity(0.08), lineWidth: selected ? 1.5 : 1)
            }
            .contentShape(RoundedRectangle(cornerRadius: DS.Radius.hero, style: .continuous))
        }
        .buttonStyle(PressableCardStyle())
        .accessibilityAddTraits(selected ? [.isSelected] : [])
    }
}

/// Dims a little while pressed, nothing more.
struct PressableCardStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(configuration.isPressed ? 0.7 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// Finds the Omi and connects. Connected: the pendant with a calm check, its name and battery,
/// and Continue. Nothing blinks or pulses.
struct PairStep: View {
    let store: OnboardingStore
    @Environment(DeviceStore.self) private var devices

    private var connected: Bool {
        devices.connection == .connected
    }

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerYourOmi"),
            title: connected ? L("nativeConnectedToOmi") : L("nativeConnectYourOmi"),
            subtitle: connected ? batteryLine : L("nativePairingHint"),
            button: StepButton(title: L("continueButton"), isEnabled: connected, action: store.next),
            secondary: connected ? nil : StepButton(title: L("nativeContinueWithIphone"), action: store.continueWithoutOmi),
            centered: true
        ) {
            PendantImage(size: 150) {
                if connected {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 34))
                        .symbolRenderingMode(.palette)
                        .foregroundStyle(.white, DS.Palette.success)
                        .background(Circle().fill(DS.Palette.background).padding(2))
                        .transition(.scale(scale: 0.6).combined(with: .opacity))
                }
            }
            .animation(DS.Motion.standard, value: connected)
            if !connected { nearby }
        }
        .task {
            devices.start()
            if devices.paired == nil || devices.connection == .disconnected { devices.scan() }
        }
        .onDisappear { devices.stopScan() }
        .onChange(of: connected) { _, connected in if connected { DSHaptics.success() } }
    }

    private var batteryLine: String {
        let name = devices.paired?.name ?? "Omi"
        guard let battery = devices.battery else { return name }
        return L("nativeOmiBatteryLine", name, String(battery))
    }

    @ViewBuilder
    private var nearby: some View {
        if devices.bluetooth == .poweredOff || devices.bluetooth == .unauthorized {
            StatusLine(L("nativeBluetoothOff"), "exclamationmark.triangle.fill", DS.Palette.warning).view
                .padding(.horizontal, DS.Spacing.gutter)
        } else if devices.discovered.isEmpty {
            HStack(spacing: DS.Spacing.sm) {
                ProgressView()
                Text(devices.connection == .connecting ? L("nativeConnecting") : L("searchingForDevices"))
            }
            .font(.subheadline)
            .foregroundStyle(DS.Palette.inkSecondary)
            .frame(maxWidth: .infinity)
        } else {
            RowList {
                ForEach(devices.discovered.prefix(3)) { discovery in
                    Button {
                        DSHaptics.selection()
                        devices.pair(discovery)
                    } label: {
                        HStack(spacing: DS.Spacing.md) {
                            Image(systemName: "circle.circle").font(.title3).foregroundStyle(DS.Palette.inkSecondary).frame(width: 28)
                            Text(discovery.name).font(.body.weight(.medium)).foregroundStyle(DS.Palette.ink)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            if devices.connection == .connecting {
                                ProgressView()
                            } else {
                                Text(L("nativeConnect"))
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(DS.Palette.onAccent)
                                    .padding(.horizontal, DS.Spacing.md)
                                    .frame(height: 32)
                                    .background(DS.Palette.ink, in: Capsule())
                            }
                        }
                        .padding(.horizontal, DS.Spacing.lg)
                        .frame(height: 60)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("onboarding.pair.\(discovery.name)")
                }
            }
        }
    }
}

/// The light, in two boxes: "Omi is recording" (blue live, red saved on the Omi) and charging
/// (green); the rare ones in one quiet line. Still dots, no blinking.
struct LightsStep: View {
    let onContinue: () -> Void

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerYourOmi"), title: L("nativeWhatTheLightMeans"),
            button: StepButton(title: L("continueButton"), action: onContinue)
        ) {
            VStack(spacing: DS.Spacing.md) {
                VStack(alignment: .leading, spacing: DS.Spacing.lg) {
                    Text(L("nativeLightRecordingTitle"))
                        .font(.headline)
                        .foregroundStyle(DS.Palette.ink)
                    // Firmware `set_led_state`: blue while connected, red while it records to its
                    // own storage (transport.c `pusher`), green while charging.
                    light(DS.Palette.agent, L("nativeLightLiveTitle"), L("nativeLightLiveShort"))
                    light(DS.Palette.live, L("nativeLightSavedTitle"), L("nativeLightSavedShort"))
                }
                .onboardingCard(padding: DS.Spacing.xl)
                light(DS.Palette.success, L("nativeLightChargingTitle"), L("nativeLightGreenBody"))
                    .onboardingCard(padding: DS.Spacing.xl)
            }
            .padding(.horizontal, DS.Spacing.gutter)
            // Red blinking until the app set the clock, nothing when off: rare, so one line.
            Text(L("nativeLightRare"))
                .font(.footnote)
                .foregroundStyle(DS.Palette.inkTertiary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, DS.Spacing.gutter)
        }
        .connectsPairedOmi()
    }

    private func light(_ color: Color, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
            Circle().fill(color).frame(width: 12, height: 12)
                .shadow(color: color.opacity(0.6), radius: 4)
                .alignmentGuide(.firstTextBaseline) { $0[.bottom] - 1 }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body.weight(.semibold)).foregroundStyle(DS.Palette.ink)
                Text(detail).font(.subheadline).foregroundStyle(DS.Palette.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityElement(children: .combine)
    }
}

struct TrailingIconLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: DS.Spacing.xs) {
            configuration.title
            configuration.icon
        }
    }
}

// MARK: Permissions

/// Notifications, microphone and location: one row each, an Allow button or a check.
struct PermissionsStep: View {
    let onContinue: () -> Void
    @Environment(LocationStore.self) private var location
    @Environment(\.openURL) private var openURL
    @State private var microphone = AVAudioApplication.shared.recordPermission == .granted
    @State private var notifications = false

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerAlmostDone"), title: L("nativeStayInTheLoop"), subtitle: L("nativePermissionsShort"),
            button: StepButton(title: L("continueButton"), action: onContinue)
        ) {
            RowList {
                row("bell.badge", L("notifications"), granted: notifications) {
                    notifications = await (
                        try? UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound])
                    ) ?? false
                }
                row("mic", L("nativeMicrophone"), granted: microphone) {
                    microphone = await AVAudioApplication.requestRecordPermission()
                }
                // While in use only, as Flutter asks here; "Always" is never needed.
                row("location", L("locationAccess"), granted: location.access == .allowed) {
                    if location.access == .denied {
                        if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                    } else {
                        await location.requestAccess()
                    }
                }
            }
        }
        .task {
            let settings = await UNUserNotificationCenter.current().notificationSettings()
            notifications = settings.authorizationStatus == .authorized
            location.refresh()
        }
    }

    private func row(_ icon: String, _ title: String, granted: Bool, request: @escaping () async -> Void) -> some View {
        HStack(spacing: DS.Spacing.md) {
            Image(systemName: icon).font(.title3).foregroundStyle(DS.Palette.inkSecondary).frame(width: 28)
            Text(title).font(.body.weight(.medium)).frame(maxWidth: .infinity, alignment: .leading)
            if granted {
                Image(systemName: "checkmark.circle.fill").font(.title3).foregroundStyle(DS.Palette.success)
                    .transition(.scale.combined(with: .opacity))
            } else {
                Button(L("allow")) { Task { await request() } }.buttonStyle(.omiPill)
            }
        }
        .padding(.horizontal, DS.Spacing.lg)
        .frame(height: 64)
        .animation(DS.Motion.snappy, value: granted)
    }
}
