import CoreAudio
import OmiTheme
import SwiftUI

@MainActor
private final class AudioInputDeviceListObserver: ObservableObject {
  @Published private(set) var revision = 0

  private var isObserving = false
  // nonisolated(unsafe): written only on the main actor (start/stop); the one
  // nonisolated read is deinit, which runs after the last reference is gone.
  nonisolated(unsafe) private var listenerBlock: AudioObjectPropertyListenerBlock?

  func start() {
    guard !isObserving else { return }

    var address = Self.devicesPropertyAddress
    let listener: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
      Task { @MainActor in
        self?.revision &+= 1
      }
    }

    let status = AudioObjectAddPropertyListenerBlock(
      AudioObjectID(kAudioObjectSystemObject),
      &address,
      DispatchQueue.main,
      listener
    )
    guard status == noErr else {
      revision &+= 1
      return
    }

    listenerBlock = listener
    isObserving = true
    revision &+= 1
  }

  func stop() {
    guard isObserving, let listenerBlock else { return }
    var address = Self.devicesPropertyAddress
    AudioObjectRemovePropertyListenerBlock(
      AudioObjectID(kAudioObjectSystemObject),
      &address,
      DispatchQueue.main,
      listenerBlock
    )
    self.listenerBlock = nil
    isObserving = false
  }

  deinit {
    guard isObserving, let listenerBlock else { return }
    var address = Self.devicesPropertyAddress
    AudioObjectRemovePropertyListenerBlock(
      AudioObjectID(kAudioObjectSystemObject),
      &address,
      DispatchQueue.main,
      listenerBlock
    )
  }

  nonisolated private static var devicesPropertyAddress: AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(
      mSelector: kAudioHardwarePropertyDevices,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain
    )
  }
}

/// Microphone selection for transcription capture. "System Default" follows
/// macOS; an explicit device (e.g. Ray-Ban Meta glasses paired over Bluetooth)
/// pins capture to that device. Bluetooth mics run at voice quality (HFP) while
/// in use — stated in plain language rather than hidden.
/// Snapshot of a selectable input device, keyed by UID (device IDs are not
/// stable across reconnects) with Bluetooth transport resolved off-main.
private struct PickerInputDevice: Identifiable, Equatable {
  var id: String { uid }
  let uid: String
  let name: String
  let isBluetooth: Bool
}

struct MicrophonePickerCard: View {
  @AppStorage(AudioCaptureService.preferredInputUIDDefaultsKey) private var preferredUID: String =
    ""
  @StateObject private var deviceListObserver = AudioInputDeviceListObserver()
  @State private var devices: [PickerInputDevice] = []
  @State private var refreshInFlight = false
  @State private var refreshQueued = false
  let onChanged: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      HStack {
        Image(systemName: "mic")
          .scaledFont(size: 16)
          .foregroundColor(Ink.primary)

        Text("Microphone")
          .scaledFont(size: 15, weight: .medium)
          .foregroundColor(Ink.primary)

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

      // The pinned device is not plugged in. `AppState.startMicCaptureIfNeeded` already
      // substitutes the Mac's input device and records the degradation, but with no row
      // matching the stored UID this card used to answer "which microphone?" by ticking
      // nothing at all — the one state where the honest answer matters most.
      if pinnedDeviceIsMissing {
        row(
          selected: true,
          title: "Selected microphone unavailable",
          subtitle: "The microphone you picked isn't connected. Omi is capturing on the Mac's "
            + "input device until it comes back. Choose another to stop waiting for it.",
          warning: true
        ) {
          preferredUID = ""
          onChanged()
        }
      }
    }
    .onAppear { deviceListObserver.start() }
    .onDisappear { deviceListObserver.stop() }
    .task(id: deviceListObserver.revision) { await refreshDevices() }
  }

  /// Coalesced: HAL property reads have no cancellation or deadline, so a slow
  /// or wedged driver must strand at most one probe worker no matter how many
  /// device-list notifications arrive — later revisions fold into a single
  /// trailing rerun instead of each launching another full enumeration.
  @MainActor
  private func refreshDevices() async {
    if refreshInFlight {
      refreshQueued = true
      return
    }
    refreshInFlight = true
    defer { refreshInFlight = false }
    // No Task.isCancelled in the loop condition: when a new `.task(id:)`
    // revision cancels this invocation, the newer one has already delegated
    // its rerun here by setting refreshQueued — dropping it would leave a
    // just-connected device missing until the next notification.
    repeat {
      refreshQueued = false
      let latest = await Task.detached(priority: .utility) {
        AudioCaptureService.availableInputDevices().map { device in
          PickerInputDevice(
            uid: device.uid,
            name: device.name,
            isBluetooth: AudioCaptureService.isBluetoothTransport(deviceID: device.id)
          )
        }
      }.value
      devices = latest
    } while refreshQueued
  }

  /// True when the user has pinned a device that the current enumeration does not contain.
  /// Guarded on a completed probe: before the first `refreshDevices()` returns, `devices` is
  /// empty for every account and an unguarded check would flash the warning at anyone with a
  /// pinned microphone.
  private var pinnedDeviceIsMissing: Bool {
    guard !preferredUID.isEmpty, !devices.isEmpty else { return false }
    return !devices.contains { $0.uid == preferredUID }
  }

  @ViewBuilder
  private func row(
    selected: Bool,
    title: String,
    subtitle: String? = nil,
    badge: String? = nil,
    warning: Bool = false,
    action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      HStack(alignment: .top, spacing: 12) {
        Image(systemName: warning ? "exclamationmark.triangle.fill" : (selected ? "checkmark.circle.fill" : "circle"))
          .scaledFont(size: 20)
          .foregroundColor(warning ? SettingsInk.notice : (selected ? Ink.primary : Ink.secondary))

        VStack(alignment: .leading, spacing: 4) {
          HStack(spacing: 8) {
            Text(title)
              .scaledFont(size: 14, weight: .medium)
              .foregroundColor(warning ? SettingsInk.notice : Ink.primary)
            if let badge {
              Text(badge)
                .scaledFont(size: 11, weight: .semibold)
                .foregroundColor(Ink.primary)
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .background(Ink.hairline)
                .clipShape(Capsule())
            }
          }
          if let subtitle {
            Text(subtitle)
              .scaledFont(size: 12)
              .foregroundColor(Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
        }

        Spacer()
      }
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
  }
}
