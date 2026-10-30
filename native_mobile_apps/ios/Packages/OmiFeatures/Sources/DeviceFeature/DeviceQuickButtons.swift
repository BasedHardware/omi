import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// My Omi's three round quick buttons under the pendant, as AirPods' noise control: pause or
/// resume listening, find the Omi (it plays its sound), and the light's brightness (a small
/// sheet). Dimmed while the Omi is away.
struct DeviceQuickButtons: View {
    @Environment(DeviceStore.self) private var devices
    @Environment(CaptureStore.self) private var capture
    @State private var showsLight = DeviceDebug.page == "light"

    var body: some View {
        let connected = devices.connection == .connected
        let paused = capture.isDeviceMuted
        HStack(alignment: .top, spacing: 0) {
            QuickButton(
                title: paused ? L("nativeQuickResume") : L("nativeQuickPause"),
                systemImage: paused ? "play.fill" : "pause",
                isOn: paused,
                spokenValue: paused ? L("nativePaused") : nil,
                identifier: "device.mute"
            ) {
                DSHaptics.selection()
                capture.isDeviceMuted.toggle()
            }
            .disabled(!connected)
            QuickButton(
                title: devices.isFinding ? L("nativeQuickPlayingSound") : L("nativeQuickFind"),
                systemImage: devices.isFinding ? "speaker.wave.2" : "dot.radiowaves.left.and.right",
                isOn: devices.isFinding,
                spokenTitle: L("nativeFindMyOmi"),
                identifier: "device.find"
            ) {
                DSHaptics.selection()
                Task { await devices.findDevice() }
            }
            .disabled(!devices.canFind || devices.isFinding)
            QuickButton(
                title: L("nativeQuickLight"),
                caption: lightCaption,
                systemImage: "sun.max",
                isOn: false,
                spokenTitle: L("nativeLightBrightness"),
                spokenValue: lightCaption,
                identifier: "device.light"
            ) {
                showsLight = true
            }
            .disabled(!devices.canDimLED)
        }
        .frame(maxWidth: .infinity)
        .padding(.bottom, DS.Spacing.lg)
        .sheet(isPresented: $showsLight) { LightSheet() }
    }

    private var lightCaption: String? {
        guard devices.canDimLED, let level = devices.ledBrightness else { return nil }
        return level < 1 ? L("off") : "\(level)%"
    }
}

/// One round quick button: a 58 pt circle with a thin glyph (filled ink while on), the label under
/// it and, for the light, its current value.
private struct QuickButton: View {
    let title: String
    var caption: String?
    let systemImage: String
    let isOn: Bool
    /// What VoiceOver says when the short label is not enough ("Find my Omi").
    var spokenTitle: String?
    var spokenValue: String?
    let identifier: String
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            VStack(spacing: DS.Spacing.sm) {
                Image(systemName: systemImage)
                    .font(.system(size: 21, weight: .light))
                    .foregroundStyle(isOn ? DS.Palette.onAccent : DS.Palette.ink)
                    .frame(width: 58, height: 58)
                    .background(isOn ? DS.Palette.ink : DS.Palette.card, in: Circle())
                    .contentTransition(.symbolEffect(.replace))
                VStack(spacing: 1) {
                    Text(title)
                        .font(DS.Typography.label)
                        .foregroundStyle(DS.Palette.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                    if let caption {
                        Text(caption)
                            .font(DS.Typography.caption.monospacedDigit())
                            .foregroundStyle(DS.Palette.inkSecondary)
                    }
                }
            }
            .frame(maxWidth: .infinity)
            .opacity(isEnabled ? 1 : 0.4)
            .contentShape(Rectangle())
        }
        .buttonStyle(QuickPressStyle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(spokenTitle ?? title))
        .accessibilityValue(Text(spokenValue ?? ""))
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier(identifier)
        .animation(DS.Motion.gentle, value: isOn)
    }
}

private struct QuickPressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.94 : 1)
            .animation(DS.Motion.snappy, value: configuration.isPressed)
    }
}

/// The light's brightness, from the Light quick button: one slider, the value, Done.
struct LightSheet: View {
    @Environment(DeviceStore.self) private var devices
    @Environment(\.dismiss) private var dismiss
    @State private var brightness: Double = 100
    @State private var lastWrite = Date.distantPast

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.lg) {
            HStack {
                Text(L("nativeLightBrightness"))
                    .font(DS.Typography.sectionTitle)
                    .foregroundStyle(DS.Palette.ink)
                Spacer()
                Text(brightness < 1 ? L("off") : "\(Int(brightness))%")
                    .font(DS.Typography.body.monospacedDigit())
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .contentTransition(.numericText())
            }
            HStack(spacing: DS.Spacing.md) {
                Image(systemName: "sun.min").foregroundStyle(DS.Palette.inkSecondary).accessibilityHidden(true)
                Slider(value: $brightness, in: 0 ... 100) {
                    Text(L("nativeLightBrightness"))
                } onEditingChanged: { editing in
                    if !editing, Int(brightness) != devices.ledBrightness { devices.setLEDBrightness(Int(brightness)) }
                }
                .tint(DS.Palette.ink)
                .accessibilityIdentifier("device.led")
                Image(systemName: "sun.max").foregroundStyle(DS.Palette.inkSecondary).accessibilityHidden(true)
            }
            Button(L("done")) { dismiss() }
                .buttonStyle(.omiPrimary)
        }
        .padding(.horizontal, DS.Spacing.gutter)
        .padding(.top, DS.Spacing.xl)
        .presentationDetents([.height(230)])
        .presentationDragIndicator(.visible)
        .presentationBackground(DS.Palette.background)
        .onAppear { if let level = devices.ledBrightness { brightness = Double(level) } }
        .onChange(of: brightness) {
            // Reading the Omi's value moves the slider too; only the user's drag is written back.
            guard Int(brightness) != devices.ledBrightness else { return }
            throttled { devices.setLEDBrightness(Int(brightness)) }
        }
    }

    /// The light follows the slider while dragging, at most every 0.3 s (Flutter's debounce).
    private func throttled(_ write: () -> Void) {
        guard Date.now.timeIntervalSince(lastWrite) > 0.3 else { return }
        lastWrite = .now
        write()
    }
}
