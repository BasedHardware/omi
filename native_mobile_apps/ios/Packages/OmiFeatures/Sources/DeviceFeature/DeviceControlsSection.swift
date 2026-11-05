import OmiComponents
import OmiDesign
import OmiDevice
import OmiService
import SwiftUI

/// My Omi › the few settings people change, one flat line each: how sensitive the microphone is,
/// what pressing twice does, and whether the button does anything. Pause, find and the light are
/// the quick buttons above. Only what the connected firmware supports is shown (Flutter
/// `device_settings.dart` customization group).
struct DeviceControlsSection: View {
    @Environment(DeviceStore.self) private var devices

    /// Microphone presets over the firmware's gain levels 1…8 (-20 dB … +40 dB): a quiet room
    /// needs more gain to catch soft voices, a loud place less.
    enum Sensitivity: Int, CaseIterable {
        case loud = 3, normal = 5, quiet = 7

        var title: String {
            switch self {
            case .quiet: L("nativeMicQuiet")
            case .normal: L("nativeMicNormal")
            case .loud: L("nativeMicLoud")
            }
        }

        /// The preset closest to a level read from the Omi (0, muted, reads as a loud place).
        init(level: Int) {
            self = Self.allCases.min { abs($0.rawValue - level) < abs($1.rawValue - level) } ?? .normal
        }
    }

    static var doubleTapChoices: [(action: DoubleTapAction, title: String)] {
        [
            (.endConversation, L("nativePressTwiceEnd")), (.toggleMute, L("nativePressTwicePause")),
            (.star, L("nativePressTwiceStar")),
        ]
    }

    var body: some View {
        @Bindable var devices = devices
        Section {
            if devices.canSetMicGain { microphone }
            pressTwice
            Toggle(isOn: $devices.buttonActionsEnabled) {
                DeviceRow(L("nativeUseTheButton"), systemImage: "circle.circle")
            }
            .accessibilityIdentifier("device.buttonActions")
        } footer: {
            Text(L("nativeUseTheButtonCaption")).lineLimit(1).minimumScaleFactor(0.85)
        }
    }

    /// Microphone · Quiet | Normal | Loud, on one line.
    private var microphone: some View {
        HStack(spacing: DS.Spacing.sm) {
            DeviceRow(L("nativeMicrophone"), systemImage: "mic").fixedSize()
            Spacer(minLength: DS.Spacing.sm)
            Picker(L("nativeMicSensitivity"), selection: Binding(
                get: { Sensitivity(level: devices.micGain ?? Sensitivity.normal.rawValue) },
                set: { devices.setMicGain($0.rawValue) }
            )) {
                ForEach(Sensitivity.allCases.reversed(), id: \.self) { Text($0.title).tag($0) }
            }
            .pickerStyle(.segmented)
            .controlSize(.small)
            .labelsHidden()
            .frame(maxWidth: 220)
            .accessibilityIdentifier("device.micGain")
        }
    }

    /// Press twice · the chosen action as a menu (dimmed while the button is off).
    private var pressTwice: some View {
        @Bindable var devices = devices
        return HStack {
            DeviceRow(L("nativePressTwice"), systemImage: "hand.tap").fixedSize()
            Spacer(minLength: DS.Spacing.sm)
            Menu {
                Picker(L("nativePressTwiceTo"), selection: $devices.doubleTapAction) {
                    ForEach(Self.doubleTapChoices, id: \.action) { Text($0.title).tag($0.action) }
                }
            } label: {
                HStack(spacing: DS.Spacing.xs) {
                    Text(Self.doubleTapChoices.first { $0.action == devices.doubleTapAction }?.title ?? "")
                        .lineLimit(1)
                        .truncationMode(.tail)
                    Image(systemName: "chevron.up.chevron.down").font(DS.Typography.caption)
                }
                .foregroundStyle(DS.Palette.inkSecondary)
            }
            .accessibilityIdentifier("device.doubleTap")
        }
        .disabled(!devices.buttonActionsEnabled)
        .opacity(devices.buttonActionsEnabled ? 1 : 0.45)
    }
}
