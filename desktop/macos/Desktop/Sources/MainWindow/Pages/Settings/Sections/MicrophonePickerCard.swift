import OmiTheme
import SwiftUI

/// Microphone selection for transcription capture. "System Default" follows
/// macOS; an explicit device (e.g. Ray-Ban Meta glasses paired over Bluetooth)
/// pins capture to that device. Bluetooth mics run at voice quality (HFP) while
/// in use — stated in plain language rather than hidden.
struct MicrophonePickerCard: View {
  @AppStorage(AudioCaptureService.preferredInputUIDDefaultsKey) private var preferredUID: String =
    ""
  @State private var devices: [AudioCaptureService.InputDeviceInfo] = []
  let onChanged: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      HStack {
        Image(systemName: "mic")
          .scaledFont(size: 16)
          .foregroundColor(OmiColors.textPrimary)

        Text("Microphone")
          .scaledFont(size: 15, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()
      }

      row(
        selected: preferredUID.isEmpty,
        title: "System Default",
        subtitle: "Follow the Mac's input device"
      ) {
        preferredUID = ""
        onChanged()
      }

      ForEach(devices) { device in
        row(
          selected: preferredUID == device.uid,
          title: device.name,
          subtitle: AudioCaptureService.isMetaGlassesName(device.name)
            ? "Ray-Ban Meta glasses — voice-quality Bluetooth audio while capturing"
            : (device.isBluetooth ? "Bluetooth microphone" : nil),
          badge: AudioCaptureService.isMetaGlassesName(device.name) ? "Glasses" : nil
        ) {
          preferredUID = device.uid
          onChanged()
        }
      }
    }
    .onAppear { devices = AudioCaptureService.listInputDevices() }
  }

  @ViewBuilder
  private func row(
    selected: Bool,
    title: String,
    subtitle: String? = nil,
    badge: String? = nil,
    action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      HStack(alignment: .top, spacing: 12) {
        Image(systemName: selected ? "checkmark.circle.fill" : "circle")
          .scaledFont(size: 20)
          .foregroundColor(selected ? OmiColors.textPrimary : OmiColors.textTertiary)

        VStack(alignment: .leading, spacing: 4) {
          HStack(spacing: 8) {
            Text(title)
              .scaledFont(size: 14, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)
            if let badge {
              Text(badge)
                .scaledFont(size: 11, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .background(OmiColors.textTertiary.opacity(0.25))
                .clipShape(Capsule())
            }
          }
          if let subtitle {
            Text(subtitle)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }
        }

        Spacer()
      }
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
  }
}
