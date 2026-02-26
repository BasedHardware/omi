import SwiftUI

/// Audio source selector for choosing between microphone and BLE device
struct AudioSourceSelector: View {
    @ObservedObject var appState: AppState
    @ObservedObject private var deviceProvider = DeviceProvider.shared

    var body: some View {
        HStack(spacing: 12) {
            // Microphone option
            audioSourceButton(
                source: .microphone,
                isSelected: appState.audioSource == .microphone,
                isAvailable: true
            )

            // BLE Device option
            audioSourceButton(
                source: .bleDevice,
                isSelected: appState.audioSource == .bleDevice,
                isAvailable: deviceProvider.isConnected
            )
        }
    }

    private func audioSourceButton(
        source: AudioSource,
        isSelected: Bool,
        isAvailable: Bool
    ) -> some View {
        Button(action: {
            guard isAvailable && !appState.isTranscribing else { return }
            appState.audioSource = source
        }) {
            HStack(spacing: 8) {
                Image(systemName: source.iconName)
                    .scaledFont(size: 14)

                VStack(alignment: .leading, spacing: 2) {
                    Text(source.displayName)
                        .scaledFont(size: 13, weight: .medium)

                    if source == .bleDevice {
                        if deviceProvider.isConnected, let device = deviceProvider.connectedDevice {
                            Text(device.displayName)
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                        } else {
                            Text("Not connected")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                    } else {
                        Text(AudioCaptureService.getCurrentMicrophoneName(preferredDeviceUID: AudioSourceManager.shared.preferredMicrophoneUID) ?? "Default")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(OmiColors.purplePrimary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isSelected ? OmiColors.purplePrimary.opacity(0.15) : OmiColors.backgroundTertiary.opacity(0.5))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(isSelected ? OmiColors.purplePrimary : Color.clear, lineWidth: 1.5)
                    )
            )
            .foregroundColor(isAvailable ? OmiColors.textPrimary : OmiColors.textTertiary)
            .opacity(isAvailable ? 1.0 : 0.5)
        }
        .buttonStyle(.plain)
        .disabled(!isAvailable || appState.isTranscribing)
    }
}

/// Compact audio source indicator for display in headers
struct AudioSourceIndicator: View {
    @ObservedObject var appState: AppState
    @ObservedObject private var deviceProvider = DeviceProvider.shared

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: appState.audioSource.iconName)
                .scaledFont(size: 12)
                .foregroundColor(indicatorColor)

            Text(sourceName)
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            if appState.audioSource == .bleDevice && deviceProvider.isConnected {
                // Show battery for BLE device
                if deviceProvider.batteryLevel >= 0 {
                    HStack(spacing: 2) {
                        Image(systemName: batteryIcon)
                            .scaledFont(size: 10)
                        Text("\(deviceProvider.batteryLevel)%")
                            .scaledFont(size: 10)
                    }
                    .foregroundColor(batteryColor)
                }
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            Capsule()
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
    }

    private var sourceName: String {
        switch appState.audioSource {
        case .microphone:
            return "Mic"
        case .bleDevice:
            if let device = deviceProvider.connectedDevice {
                return device.type.displayName
            }
            return "Device"
        }
    }

    private var indicatorColor: Color {
        if appState.audioSource == .bleDevice {
            return deviceProvider.isConnected ? OmiColors.purplePrimary : .orange
        }
        return OmiColors.purplePrimary
    }

    private var batteryIcon: String {
        let level = deviceProvider.batteryLevel
        switch level {
        case 0..<10: return "battery.0"
        case 10..<35: return "battery.25"
        case 35..<60: return "battery.50"
        case 60..<85: return "battery.75"
        default: return "battery.100"
        }
    }

    private var batteryColor: Color {
        let level = deviceProvider.batteryLevel
        switch level {
        case 0..<20: return .red
        case 20..<40: return .orange
        default: return .green
        }
    }
}

// MARK: - Preview

#Preview("Audio Source Selector") {
    VStack(spacing: 20) {
        AudioSourceSelector(appState: AppState())
        AudioSourceIndicator(appState: AppState())
    }
    .padding()
    .background(OmiColors.backgroundPrimary)
}
